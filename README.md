# anneal

anneal hardens code diffs by running an auditor+fixer loop, or a Red-vs-Blue adversarial loop, until convergence. Classic mode runs a single auditor that finds issues and a fixer that patches them, repeating until N consecutive clean rounds. Adversarial mode pits a Red agent (writing failing tests or structured findings) against a Blue agent (audit+fix), iterating until Red comes up empty.

## Install

```bash
pip install -e .
```

## Try the examples

```bash
# Classic mode — 4 planted bugs in a payment module
cd examples/synthetic_buggy && anneal --tier cheap HEAD~1

# Adversarial mode — Red vs Blue duel on a "hardened" rate-limiter
cd examples/adversarial_demo && anneal adversarial --tier cheap HEAD~1
```

Each example directory has a `README.md` explaining the planted bugs,
expected output, and cost estimate.

## Quick start

```bash
# Classic mode — audit+fix loop on HEAD
anneal HEAD

# Adversarial mode — Red vs Blue
anneal adversarial HEAD

# AM replay demo
anneal replay-am --commit cc4fca1 --repo /path/to/antigravity

# Canary suite
anneal canary --subset all
```

## Status: v0.0.1 — under active development
