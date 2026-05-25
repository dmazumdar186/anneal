# Expected Findings — synthetic_buggy

These four bugs are planted in `payment.py`.  A `--tier cheap` run should
surface all of them within 1-2 audit rounds.

---

## BUG-1 — Missing None guard (null/missing-key access)

| Field    | Value |
|----------|-------|
| File     | `payment.py` |
| Line     | ~22 (`return currency.upper()`) |
| Severity | HIGH |
| Class    | `null-dereference` / `AttributeError` |

`dict.get("currency")` returns `None` when the key is absent.  The very next
line calls `.upper()` on the result without a None guard, raising
`AttributeError: 'NoneType' object has no attribute 'upper'`.

**Fix:** `return (transaction.get("currency") or "").upper()` — or raise early
if currency is required.

---

## BUG-2 — Missing input validation (negative amount)

| Field    | Value |
|----------|-------|
| File     | `payment.py` |
| Line     | ~36 (`return round(rate * amount + fixed, 2)`) |
| Severity | HIGH |
| Class    | `missing-validation` |

`calculate_fee` accepts any float, including negative values.  A negative
amount produces a negative fee (`-0.29 * 100 + 0.30 = -2.60`), which could
credit the payer instead of charging them.

**Fix:** add a guard at the top of the function:
```python
if amount < 0:
    raise ValueError(f"amount must be non-negative, got {amount}")
```

---

## BUG-3 — Off-by-one in refund loop

| Field    | Value |
|----------|-------|
| File     | `payment.py` |
| Line     | ~50 (`for i in range(1, n):`) |
| Severity | MEDIUM |
| Class    | `off-by-one` |

`range(1, n)` skips index 0, so `payments[0]` is never included in the
refund total.  A refund for "first 3 payments" only covers payments 2 and 3.

**Fix:** `for i in range(n):` (or equivalently `range(0, n)`).

---

## BUG-4 — Wrong comparator (`is` instead of `in`)

| Field    | Value |
|----------|-------|
| File     | `payment.py` |
| Line     | ~65 (`return txn_id is seen_ids`) |
| Severity | HIGH |
| Class    | `wrong-comparator` |

`txn_id is seen_ids` tests object identity between a string and a set —
this always evaluates to `False`, so every transaction is considered
non-duplicate.  The duplicate-payment guard is completely bypassed.

Note: even if the intent were to compare two strings, `is` would be wrong
(it works coincidentally for CPython-interned short strings but silently
fails for dynamically constructed IDs).

**Fix:** `return txn_id in seen_ids`
