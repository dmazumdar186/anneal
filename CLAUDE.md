# CLAUDE.md — anneal

Developer guide for working inside the `anneal` repo.
Entry point for any AI environment (Claude Code, Cursor, Gemini, etc.).

---

## Architecture

anneal hardens code diffs through two orchestration modes:

**Classic mode** (`anneal classic` / `anneal HEAD`):
- A single **Auditor** LLM reads the diff and returns a list of findings.
- A **Fixer** LLM applies patches for each finding.
- The loop repeats until N consecutive clean rounds (default: 2).
- Optional **VotingAuditor** (`--audit-samples N`) runs multiple Auditor calls and takes majority consensus before passing findings to the Fixer.

**Adversarial mode** (`anneal adversarial HEAD`):
- **Red agents** (security-red, perf-red, logic-red + coordinator) attack the diff by writing failing tests or structured findings.
- **Blue agent** audits and fixes what Red surfaces.
- A **Judge** LLM (optionally a **VotingJudge** with `--judge-samples N`) declares convergence or requests another round.
- The loop terminates when Red comes up empty or the round cap is hit.

Both modes share: SAST pre-pass → repo-graph context injection → LLM loop → transcript + cost report.

---

## Entry points

```bash
# Install (editable)
pip install -e .
pip install -e ".[gemini]"   # adds google-genai for Gemini-direct path

# Classic mode
py -m anneal.cli classic <base-ref>          # e.g. HEAD~1
anneal HEAD                                  # shorthand via script entrypoint

# Adversarial mode
py -m anneal.cli adversarial <base-ref>
anneal adversarial HEAD

# Canary suite (planted-bug regression)
anneal canary --subset all

# Suppressions management
anneal suppressions list
anneal suppressions add "pattern to suppress"
anneal suppressions remove <id>
```

Confirmed from `pyproject.toml`: `anneal = "anneal.cli:main"`.

---

## Test command

```bash
pytest -q                       # all 136 unit tests (all mock-based, no API calls)
pytest -q -m "not slow"         # skip slow tests
pytest -q -m "not live_api"     # skip tests requiring ANTHROPIC_API_KEY
```

Tests live in `tests/`. All are mock-based; no real LLM calls by default.

---

## Tiers

