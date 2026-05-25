"""Token counter and per-run budget enforcement.

Pricing table (USD per 1 million tokens). Updated 2026-05-25.
Sources: anthropic.com/pricing and openrouter.ai/models.

Anthropic direct (via ClaudeLLM) — full per-token-type pricing:
    claude-haiku-4-5-20251001 / claude-haiku-4-5:
        input $1/M, cache_read $0.10/M, cache_write $1.25/M, output $5/M
    claude-sonnet-4-6:
        input $3/M, cache_read $0.30/M, cache_write $3.75/M, output $15/M
    claude-opus-4-7:
        input $15/M, cache_read $1.50/M, cache_write $18.75/M, output $75/M

OpenRouter (via OpenRouterLLM — model IDs as OpenRouter slugs):
    Caching is NOT uniformly supported via OpenRouter; flat blended rates used.
    google/gemini-2.5-flash          : $0.30  (~$0.075 in / $0.30 out)
    deepseek/deepseek-chat           : $0.50
    meta-llama/llama-3.3-70b-instruct: $0.40
    openai/gpt-5                     : $8.00  (OpenAI via OpenRouter, ~5% markup)
    anthropic/claude-haiku-4-5       : $2.10  (Haiku via OpenRouter, ~5% markup)

All prices are rough proxies. The purpose is budget-gate enforcement (abort before
runaway cost), not billing reconciliation.
"""

from __future__ import annotations

from typing import TypedDict


class _ModelPricing(TypedDict):
    """Per-model pricing in USD per 1M tokens, by token category."""

    input: float        # standard (non-cached) input tokens
    cache_read: float   # prompt-cache read tokens (Anthropic: 0.1× input)
    cache_write: float  # prompt-cache creation tokens (Anthropic: 1.25× input)
    output: float       # output / completion tokens


# Full per-token-type pricing for Anthropic direct models.
# cache_read = 0.1 × input; cache_write = 1.25 × input (Anthropic standard ratios).
_ANTHROPIC_PRICES: dict[str, _ModelPricing] = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "cache_read": 0.10,
        "cache_write": 1.25,
        "output": 5.00,
    },
    "claude-haiku-4-5": {  # alias
        "input": 1.00,
        "cache_read": 0.10,
        "cache_write": 1.25,
        "output": 5.00,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
        "output": 15.00,
    },
    "claude-opus-4-7": {
        "input": 15.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
        "output": 75.00,
    },
}

# Flat blended rates for non-Anthropic / OpenRouter models (no cache breakdown).
# Represented as _ModelPricing with cache_read == cache_write == input for simplicity.
def _flat(blended: float) -> _ModelPricing:
    return {
        "input": blended,
        "cache_read": blended,
        "cache_write": blended,
        "output": blended,
    }


_OPENROUTER_PRICES: dict[str, _ModelPricing] = {
    "google/gemini-2.5-flash": _flat(0.30),
    "deepseek/deepseek-chat": _flat(0.50),
    "meta-llama/llama-3.3-70b-instruct": _flat(0.40),
    "openai/gpt-5": _flat(8.00),
    "anthropic/claude-haiku-4-5": _flat(2.10),  # Haiku via OR (~5% markup, no cache)
}

_ALL_MODEL_PRICES: dict[str, _ModelPricing] = {
    **_ANTHROPIC_PRICES,
    **_OPENROUTER_PRICES,
}

# Legacy flat-rate table kept for backward compat (canary/runner imports it).
_PRICES_USD_PER_MILLION: dict[str, float] = {
    "claude-haiku-4-5-20251001": 2.0,
    "claude-haiku-4-5": 2.0,
    "claude-sonnet-4-6": 5.0,
    "claude-opus-4-7": 25.0,
    "google/gemini-2.5-flash": 0.30,
    "deepseek/deepseek-chat": 0.50,
    "meta-llama/llama-3.3-70b-instruct": 0.40,
    "openai/gpt-5": 8.0,
    "anthropic/claude-haiku-4-5": 2.1,
}
_DEFAULT_PRICE = 10.0

