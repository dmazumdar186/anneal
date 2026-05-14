"""Token counter and per-run budget enforcement.

Pricing table (USD per 1 million tokens, blended input+output proxy).
Updated 2026-05-13. Sources: anthropic.com/pricing and openrouter.ai/models.

Anthropic direct (via ClaudeLLM):
    claude-haiku-4-5-20251001 / claude-haiku-4-5 : $2.00  (~$1 in / $5 out blended)
    claude-sonnet-4-6                             : $5.00  (~$3 in / $15 out blended)
    claude-opus-4-7                               : $25.00 (~$15 in / $75 out blended)

OpenRouter (via OpenRouterLLM — model IDs as OpenRouter slugs):
    google/gemini-2.5-flash                  : $0.30  (~$0.075 in / $0.30 out)
    deepseek/deepseek-chat                   : $0.50
    meta-llama/llama-3.3-70b-instruct        : $0.40
    openai/gpt-5                             : $8.00  (OpenAI via OpenRouter, ~5% markup)
    anthropic/claude-haiku-4-5               : $2.10  (Haiku via OpenRouter, ~5% markup)

All prices are rough proxies. The purpose is budget-gate enforcement (abort before
runaway cost), not billing reconciliation.
"""

from __future__ import annotations

# USD per 1M tokens, blended input+output proxy. Updated 2026-05-13.
# Source: anthropic.com/pricing and openrouter.ai/models.
_PRICES_USD_PER_MILLION: dict[str, float] = {
    # Anthropic direct (via ClaudeLLM)
    "claude-haiku-4-5-20251001": 2.0,    # ~$1 in / $5 out blended
    "claude-haiku-4-5": 2.0,             # alias
    "claude-sonnet-4-6": 5.0,            # ~$3 in / $15 out blended
    "claude-opus-4-7": 25.0,             # ~$15 in / $75 out blended
    # OpenRouter (via OpenRouterLLM) — model IDs as OpenRouter slugs
    "google/gemini-2.5-flash": 0.30,     # cheap; ~$0.075 in / $0.30 out
    "deepseek/deepseek-chat": 0.50,
    "meta-llama/llama-3.3-70b-instruct": 0.40,
    "openai/gpt-5": 8.0,                 # OpenAI via OpenRouter (small markup)
    "anthropic/claude-haiku-4-5": 2.1,   # Haiku via OpenRouter (~5% markup over direct)
}
# Fallback for unknown models
_DEFAULT_PRICE = 10.0

# Keep legacy name as alias for backward compat with any existing callers
_PRICE_PER_M = _PRICES_USD_PER_MILLION
_DEFAULT_PRICE_PER_M = _DEFAULT_PRICE

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class BudgetExceeded(Exception):
    """Raised when cumulative token cost exceeds the configured max_cost_usd."""


class CostTracker:
    """Tracks token usage across rounds and enforces a USD budget ceiling.

    Example::

        tracker = CostTracker(max_usd=1.00)
        tracker.add(500_000, "claude-sonnet-4-6")  # $2.50 per 1M → $1.25 total
        tracker.check()  # raises BudgetExceeded
    """

    def __init__(self, max_usd: float) -> None:
        self._max_usd = max_usd
        self._total_tokens: int = 0
        self._total_usd: float = 0.0
        # per-model breakdown: model → {tokens, usd}
        self._breakdown: dict[str, dict[str, float | int]] = {}

    def _price(self, model: str) -> float:
        """Return USD per 1M tokens for the given model."""
        return _PRICES_USD_PER_MILLION.get(model, _DEFAULT_PRICE)

    def add(self, tokens_used: int, model: str | None = None) -> None:
        """Record token usage for a single LLM call.

        Args:
            tokens_used: Total tokens consumed (input + output).
            model: Model name. Defaults to claude-haiku-4-5-20251001 if None.

        Raises:
            BudgetExceeded: if cumulative cost now exceeds max_usd.
        """
        model = model or _DEFAULT_MODEL
        cost = tokens_used * self._price(model) / 1_000_000.0

        self._total_tokens += tokens_used
        self._total_usd += cost

        if model not in self._breakdown:
            self._breakdown[model] = {"tokens": 0, "usd": 0.0}
        self._breakdown[model]["tokens"] = int(self._breakdown[model]["tokens"]) + tokens_used
        self._breakdown[model]["usd"] = float(self._breakdown[model]["usd"]) + cost

        self.check()

    def check(self) -> None:
        """Raise BudgetExceeded if current spend is already over the limit."""
        if self._total_usd > self._max_usd:
            raise BudgetExceeded(
                f"Budget exceeded: ${self._total_usd:.4f} spent, "
                f"limit is ${self._max_usd:.4f}"
            )

    @property
    def total_usd(self) -> float:
        """Total USD spent so far."""
        return self._total_usd

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed so far."""
        return self._total_tokens

    @property
    def estimated_cost_usd(self) -> float:
        """Best-effort USD estimate based on model pricing table (alias for total_usd)."""
        return self._total_usd

    def summary(self) -> dict:
        """Return totals and per-model breakdown.

        Returns::

            {
                "total_tokens": 12000,
                "total_usd": 0.06,
                "max_usd": 5.0,
                "remaining_usd": 4.94,
                "per_model": {
                    "claude-sonnet-4-6": {"tokens": 12000, "usd": 0.06}
                }
            }
        """
        return {
            "total_tokens": self._total_tokens,
            "total_usd": round(self._total_usd, 6),
            "max_usd": self._max_usd,
            "remaining_usd": round(self._max_usd - self._total_usd, 6),
            "per_model": {
                model: {"tokens": int(v["tokens"]), "usd": round(float(v["usd"]), 6)}
                for model, v in self._breakdown.items()
            },
        }