| Tier | Auditor / Red / Blue | Judge | Provider | ~Cost/round |
|------|----------------------|-------|----------|-------------|
| `cheap` | `google/gemini-2.5-flash` | `google/gemini-2.5-flash` | OpenRouter | ~$0.01 |
| `balanced` (default) | `claude-haiku-4-5-20251001` | `google/gemini-2.5-flash` | Anthropic + OpenRouter | ~$0.05 |
| `premium` | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` | Anthropic | ~$0.20 |
| `ultra` | `claude-opus-4-7` | `claude-sonnet-4-6` | Anthropic | ~$1.00 |
| `cheap-gemini` | `gemini-2.0-flash` | `gemini-2.0-flash` | Gemini direct | ~$0.01 |

`cheap-gemini` requires only `GEMINI_API_KEY` — no OpenRouter balance needed.
Use it when OpenRouter credits are $0 (see T1.1 note in workspace notes).

---

## Key files

| File | Purpose |
|------|---------|
| `src/anneal/cli.py` | CLI entry point, arg parsing, mode dispatch |
| `src/anneal/audit/base.py` | `Auditor` protocol + `Finding` / `AuditReport` dataclasses |
| `src/anneal/audit/pipeline_auditor.py` | LLM auditor implementation; parses structured markdown output |
| `src/anneal/audit/voting.py` | `VotingAuditor` — multi-sample consensus |
| `src/anneal/fix/base.py` | `Fixer` protocol |
| `src/anneal/fix/default_fixer.py` | Default patch-applying fixer |
| `src/anneal/adversarial/red.py` | Red agents (security/perf/logic + coordinator) |
| `src/anneal/adversarial/blue.py` | Blue agent (audit + fix) |
| `src/anneal/adversarial/judge.py` | Judge LLM + VotingJudge |
| `src/anneal/sast/ruff_runner.py` | Ruff SAST pre-pass (subprocess-encoding-safe) |
| `src/anneal/sast/semgrep_runner.py` | Semgrep SAST pre-pass (subprocess-encoding-safe) |
| `src/anneal/cost.py` | Cache-aware pricing (4 token types per Claude model) |
| `src/anneal/runner/sandbox.py` | Env-stripped subprocess runner |
| `src/anneal/suppressions/store.py` | SQLite-backed suppression store; threading.Lock on writes |
| `src/anneal/llm/gemini.py` | Gemini-direct adapter (`google-genai`) |
| `src/anneal/llm/openrouter.py` | OpenRouter adapter (`openai` SDK) |
| `src/anneal/llm/claude.py` | Anthropic-direct adapter (`anthropic` SDK) |
| `src/anneal/audit/prompts/pipeline_auditor.md` | Static auditor system prompt (loaded at runtime) |

**Prompt files** (static system prompts, loaded at runtime, not re-derived each call):
- `src/anneal/adversarial/prompts/red.md`, `blue.md`, `judge.md`
- `src/anneal/adversarial/prompts/security_red.md`, `perf_red.md`, `logic_red.md`
- `src/anneal/fix/prompts/default_fixer.md`, `test_fixer.md`, `security_fixer.md`, `refactor_fixer.md`

---

## Windows quirks — hardened patterns (canonical references)

These patterns are already applied throughout this repo. Treat them as the reference implementation for any new code added:

1. **Subprocess encoding** — `subprocess.run(..., encoding="utf-8", errors="replace")` on every call with `text=True` or `capture_output=True`. See `sast/ruff_runner.py` and `sast/semgrep_runner.py`. Windows cp1252 crashes on bytes ≥ 0x80.

2. **Threading locks** — `threading.Lock()` guards all shared mutable state inside `ThreadPoolExecutor`. See `suppressions/store.py`. GIL does NOT protect `+=` or concurrent directory writes.

3. **LLM-supplied path validation** — any filename from LLM output is `.resolve()`ed and checked `resolved.is_relative_to(boundary)` before filesystem use. See `runner/sandbox.py` and JS/Go test runners.

4. **Cache-aware Claude pricing** — `cost.py` carries 4 entries per Claude model: `input`, `cache_read` (0.1×), `cache_write` (1.25×), `output`. Flat-rate estimates over-count 5–10× under prompt caching.

5. **Never `except Exception: pass`** — every bare swallow has a log line + comment. Silent swallows are what this tool exists to catch.

---

## How to add a new SAST rule

1. Add the rule to Semgrep (`src/anneal/sast/semgrep_runner.py`) or as a custom Ruff check.
2. If it's a project-specific bug class (not a generic lint), document it in `src/anneal/audit/prompts/pipeline_auditor.md` under a `## Known bug classes` section so the LLM auditor doesn't re-derive it each round.
3. Add a canary fixture: `src/anneal/canary/fixtures/planted_bugs/<rule_name>/before.py` and `after.py`.
4. Run `anneal canary --subset all` to verify detection.

---

## How to add a new tier

1. Add a row to the `TIERS` dict in `src/anneal/llm/factory.py` (or equivalent registry).
2. Pick an `auditor_model`, `fixer_model`, `judge_model`, and `provider`.
3. Add pricing to `cost.py` (4 entries for Claude models, flat rate for OpenRouter).
4. Update the tiers table in `README.md`.
5. Add a test in `tests/` to verify the new tier resolves correctly (mock-based).

---

## Skill reference

The workspace-level skill lives at:
`C:\Users\deban\OneDrive\Documents\AntiGravity Project Space\.claude\skills\anneal\SKILL.md`

Invoke with `/anneal` or by saying "anneal this diff". The skill reads this CLAUDE.md for architecture context — no need to re-state it in the prompt.
