"""Unit tests for CostTracker: pricing, budget enforcement, and summary shape."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from anneal.cost import BudgetExceeded, CostTracker


def test_add_haiku_tokens_cost() -> None:
    """1M tokens at claude-haiku-4-5-20251001 ($2/M) → total_usd ≈ 2.00 (±0.01)."""
    tracker = CostTracker(max_usd=100.0)
    tracker.add(1_000_000, "claude-haiku-4-5-20251001")
    assert abs(tracker.total_usd - 2.00) < 0.01


def test_add_sonnet_tokens_cost() -> None:
    """1M tokens at claude-sonnet-4-6 ($5/M) → total_usd ≈ 5.00 (±0.01)."""
    tracker = CostTracker(max_usd=100.0)
    tracker.add(1_000_000, "claude-sonnet-4-6")
    assert abs(tracker.total_usd - 5.00) < 0.01


def test_add_gemini_flash_tokens_cost() -> None:
    """1M tokens at google/gemini-2.5-flash ($0.30/M) → total_usd ≈ 0.30 (±0.01)."""
    tracker = CostTracker(max_usd=100.0)
    tracker.add(1_000_000, "google/gemini-2.5-flash")
    assert abs(tracker.total_usd - 0.30) < 0.01


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
    """summary() returns a dict with total_usd and per_model keys."""
    tracker = CostTracker(max_usd=10.0)
    tracker.add(100_000, "claude-haiku-4-5-20251001")
    tracker.add(50_000, "claude-opus-4-7")

    s = tracker.summary()

    assert "total_usd" in s
    assert "by_model" in s or "per_model" in s
    assert s["total_usd"] > 0


# ── Cache-aware pricing tests ──────────────────────────────────────────────────


def test_cache_read_tokens_billed_at_tenth_rate() -> None:
    """1M cache-read tokens on Sonnet ($0.30/M) → $0.30, not $3.00 (flat input rate).

    Sonnet input = $3.00/M; cache_read = $0.30/M (0.1× input).
    """
    tracker = CostTracker(max_usd=100.0)
    tracker.add(
        tokens_used=1_000_000,
        model="claude-sonnet-4-6",
        cache_read_tokens=1_000_000,
        output_tokens=0,
    )
    # Expect $0.30 (cache_read rate), NOT $3.00 (input rate)
    assert abs(tracker.total_usd - 0.30) < 0.01


def test_cache_creation_tokens_billed_at_write_rate() -> None:
    """1M cache-creation tokens on Sonnet ($3.75/M) → $3.75, not $3.00 (flat input).

    Sonnet input = $3.00/M; cache_write = $3.75/M (1.25× input).
    """
    tracker = CostTracker(max_usd=100.0)
    tracker.add(
        tokens_used=1_000_000,
        model="claude-sonnet-4-6",
        cache_creation_tokens=1_000_000,
        output_tokens=0,
    )
    # Expect $3.75 (cache_write rate), NOT $3.00 (input rate)
    assert abs(tracker.total_usd - 3.75) < 0.01


def test_mixed_cache_usage_sums_correctly() -> None:
    """Mixed token categories on Sonnet compute weighted cost correctly.

    Breakdown (all 1M each, total tokens_used = 4M):
    - 1M uncached input:        1M × $3.00/M = $3.00
    - 1M cache_read:            1M × $0.30/M = $0.30
    - 1M cache_creation:        1M × $3.75/M = $3.75
    - 1M output:                1M × $15.00/M = $15.00
    Expected total:  $22.05
    """
    tracker = CostTracker(max_usd=100.0)
    tracker.add(
        tokens_used=4_000_000,
        model="claude-sonnet-4-6",
        cache_read_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    expected = 3.00 + 0.30 + 3.75 + 15.00  # = 22.05
    assert abs(tracker.total_usd - expected) < 0.01


# ── Thread-safety tests ───────────────────────────────────────────────────────


def test_cost_tracker_thread_safe() -> None:
    """100 threads each add 100 tokens; no increments must be lost under concurrency."""
    tracker = CostTracker(max_usd=1_000.0)
    n_threads = 100
    tokens_per_thread = 100
    model = "claude-sonnet-4-6"

    barrier = threading.Barrier(n_threads)

    def _add() -> None:
        barrier.wait()  # all threads start simultaneously
        tracker.add(tokens_per_thread, model)

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        futures = [pool.submit(_add) for _ in range(n_threads)]
        for f in futures:
            f.result()  # re-raise any exception

    assert tracker.total_tokens == n_threads * tokens_per_thread
