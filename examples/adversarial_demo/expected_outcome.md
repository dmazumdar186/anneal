# Expected Duel Outcome — adversarial_demo

Two hidden vulnerabilities in `token_bucket.py`.  The existing test suite
passes — Red must generate adversarial tests or structured findings to expose
them.

---

## VULNERABILITY-1 — Missing constructor validation

| Field    | Value |
|----------|-------|
| File     | `token_bucket.py` |
| Line     | ~30 (`self.capacity = capacity`) |
| Severity | MEDIUM |
| Class    | `missing-validation` |

`TokenBucket(capacity=0, rate=1.0)` is silently accepted.  With capacity=0
the bucket is permanently empty: `_tokens` can never exceed 0, so every call
to `consume()` returns False — the rate limiter hard-blocks all traffic
instead of rate-limiting it.

`TokenBucket(capacity=10, rate=0)` is also accepted.  With rate=0 the bucket
never refills; once drained it is permanently empty.  Neither of these
degeneracies raises an error.

**Red strategy:** generate a test that constructs `TokenBucket(0, 1)` and
asserts `consume()` returns True (it should for a valid 0-capacity bucket or
raise early for an invalid one).

**Blue fix:**
```python
if capacity <= 0:
    raise ValueError(f"capacity must be positive, got {capacity}")
if rate < 0:
    raise ValueError(f"rate must be non-negative, got {rate}")
```

---

## VULNERABILITY-2 — Check-then-act race (lock released too early)

| Field    | Value |
|----------|-------|
| File     | `token_bucket.py` |
| Line     | ~68 (between `with self._lock:` and `if self._tokens >= tokens:`) |
| Severity | HIGH |
| Class    | `race-condition` / `check-then-act` |

`_refill()` runs inside the lock, but the lock is released before the
`if self._tokens >= tokens` check and the `self._tokens -= tokens` decrement.
Two concurrent threads can both pass the guard, both decrement, and the bucket
goes negative — more requests are allowed than the capacity permits.

**Red strategy:** generate a multithreaded stress test that fires 100
concurrent `consume(1)` calls on a `TokenBucket(capacity=5, rate=0)` and
asserts `tokens_consumed <= 5`.  The buggy implementation allows >5.

**Blue fix:** move the check and decrement inside the `with self._lock:` block:
```python
def consume(self, tokens: float = 1.0) -> bool:
    with self._lock:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False
```

---

## Duel timeline

| Round | Agent | Action |
|-------|-------|--------|
| 1     | Red   | Generates adversarial test for capacity=0; finds VULNERABILITY-1 |
| 1     | Blue  | Adds positivity guard to `__init__`; patches VULNERABILITY-1 |
| 2     | Red   | Generates multithreaded stress test; finds VULNERABILITY-2 |
| 2     | Blue  | Moves check+decrement inside lock; patches VULNERABILITY-2 |
| 3     | Red   | No new findings |
| 3     | Blue  | No changes needed |
| —     | Judge | Duel ends: Blue wins, 0 open findings |

Expected total cost: **cheap tier ~$0.15–0.30** (2 productive Red rounds +
1 confirmation round).
