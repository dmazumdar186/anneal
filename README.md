# anneal

anneal hardens code diffs by running an auditor+fixer loop, or a Red-vs-Blue adversarial loop, until convergence. Classic mode runs a single auditor that finds issues and a fixer that patches them, repeating until N consecutive clean rounds. Adversarial mode pits a Red agent (writing failing tests or structured findings) against a Blue agent (audit+fix), iterating until Red comes up empty.

## Install

```bash
pip install -e .
```

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
