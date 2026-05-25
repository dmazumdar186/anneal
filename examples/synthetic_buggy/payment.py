"""
payment.py — a minimal payment-processing module.

This file contains 4 planted bugs for the anneal synthetic_buggy demo.
Run `anneal --tier cheap HEAD~1` from this directory to see them found.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def get_currency(transaction: dict[str, Any]) -> str:
    """Return the ISO currency code from a transaction record.

    BUG-1 (null/missing-key): uses dict.get() without a None guard,
    then calls .upper() unconditionally — raises AttributeError when the
    key is absent.
    """
    currency = transaction.get("currency")  # returns None if missing
    return currency.upper()                 # AttributeError if currency is None


# ---------------------------------------------------------------------------
# Fee calculation
# ---------------------------------------------------------------------------

def calculate_fee(amount: float, rate: float = 0.029, fixed: float = 0.30) -> float:
    """Return the processing fee for *amount* (Stripe-style: rate * amount + fixed).

    BUG-2 (missing input validation): negative amounts are accepted silently,
    producing a negative fee that can result in the merchant being *charged*
    rather than receiving funds.
    """
    return round(rate * amount + fixed, 2)


# ---------------------------------------------------------------------------
# Refund slice
# ---------------------------------------------------------------------------

def pro_rata_refund(payments: list[float], n: int) -> float:
    """Return the sum of the first *n* payments (1-indexed label, 0-indexed list).

    BUG-3 (off-by-one): range starts at 1, so payments[0] is always skipped.
    A refund that should cover payments 1-3 only covers 2-3.
    """
    total = 0.0
    for i in range(1, n):          # BUG: should be range(0, n) or range(n)
        total += payments[i]
    return round(total, 2)


# ---------------------------------------------------------------------------
# Duplicate-payment detection
# ---------------------------------------------------------------------------

def is_duplicate(txn_id: str, seen_ids: set[str]) -> bool:
    """Return True if *txn_id* has already been processed.

    BUG-4 (wrong comparator): uses `is` for string comparison.
    Works coincidentally for interned short strings in CPython,
    silently misses duplicates for longer / dynamically constructed IDs.
    """
    return txn_id is seen_ids   # BUG: should be `txn_id in seen_ids`


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_payment(transaction: dict[str, Any], seen_ids: set[str]) -> dict[str, Any]:
    """Validate and process a single payment transaction.

    Returns a result dict with fee, currency, and duplicate flag.
    Raises ValueError for invalid transactions.
    """
    txn_id = transaction.get("id", "")
    amount = transaction.get("amount", 0.0)

    if not txn_id:
        raise ValueError("transaction must have a non-empty 'id'")

    currency = get_currency(transaction)
    fee = calculate_fee(amount)
    duplicate = is_duplicate(txn_id, seen_ids)

    return {
        "id": txn_id,
        "amount": amount,
        "currency": currency,
        "fee": fee,
        "duplicate": duplicate,
    }
