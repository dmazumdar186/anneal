# anneal — session handoff

## What anneal is

A Python CLI + library that hardens code diffs through iterative LLM-driven loops. Two modes:
- **Classic** (`anneal <ref>`): auditor LLM finds issues → fixer LLM patches → re-audit → loop until N consecutive clean rounds.
- **Adversarial** (`anneal adversarial <ref>`): **Red vs Blue.** Red attacks (writes failing pytest files OR makes structured claims verified by a Judge LLM); Blue hardens. Loop until Red comes up empty for N rounds.

Public artifact + portfolio piece. Narrative ties back to a past client project (Accessory Masters / AM) where 16 audit rounds were run by hand using the same pattern.

## Where things live

- **Anneal repo:** `C:\Users\deban\dev\anneal\` — outside OneDrive. **Pushed to https://github.com/dmazumdar186/anneal (public).** `origin/master` tracks remote.
- **Plan file:** `C:\Users\deban\.claude\plans\new-project-eager-hopcroft.md`
- **Claude Code skill wrapper:** `~/.claude/skills/anneal/` (installed globally)

## Status: v0.1 — 138 unit tests passing

### Recent session — T1–T4 implementation + post-review hardening (2026-05-25)

18 roadmap items + 1 bonus + post-review hardening shipped across 22 commits. Tests: 73 → 138 (all mock-based, zero real API spend).

**Post-review hardening** (after independent code-reviewer audit returned FAIL with 3 critical + 3 high findings):
- `fa8100e` — `fix(v0.1): close 6 audit findings (concurrency, path traversal, tie-break, router cache, symlink, gemini exc)`
  - Added `threading.Lock` to `CostTracker` (race on `_total_usd +=` under ThreadPoolExecutor)
  - Added `threading.Lock` to `SuppressionStore` (concurrent `is_suppressed`-with-save corruption)
  - Added path-traversal guards in JS + Go test runners (LLM-supplied paths could escape worktree)
  - Removed module-level fixer-router cache (stale-`llm=None` instances poisoned later real-LLM calls)
  - Added symlink-cycle guard in `repograph.python_graph._walk_python_files`
  - Made `VotingAuditor` verdict tie-break deterministic (was insertion-order-dependent via `Counter.most_common`)
- `cdfceae` — `fix(subprocess): force utf-8 encoding on all subprocess output to avoid cp1252 errors on Windows`
  - Surfaced during meta-audit run: `subprocess._readerthread` defaulted to cp1252 on Windows English locale and crashed on bytes ≥ 0x80
  - Patched `diff/patch.py` and `diff/worktree.py` git invocations with explicit `encoding="utf-8", errors="replace"`

**Real-API validation (2026-05-25 with cheap-gemini tier + GEMINI_API_KEY)**:
- T1.1 canary on `planted` subset: **8.33% catch rate** (1 of 12 — `wrong_comparator` caught; rest missed), $0.0107 total, 1 transient Gemini 503 error on `regex_backtrack` fixture
- T1.1 meta-audit (`anneal classic HEAD~1 --tier cheap-gemini`): ran end-to-end, exited cleanly with `reason=patch_conflict`, $0.0064
- **Important caveat**: the canary runner uses single-shot auditor only — it does NOT exercise the new SAST pre-pass, multi-sample voting, repo-graph context, or semantic-diff features. The 8.33% is a baseline for "Gemini Flash auditor with no help"; the full v0.1 pipeline (--audit-samples 3 + SAST on) is expected to be significantly higher. Run with `--audit-samples 3 --vote-threshold 2` for a fairer measurement (cost ~3x).

**Known gaps** (not addressed this session):
- Gemini adapter has no second-level retry on transient 503/UNAVAILABLE (relies only on google-genai SDK's tenacity); transient errors get reported as fixture misses with traceback. Worth a small retry wrapper in `llm/gemini.py`.
- Adversarial-mode determinism: T4.14's `_apply_determinism()` only patches classic-loop auditor/fixer LLMs; adversarial Red/Blue/Judge LLMs still un-patched.



| Tier | Item | Commit | Status |
|---|---|---|---|
| T1.1 | Phase 4c real-API canary | — | **BLOCKED**: OR balance $0 + ANTHROPIC_API_KEY missing. **UNBLOCKED via bonus Gemini-direct adapter** (`5021e94`) + `--tier cheap-gemini` + GEMINI_API_KEY |
| T1.2 | Cache-aware cost model | `25f979a` | ✅ |
| T1.3 | Opus 4.7 + `ultra` tier | `e1aebc3` | ✅ |
| T1.4 | Example fixtures | `d8fddc1` | ✅ |
| T1.5 | Claude Code skill wrapper | — | ✅ (lives at `~/.claude/skills/anneal/`) |
| T2.6a | SAST scaffold + ruff | `7d7db7e` | ✅ |
| T2.6b | Semgrep runner | `c36f62f` | ✅ |
| T2.6c | SAST wired into classic loop | `3a1ac64` | ✅ |
| T2.7 | Multi-sample voting auditor | `af4d4d8` | ✅ |
| T2.8a | Repo-graph Python extractor | `115af61` | ✅ |
| T2.8b | Repo-graph wired into loop | `fa99332` | ✅ |
| T2.9 | SWE-Bench Lite | — | PARKED (over $5 budget) |
| T3.10 | AST-aware semantic diff | `91073d2` | ✅ |
| T3.11 | Parallel Judge calls | `03a3a1f` | ✅ |
| T3.12 | Suppressions DB | `15d63db` | ✅ |
| T3.13 | JS + Go test runners | `2566ca2` | ✅ |
| T4.14 | Deterministic replay | `9da1509` | ✅ |
| T4.15 | Specialized fixers (test/security/refactor) | `e7d12e2` | ✅ |
| T4.16 | Specialized Red agents (security/perf/logic) | `834d849` | ✅ |
| T4.17 | Human-in-the-loop pause | `7021f55` | ✅ |
| T4.18 | VotingJudge meta-verification | `204c3cd` | ✅ |
| BONUS | Direct Gemini adapter + cheap-gemini tier | `5021e94` | ✅ |

### Prior session — phases 1–4b (baseline at HANDOFF)

| Phase | Final SHA | What landed |
|---|---|---|
| 1 Scaffold | `558b474` | 81-file skeleton, pyproject.toml, .env.example |
| 2a Foundation | `d131d27` | config, cost tracker, LLM adapters, parser, fix prompt, git ops, transcript writer |
| 2b Classic loop | `0d4eb04` | AnnealResult, anneal_classic orchestrator, oscillation detection, CLI |
| 3a OpenRouter pivot | `4312ddb` | openrouter.py, `--tier {cheap,balanced,premium}`, `--provider`, cost table |
| 3b1 Adversarial primitives | `ea6e3b3` | Attack/AttackResult, sandboxed python_test_runner, Red/Blue/Judge agents |
| 3b2 Adversarial loop + CLI | `154de51` | anneal_adversarial, 5 termination paths, adversarial subcommand |
| 4a Canary fixtures | `0de223a` | 12 planted_bugs + 36 perturbations + 8 clean_diffs |
| 4b Canary runner + CLI | `8157f71` | canary/runner.py, CLI canary subcommand, 13 runner tests |

## Tier presets

| Tier | Auditor / Fixer / Red / Blue | Judge | Provider |
|---|---|---|---|
| `cheap` | `google/gemini-2.5-flash` | `google/gemini-2.5-flash` | OpenRouter (all) |
| `balanced` (default) | `claude-haiku-4-5-20251001` | `google/gemini-2.5-flash` | Anthropic direct + OpenRouter |
| `premium` | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` | Anthropic direct |
| `ultra` | `claude-opus-4-7` | `claude-sonnet-4-6` | Anthropic direct |
| `cheap-gemini` | `gemini-2.0-flash` | `gemini-2.0-flash` | Gemini direct (no OpenRouter) |

