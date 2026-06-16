# Changelog

## Unreleased

### Added

- **Loop with memory (classic mode).** The auditor at round N+1 now receives a "Prior round attempts" markdown block summarizing what was raised in earlier rounds and the fixer's rationale for each attempted patch. The prompt instructs the auditor to (a) avoid re-raising findings the latest fix resolved, (b) re-raise findings the fix tried-and-failed at, and (c) avoid proposing approaches the fixer already tried. Adopted from the vibe-check improvement-loop pattern; same Karpathy-derived discipline as `anneal`'s existing structure, made explicit at the prompt level.
  - New: `PriorAttempt` dataclass + `format_prior_attempts(history)` helper in `anneal.audit.base`.
  - New: `prior_attempts: str = ""` kwarg on the `Auditor` Protocol, `PipelineAuditor.audit()`, and `VotingAuditor.audit()` (back-compat default).
  - New: classic loop tracks one `PriorAttempt` per FAIL/WARNINGS round (verdict + finding summaries + fixer rationale) and feeds it forward. Captured even when the patch fails to apply.
  - Hard cap of 5 prior rounds in the prompt; per-rationale cap of 600 chars with ellipsis truncation. Bounds context size.
  - Updated `audit/prompts/pipeline_auditor.md` with the prior-attempts handling note.
  - Tests: `test_prior_attempts_format.py` (7), `test_pipeline_auditor_prior_attempts.py` (4), `test_voting_prior_attempts.py` (3), `test_loop_classic_memory.py` (2). 16 new + 0 regressions (157 pass / 4 skipped baseline).
  - **Tests verify *injection*, not *effect*.** All tests are mock-based. Real-LLM empirical validation (does the memory actually reduce rounds-to-convergence?) is owed — see HANDOFF.md §5 for the benchmark recipe.
  - **Prompt-caching impact: zero.** `ClaudeLLM` caches only the system block (`cache_control={"type": "ephemeral"}`); `prior_attempts` lands in the user message, which is not cached. Per-round overhead bounded at ~1.2k input tokens (5 rounds × 600 char cap + headers) ≈ $0.0036/round at Sonnet 4.6 pricing.
  - **Back-compat:** `prior_attempts=""` is the default; existing callers and tests behave identically. The new behavior only activates when the loop populates the block (round 2+ after a FAIL/WARNINGS round).
  - Adversarial mode unchanged (uses Red/Blue Attack protocol, separate from `Auditor`). A future change can mirror the pattern there if useful — see HANDOFF.md §5 for the design tension (over-constraining Red collapses the attack distribution).

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
