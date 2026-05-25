# anneal

anneal hardens code diffs by running an auditor+fixer loop, or a Red-vs-Blue adversarial loop, until convergence. Classic mode runs a single auditor that finds issues and a fixer that patches them, repeating until N consecutive clean rounds. Adversarial mode pits a Red agent (writing failing tests or structured findings) against a Blue agent (audit+fix), iterating until Red comes up empty.

## Install

```bash
pip install -e .

# Optional: Gemini-direct support (no OpenRouter needed)
pip install -e ".[gemini]"
```

## Try the examples

```bash
# Classic mode — 4 planted bugs in a payment module
cd examples/synthetic_buggy && anneal --tier cheap HEAD~1

# Adversarial mode — Red vs Blue duel on a "hardened" rate-limiter
cd examples/adversarial_demo && anneal adversarial --tier cheap HEAD~1
```

Each example directory has a `README.md` explaining the planted bugs, expected output, and cost estimate.

## Quick start

```bash
# Classic mode — audit+fix loop on HEAD
anneal HEAD

# Adversarial mode — Red vs Blue
anneal adversarial HEAD

# Canary suite
anneal canary --subset all

# Manage suppressions
anneal suppressions list
anneal suppressions add "finding pattern to suppress"
anneal suppressions remove <id>
```

## Tiers

| Tier | Auditor / Fixer / Red / Blue | Judge | Provider | Approx cost / round |
|------|------------------------------|-------|----------|---------------------|
| `cheap` | `google/gemini-2.5-flash` | `google/gemini-2.5-flash` | OpenRouter (all) | ~$0.01 |
| `balanced` (default) | `claude-haiku-4-5-20251001` | `google/gemini-2.5-flash` | Anthropic + OpenRouter | ~$0.05 |
| `premium` | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` | Anthropic (all) | ~$0.20 |
| `ultra` | `claude-opus-4-7` | `claude-sonnet-4-6` | Anthropic (all) | ~$1.00 |
| `cheap-gemini` | `gemini-2.0-flash` | `gemini-2.0-flash` | Gemini direct | ~$0.01 |

Use `--tier ultra` for high-stakes diffs (security, payments, migrations).
Use `--tier cheap-gemini` when you have a Gemini API key but no OpenRouter balance.

## CLI flags

```bash
# Voting auditor
anneal HEAD --audit-samples 3 --vote-threshold 0.6

# VotingJudge (adversarial)
anneal adversarial HEAD --judge-samples 3 --judge-vote-threshold 0.6 \
  --judge-max-workers 4  # or --no-parallel-judge

# Deterministic replay (classic loop only)
anneal HEAD --deterministic --seed 42

# Human-in-the-loop pause at failure modes
anneal HEAD --interactive

# Gemini-direct tier
anneal HEAD --tier cheap-gemini

# Budget guard
anneal HEAD --max-cost-usd 2.00
```

## What v0.1 adds

Shipped across 19 commits in the T1–T4 implementation session (2026-05-25):

- **SAST pre-pass** — ruff + Semgrep scan before the LLM loop; findings injected as context
- **Repo-graph context** — Python symbol extractor + caller index; call graph attached to audit prompt
- **Voting auditor** — multi-sample consensus with configurable threshold (`--audit-samples`, `--vote-threshold`)
- **VotingJudge** — meta-verification layer with parallel Judge calls and majority vote
- **Suppressions DB** — persistent SQLite store for known-false-positive findings; survives across runs
- **AST-aware semantic diff** — unified diff annotated with symbol-level change classification
- **Interactive mode** — human-in-the-loop pause at failure modes (`--interactive`)
- **Deterministic replay** — temperature=0 + seed control for reproducible classic-loop runs
- **Multi-language test runners** — JavaScript (Vitest) and Go runners alongside Python
- **Specialized fixers** — router selects test-fixer, security-fixer, or refactor-fixer per finding type
- **Specialized Red agents** — security-red, perf-red, logic-red + coordinator for adversarial mode
- **Cache-aware cost model** — prompt-cache pricing for Claude models (input / cache_read / cache_write / output)
- **Direct Gemini adapter** — `gemini` provider + `cheap-gemini` tier; no OpenRouter dependency

## Status

v0.1 — 136 unit tests passing (all mock-based). Public repo: https://github.com/dmazumdar186/anneal
