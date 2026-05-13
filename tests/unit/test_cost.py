"""Unit tests for CostTracker: pricing, budget enforcement, and summary shape."""

from __future__ import annotations

import pytest

from anneal.cost import BudgetExceeded, CostTracker


def test_add_sonnet_tokens_cost() -> None:
    """1M tokens at claude-sonnet-4-6 ($5/M) → total_usd ≈ 5.00 (±0.01)."""
    tracker = CostTracker(max_usd=100.0)
    tracker.add(1_000_000, "claude-sonnet-4-6")
    assert abs(tracker.total_usd - 5.00) < 0.01


def test_budget_exceeded_on_second_add() -> None:
    """200k sonnet tokens (~$1) fits; a second 200k trips BudgetExceeded."""
    tracker = CostTracker(max_usd=1.0)
    # 200_000 tokens × $5/M = $1.00 — exactly at the limit, should NOT raise
    # (the check is strictly-greater-than)
    tracker.add(200_000, "claude-sonnet-4-6")
    tracker.check()  # still at limit — no raise

    # One more token pushes over
    with pytest.raises(BudgetExceeded):
        tracker.add(1, "claude-sonnet-4-6")


def test_summary_shape() -> None:
    """summary() returns a dict with total_usd and by_model keys."""
    tracker = CostTracker(max_usd=10.0)
    tracker.add(100_000, "claude-sonnet-4-6")
    tracker.add(50_000, "claude-opus-4-7")

    s = tracker.summary()

    assert "total_usd" in s
    assert "by_model" in s or "per_model" in s
    assert s["total_usd"] > 0
