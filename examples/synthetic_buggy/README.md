# synthetic_buggy — classic mode demo

`payment.py` is a small payment-processing module with **4 planted bugs** of
distinct classes.  The test suite passes (all happy-path) but does not cover
the bugs.  Run `anneal` to watch the audit loop surface them automatically.

## Quick start

```bash
cd examples/synthetic_buggy

# Commit the buggy state so anneal has a diff to audit
git add . && git commit -m "demo: synthetic_buggy fixture"

# Classic mode — cheap tier, audit HEAD vs HEAD~1
anneal --tier cheap HEAD~1
```

> **Tip:** if you haven't committed yet, `anneal HEAD` audits your working
> tree against the last commit.

## What to expect

Round 1 should produce 4 findings (one per bug class).  The fixer patches
them, round 2 runs clean, and anneal terminates at **2 consecutive clean
rounds**.

**Sample output (abridged):**

```
[anneal] round 1 — auditing diff (37 lines changed)
  FINDING  HIGH   payment.py:22  null-dereference — currency.upper() on None
  FINDING  HIGH   payment.py:36  missing-validation — negative amount accepted
  FINDING  MEDIUM payment.py:50  off-by-one — range(1, n) skips index 0
  FINDING  HIGH   payment.py:65  wrong-comparator — `is` instead of `in`
[anneal] round 1 — 4 findings → applying fixes ...
[anneal] round 2 — 0 findings (clean)
[anneal] round 3 — 0 findings (clean) → converged in 2 consecutive clean rounds
```

## Cost estimate

- **cheap tier** (~Haiku / GPT-4o-mini): ~$0.05–0.10 per run
- **balanced tier** (~Sonnet): ~$0.15–0.25 per run

## Planted bugs

See [`expected_findings.md`](expected_findings.md) for the full catalogue with
file:line references and recommended fixes.

| # | Class | Line | Severity |
|---|-------|------|----------|
| 1 | null/missing-key | ~22 | HIGH |
| 2 | missing input validation | ~36 | HIGH |
| 3 | off-by-one | ~50 | MEDIUM |
| 4 | wrong comparator | ~65 | HIGH |
