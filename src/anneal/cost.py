"""Token counter and per-run budget enforcement."""

from __future__ import annotations


class BudgetExceeded(Exception):
    """Raised when cumulative token cost exceeds the configured max_cost_usd."""


class CostTracker:
    """Tracks token usage across rounds and enforces a USD budget ceiling."""

    def __init__(self, max_cost_usd: float) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def add(self, tokens_used: int, model: str | None = None) -> None:
        """Record token usage for a single LLM call.

        Raises BudgetExceeded if cumulative cost exceeds max_cost_usd.
        """
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def check(self) -> None:
        """Raise BudgetExceeded if current spend is already over the limit."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed so far."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    @property
    def estimated_cost_usd(self) -> float:
        """Best-effort USD estimate based on model pricing table."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
