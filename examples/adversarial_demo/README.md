# adversarial_demo — Red vs Blue mode

`token_bucket.py` is a token-bucket rate-limiter that *looks* hardened:
type hints, docstrings, thread-safety via `Lock`, and a full passing test
suite.  Two subtle vulnerabilities survive static inspection and the existing
tests.

## Quick start

```bash
cd examples/adversarial_demo

# Commit the state so anneal has a diff
git add . && git commit -m "demo: adversarial_demo fixture"

# Adversarial mode — Red attacks, Blue defends
anneal adversarial --tier cheap HEAD~1
```

## What Red should attack

Red receives the diff and generates **adversarial tests** or **structured
findings** targeting:

1. **Degenerate constructor inputs** — what happens with `capacity=0`?
   With `rate=0`?  These edge cases are not guarded.

2. **Concurrent `consume()` calls** — the lock is released between the
   token check and the decrement.  A multithreaded stress test should be
   able to drain more tokens than the bucket holds.

## What Blue must defend

Blue receives Red's findings and patches `token_bucket.py`.  A clean defence:

- Add positivity guards in `__init__` (raises `ValueError` on bad params).
- Move the check + decrement inside the `with self._lock:` block in
  `consume()` — atomic check-then-act.

## Expected duel flow

| Round | Red | Blue |
|-------|-----|------|
| 1 | Finds missing constructor validation | Patches `__init__` |
| 2 | Finds check-then-act race in `consume()` | Moves decrement inside lock |
| 3 | No findings | No changes |
| — | Judge declares Blue wins | — |

See [`expected_outcome.md`](expected_outcome.md) for the full breakdown,
including line numbers, severity, and recommended fixes.

## Cost estimate

- **cheap tier**: ~$0.15–0.30 (2 productive rounds + 1 confirmation)
- **balanced tier**: ~$0.30–0.50
