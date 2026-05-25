# Changelog

## v0.1 — 2026-05-25

18 roadmap items + 1 bonus shipped. Tests: 73 → 136.

### T1 — Foundation hardening

| Item | Commit | Description |
|---|---|---|
| T1.1 | — | Phase 4c real-API canary — UNBLOCKED via BONUS Gemini adapter + `cheap-gemini` tier |
| T1.2 | `25f979a` | Cache-aware cost model: prompt-cache pricing for Claude (input / cache_read / cache_write / output) |
| T1.3 | `e1aebc3` | `ultra` tier: Opus 4.7 auditor/fixer/red/blue + Sonnet 4.6 judge |
| T1.4 | `d8fddc1` | Example fixtures: `examples/synthetic_buggy/` and `examples/adversarial_demo/` |
| T1.5 | — | Claude Code skill wrapper installed at `~/.claude/skills/anneal/` |

### T2 — Static analysis + signal enrichment

| Item | Commit | Description |
|---|---|---|
| T2.6a | `7d7db7e` | SAST scaffold + ruff runner |
| T2.6b | `c36f62f` | Semgrep runner |
| T2.6c | `3a1ac64` | SAST pre-pass wired into classic loop; findings injected as audit context |
| T2.7 | `af4d4d8` | Multi-sample voting auditor with configurable consensus threshold |
| T2.8a | `115af61` | Repo-graph: Python symbol extractor + caller index |
| T2.8b | `fa99332` | Repo-graph context wired into classic loop |
| T2.9 | — | SWE-Bench Lite — PARKED (estimated cost ~$20, over $5 budget) |

### T3 — Parallelism + language coverage

| Item | Commit | Description |
|---|---|---|
| T3.10 | `91073d2` | AST-aware semantic diff: unified diff annotated with symbol-level change classification |
| T3.11 | `03a3a1f` | Parallel Judge calls via thread pool in adversarial mode |
| T3.12 | `15d63db` | Suppressions DB: persistent SQLite store for known-false-positive findings |
| T3.13 | `2566ca2` | JavaScript (Vitest) and Go test runners alongside Python |

### T4 — Determinism + specialization + interactivity

| Item | Commit | Description |
|---|---|---|
| T4.14 | `9da1509` | Deterministic replay: temperature=0 + seed control (classic loop; adversarial loop not yet patched) |
| T4.15 | `e7d12e2` | Specialized fixers: test-fixer, security-fixer, refactor-fixer with router |
| T4.16 | `834d849` | Specialized Red agents: security-red, perf-red, logic-red + coordinator |
| T4.17 | `7021f55` | Human-in-the-loop pause at failure modes (`--interactive`) |
| T4.18 | `204c3cd` | VotingJudge: meta-verification wrapper with majority vote over parallel Judge calls |

### BONUS

| Item | Commit | Description |
|---|---|---|
| Gemini adapter | `5021e94` | Direct Gemini provider + `cheap-gemini` tier; unblocks real-API canary without OpenRouter balance |

---

Stats (T1.4 baseline `d8fddc1` → HEAD): 69 files changed, +6706 / -108 lines.

## v0.0.1 — prior session

Phases 1–4b: scaffold, foundation, classic loop, OpenRouter pivot, adversarial primitives + loop, canary fixtures + runner. 73 unit tests, all mock-based.
