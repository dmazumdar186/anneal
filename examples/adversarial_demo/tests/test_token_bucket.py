"""
Tests for token_bucket.py — passing suite that misses both vulnerabilities.

The tests exercise the happy path and basic rate-limiting semantics but:
  - never pass capacity=0 or rate=0 (misses VULNERABILITY-1)
  - are single-threaded, so the check-then-act race (VULNERABILITY-2) is
    invisible to pytest
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from token_bucket import TokenBucket


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------

def test_starts_full():
    b = TokenBucket(capacity=10.0, rate=1.0)
    assert b.available() == pytest.approx(10.0, abs=0.01)


# ---------------------------------------------------------------------------
# consume() — single-threaded happy path
# ---------------------------------------------------------------------------

def test_consume_allows_within_capacity():
    b = TokenBucket(capacity=5.0, rate=1.0)
    assert b.consume(3.0) is True
    assert b.available() == pytest.approx(2.0, abs=0.05)


def test_consume_rejects_when_empty():
    b = TokenBucket(capacity=1.0, rate=0.0001)  # refill too slow to matter
    assert b.consume(1.0) is True
    assert b.consume(1.0) is False


def test_consume_default_one_token():
    b = TokenBucket(capacity=3.0, rate=1.0)
    for _ in range(3):
        assert b.consume() is True
    assert b.consume() is False


# ---------------------------------------------------------------------------
# Refill over time
# ---------------------------------------------------------------------------

def test_tokens_refill_over_time():
    b = TokenBucket(capacity=10.0, rate=5.0)
    b._tokens = 0.0                      # drain manually for test speed
    b._last_refill = time.monotonic()
    time.sleep(0.2)
    # After 200 ms at 5 tok/s we expect ~1 token
    assert b.available() >= 0.8


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

def test_reset_refills_bucket():
    b = TokenBucket(capacity=5.0, rate=1.0)
    b.consume(5.0)
    b.reset()
    assert b.available() == pytest.approx(5.0, abs=0.05)


# ---------------------------------------------------------------------------
# Large single consume
# ---------------------------------------------------------------------------

def test_consume_more_than_capacity_fails():
    b = TokenBucket(capacity=3.0, rate=1.0)
    assert b.consume(10.0) is False