Default `--max-cost-usd`: $1.00 (canary suite uses $10).

## Next steps for the user

### 1. Validate real-API path via cheap-gemini (T1.1 unblocked)

OpenRouter balance is $0 and no ANTHROPIC_API_KEY; the Gemini-direct path is the current unblocked live-fire route.

```bash
# 1. Install the gemini extra
pip install -e ".[gemini]"

# 2. Add to .env
GEMINI_API_KEY=<your key from aistudio.google.com/app/apikey>

# 3. Run a cheap canary subset (~$0.10–0.30)
anneal canary --subset planted --tier cheap-gemini --max-cost-usd 1
```

Triage `.canary/<timestamp>/canary_report.json`:
- All 12 planted_bugs caught → cheap-gemini becomes validated default for canary
- Many missed → bring failing fixtures to next session for prompt tuning

### 2. SWE-Bench Lite (T2.9 — parked)

Parked because the estimated run cost (~$20) exceeded the $5 session budget. Re-fund OpenRouter or Anthropic, then:
```bash
anneal swe-bench --tier balanced --max-cost-usd 10
```

### 3. Adversarial determinism gap (T4.14 partial)

T4.14 patched deterministic temperature + seed control into the **classic loop only**. `loop_adversarial` Red/Blue/Judge paths are still non-deterministic. If reproducible adversarial replays matter, add `--deterministic` support to `loop_adversarial` in a follow-up session.

### 4. Phase 5 — AM replay (deferred)

`anneal replay-am --commit cc4fca1 --repo /path/to/antigravity` — walk the AM Round 8 audit commit (14 fixes) through the classic loop and compare findings to the historical commit message. Budget ~$0.50. Still on the roadmap, not yet implemented.

## Critical constraints

- **AM is FROZEN.** Never edit `execution/infrastructure/api-proxy/`, `website/`, `website-dashboard/`, `directives/gtm_client_workflows/accessory_masters_*`, `config/accessory_masters*`, or any AM-coupled path.
- **No AM client keys.** Anneal uses only personal keys.
- **Anneal repo is public at https://github.com/dmazumdar186/anneal.** Ask before pushing — do not auto-push.

## How to run

```powershell
cd C:\Users\deban\dev\anneal
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q   # 136 tests
.\.venv\Scripts\anneal.exe --help
```

Key CLI flags added this session:
- `--audit-samples N`, `--vote-threshold F` — multi-sample voting auditor
- `--judge-samples N`, `--judge-vote-threshold F`, `--no-parallel-judge`, `--judge-max-workers N` — VotingJudge control
- `--deterministic`, `--seed N` — deterministic replay (classic loop only)
- `--interactive` — human-in-the-loop pause at failure modes
- `--tier cheap-gemini` — Gemini-direct tier (no OpenRouter dependency)
- `suppressions list|add|remove` — manage persistent finding suppressions

## Working-style preferences

- Terse responses. Skip trailing summaries.
- Sub-agent budget: ~3-4 min, ~6-8 files max. Force incremental commits.
- Opus 4.7 for orchestration; Sonnet for sub-agent implementation.
- Plan mode + ExitPlanMode for non-trivial builds.
- Cost transparency first.