# Keep legacy name as alias for backward compat with any existing callers
_PRICE_PER_M = _PRICES_USD_PER_MILLION
_DEFAULT_PRICE_PER_M = _DEFAULT_PRICE

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class BudgetExceeded(Exception):
    """Raised when cumulative token cost exceeds the configured max_cost_usd."""


class CostTracker:
    """Tracks token usage across rounds and enforces a USD budget ceiling.

    Basic (flat-rate) usage — backward-compatible::

        tracker = CostTracker(max_usd=1.00)
        tracker.add(500_000, "claude-sonnet-4-6")
        tracker.check()  # raises BudgetExceeded

    Cache-aware usage (Anthropic prompt caching)::

        tracker = CostTracker(max_usd=5.00)
        tracker.add(
            tokens_used=500,           # uncached input + output
            model="claude-sonnet-4-6",
            cache_read_tokens=4500,    # served from cache at 0.1× input price
            cache_creation_tokens=0,
            output_tokens=200,
        )
    """

    def __init__(self, max_usd: float) -> None:
        self._max_usd = max_usd
        self._total_tokens: int = 0
        self._total_usd: float = 0.0
        # per-model breakdown: model → {tokens, usd}
        self._breakdown: dict[str, dict[str, float | int]] = {}

    def _pricing(self, model: str) -> _ModelPricing:
        """Return the full pricing dict for the given model."""
        return _ALL_MODEL_PRICES.get(model, _flat(_DEFAULT_PRICE))

    def _price(self, model: str) -> float:
        """Return blended USD per 1M tokens (legacy helper for backward compat)."""
        return _PRICES_USD_PER_MILLION.get(model, _DEFAULT_PRICE)

    def add(
        self,
        tokens_used: int,
        model: str | None = None,
        *,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record token usage for a single LLM call.

        Backward-compatible: if only ``tokens_used`` is passed (the old
        signature), the cost is computed using the flat blended price, exactly
        as before.

        Cache-aware: when ``cache_read_tokens`` / ``cache_creation_tokens`` /
        ``output_tokens`` are provided, the cost is computed per-category:

        * ``cache_read_tokens``    → billed at ``pricing.cache_read`` per 1M
        * ``cache_creation_tokens``→ billed at ``pricing.cache_write`` per 1M
        * ``output_tokens``        → billed at ``pricing.output`` per 1M
        * remaining input tokens   → ``tokens_used - output_tokens
                                       - cache_read_tokens - cache_creation_tokens``
                                       billed at ``pricing.input`` per 1M

        For non-Anthropic models the per-category prices are all equal to the
        blended rate, so the math is identical to the flat calculation.

        Args:
            tokens_used: Total tokens (input + output, as reported by the adapter).
                         When cache fields are omitted this is used directly with
                         the flat blended rate (legacy behaviour).
            model: Model name. Defaults to claude-haiku-4-5-20251001 if None.
            cache_read_tokens: Tokens served from Anthropic prompt cache.
            cache_creation_tokens: Tokens written into Anthropic prompt cache.
            output_tokens: Output / completion tokens (needed to split input correctly).

        Raises:
            BudgetExceeded: if cumulative cost now exceeds max_usd.
        """
        model = model or _DEFAULT_MODEL

        if cache_read_tokens or cache_creation_tokens or output_tokens:
            # Cache-aware path: compute weighted cost per token category.
            pricing = self._pricing(model)
            # Uncached input = total - output - cache_read - cache_creation
            uncached_input = max(
                0,
                tokens_used - output_tokens - cache_read_tokens - cache_creation_tokens,
            )
            cost = (
                uncached_input * pricing["input"]
                + cache_read_tokens * pricing["cache_read"]
                + cache_creation_tokens * pricing["cache_write"]
                + output_tokens * pricing["output"]
            ) / 1_000_000.0
        else:
            # Legacy flat-rate path: blended price × total tokens.
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
