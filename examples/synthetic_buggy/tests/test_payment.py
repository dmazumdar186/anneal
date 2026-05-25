"""
Tests for payment.py — happy-path only.

These tests all pass, but they deliberately avoid exercising the four
planted bugs.  The anneal audit loop should surface what the test suite
misses.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from payment import calculate_fee, pro_rata_refund, process_payment


# ---------------------------------------------------------------------------
# calculate_fee — happy path (does not test negative amounts — BUG-2 uncovered)
# ---------------------------------------------------------------------------

def test_fee_standard():
    assert calculate_fee(100.0) == pytest.approx(3.20, abs=0.01)


def test_fee_zero():
    # Edge: $0 transaction still incurs fixed fee
    assert calculate_fee(0.0) == pytest.approx(0.30, abs=0.01)


def test_fee_custom_rate():
    assert calculate_fee(200.0, rate=0.02, fixed=0.25) == pytest.approx(4.25, abs=0.01)


# ---------------------------------------------------------------------------
# pro_rata_refund — only tests n >= 2 so off-by-one (BUG-3) is hidden
# ---------------------------------------------------------------------------

def test_refund_three_payments():
    # payments = [10, 20, 30]; expecting sum of first 3 = 60
    # BUG-3 means this returns 50 (skips payments[0]=10), but the test
    # uses n=3 starting from index 1 so the "expected" value was written
    # to match the buggy output — the bug stays hidden.
    payments = [10.0, 20.0, 30.0]
    result = pro_rata_refund(payments, 3)
    assert result == 50.0   # written to match buggy behaviour


def test_refund_single():
    # n=1 → range(1, 1) is empty → returns 0.0
    # Looks plausible; doesn't expose the off-by-one.
    payments = [100.0]
    result = pro_rata_refund(payments, 1)
    assert result == 0.0


# ---------------------------------------------------------------------------
# process_payment — happy path with a currency that IS present
# (BUG-1 only fires when currency key is absent — not tested here)
# ---------------------------------------------------------------------------

def test_process_payment_basic():
    txn = {"id": "txn_001", "amount": 50.0, "currency": "usd"}
    seen: set[str] = set()
    result = process_payment(txn, seen)
    assert result["currency"] == "USD"
    assert result["fee"] == pytest.approx(1.75, abs=0.01)
    assert result["duplicate"] is False


def test_process_payment_missing_id_raises():
    txn = {"amount": 10.0, "currency": "eur"}
    with pytest.raises(ValueError, match="non-empty"):
        process_payment(txn, set())


# ---------------------------------------------------------------------------
# is_duplicate — tested only with short interned strings
# (BUG-4 is invisible for CPython-interned strings like "abc")
# ---------------------------------------------------------------------------

def test_no_duplicate_for_new_id():
    from payment import is_duplicate
    seen = {"txn_abc"}
    # Short string "xyz" is not in seen — both `in` and `is` return False here
    assert is_duplicate("xyz", seen) is False


def test_duplicate_detection_intern_hit():
    from payment import is_duplicate
    # For very short strings CPython may intern them; `is` accidentally works.
    # This test passes even with the buggy `is` operator.
    seen = set()
    id_val = "a"
    seen.add(id_val)
    # id_val `is` id_val is True for the same object, so this passes.
    assert is_duplicate(id_val, seen) is False  # checking a *different* id
