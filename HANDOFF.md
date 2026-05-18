# Resume anneal — session handoff

I'm continuing work on **anneal**, a personal Python project. The prior session is done; everything below is what you need to pick up.

## What anneal is

A Python CLI + library that hardens code diffs through iterative LLM-driven loops. Two modes:
- **Classic** (`anneal <ref>`): auditor LLM finds issues → fixer LLM patches → re-audit → loop until N consecutive clean rounds.
- **Adversarial** (`anneal adversarial <ref>`): **Red vs Blue.** Red attacks (writes failing pytest files OR makes claims verified by a Judge LLM); Blue hardens. Loop until Red comes up empty for N rounds.

Public artifact + portfolio piece for a client named Bryce. Narrative ties back to a recently-shipped client project (Accessory Masters / AM) where I ran 16 audit rounds by hand using the same pattern.

## Where things live

- **Anneal repo:** `C:\Users\deban\dev\anneal\` — fresh git repo, outside OneDrive. **Pushed to https://github.com/dmazumdar186/anneal (public).** `origin/master` tracks remote.
- **Plan file (READ THIS FIRST):** `C:\Users\deban\.claude\plans\new-project-eager-hopcroft.md` — full architecture, CLI surface, tier presets, cost budget, risks, verification plan.
- **AntiGravity workspace:** `c:\Users\deban\OneDrive\Documents\AntiGravity Project Space` — the AM client repo, **FROZEN**. Read-only context only. See CLAUDE.local.md for lockdown rules.

## What's done — 27 commits, 73 unit tests passing

| Phase | Final SHA | What landed |
|---|---|---|
| 1 Scaffold | `558b474` | 81-file skeleton, pyproject.toml, .env.example |
| 2a Foundation | `d131d27` | config (AM-key guard), cost tracker, LLM adapters, pipeline-auditor parser, fix prompt, git worktree/patch ops, transcript writer |
| 2b Classic loop | `0d4eb04` | AnnealResult, anneal_classic orchestrator, oscillation detection, CLI classic subcommand, 20+ tests |
| 3a OpenRouter pivot | `4312ddb` | Deleted openai.py, added openrouter.py, `--tier {cheap,balanced,premium}`, `--provider` flag, new cost table, default model = Haiku 4.5, `--max-cost-usd` default 5→1 |
| 3b1 Adversarial primitives | `ea6e3b3` | Attack/AttackResult, sandboxed python_test_runner (env-strip + timeout), Red/Blue/Judge agents + prompts |
| 3b2 Adversarial loop + CLI | `154de51` | anneal_adversarial with 5 termination paths (clean / blue_cannot_defend / patch_conflict / max_rounds / budget), CLI adversarial subcommand, test-path security check |
| 4a Canary fixtures | `0de223a` | 108 files: 12 planted_bugs + 36 perturbations (3 variants each) + 8 clean_diffs |
| 4b Canary runner + CLI | `8157f71` | canary/runner.py (fixture discovery, difflib diff synthesis, regex-match catch logic, per-fixture transcripts, aggregate report), CLI canary subcommand, 12 runner tests + 1 CLI smoke |
| Handoff | (this commit) | HANDOFF.md |

All 73 unit tests use `DeterministicMockLLM` — **zero real API calls so far.** AntiGravity workspace clean throughout.

## Tier presets (resolved by `--tier`)

| Tier | Auditor / Fixer / Red / Blue | Judge | Provider |
|---|---|---|---|
| cheap | `google/gemini-2.5-flash` | `google/gemini-2.5-flash` | OpenRouter for all |
| balanced (current default) | `claude-haiku-4-5-20251001` | `google/gemini-2.5-flash` | Anthropic direct + OpenRouter |
| premium | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` | Anthropic direct |

Default `--max-cost-usd`: $1.00 (canary suite uses $10).

## What's next

### Phase 4c — MY TURN (PENDING — I haven't done this yet)

Before any more code, I need to:

1. **Provision OpenRouter key only.** Sign up at openrouter.ai/keys, add $5 (minimum top-up). Drop into `C:\Users\deban\dev\anneal\.env` as `OPENROUTER_API_KEY=sk-or-...`. **Do NOT provision an Anthropic key separately** — credits don't refund, and OpenRouter routes to Anthropic models too with ~5% markup. One key = one billing surface.
2. **Run a minimal cheap-tier canary first** (~$0.20-0.40, validates plumbing):
   ```powershell
   cd C:\Users\deban\dev\anneal
   .\.venv\Scripts\anneal.exe canary --subset planted --tier cheap --max-cost-usd 1
   ```
3. **Triage the result** at `.canary/<timestamp>/canary_report.json`:
   - All 12 planted_bugs caught → cheap tier becomes new default; finish canary (`--subset perturb`, `--subset clean`) at cheap tier, total <$1.
   - Most caught but a few missed → bump to `--tier balanced --provider openrouter` (Haiku via OpenRouter, still one key, ~$3-5 for full canary).
   - Many missed → bring failing fixtures to next session for prompt/fixture tuning before more spend.

I will tell you the report results when I have them.

### After 4c — Phase 5: AM-replay

`src/anneal/replay/am.py` + `anneal replay-am --commit cc4fca1` subcommand. Target commit: `cc4fca1` (Round 8 deep audit, 14 fixes on AM). Walk: `git worktree add <tempdir> cc4fca1^` against the AntiGravity repo (read-only), run anneal classic, compare findings to historical commit message. Integration smoke must assert AntiGravity `git status` stays clean. Budget: `--max-cost-usd 2`, expected ~$0.50.

### Phase 6 — Demos + README + Claude Code skill wrapper

`examples/synthetic_buggy/`, `examples/adversarial_demo/`, README with tier table + hero demo blocks + canary results, `.claude/skills/anneal/SKILL.md`, record demo GIF. Expected spend: $3-5.

## Critical constraints (do not violate)

- **AM is FROZEN.** Never edit `execution/infrastructure/api-proxy/`, `website/`, `website-dashboard/`, `directives/gtm_client_workflows/accessory_masters_*`, `config/accessory_masters*`, or any AM-coupled path. Read-only access to AM git history is OK (for replay-am).
- **No AM client keys.** Anneal uses ONLY my personal keys (OpenRouter for now).
- **No deploys to client cloud.** No `wrangler deploy`, no `vercel deploy`, no touching the AM Cloudflare or Vercel accounts.
- **Anneal repo is public at https://github.com/dmazumdar186/anneal.** Ask before pushing any new commits — don't auto-push after every commit.

## Working-style preferences (in CLAUDE.local.md already)

- Terse responses. Skip trailing summaries.
- Sub-agent reliable budget: ~3-4 min of actual work, ~6-8 files modified max. Force incremental commits in agent prompts. Split big phases (2a/2b, 3b1/3b2).
- Opus 4.7 for main orchestration; Sonnet for sub-agent implementation and exploration.
- Batch AskUserQuestion to the 4-question limit.
- Plan mode + ExitPlanMode for any non-trivial build.
- Cost transparency first when real money is involved.

## How to pick up

1. Read `C:\Users\deban\.claude\plans\new-project-eager-hopcroft.md` (Canary suite + Model strategy sections especially).
2. Verify state with these read-only checks:
   ```powershell
   git -C C:\Users\deban\dev\anneal log --oneline -10
   git -C "C:\Users\deban\OneDrive\Documents\AntiGravity Project Space" status
   cd C:\Users\deban\dev\anneal
   .\.venv\Scripts\python.exe -m pytest tests/unit/ -q
   ```
   Expect: 10 commits visible (latest = handoff commit), AntiGravity unchanged from baseline, 73 tests passing.
3. Ask me: did I provision the OpenRouter key and run the cheap-tier canary subset? If yes, I'll paste the report. If no, walk me through it (refer to "Phase 4c — MY TURN" above).
4. From there: triage Phase 4c → Phase 5 (AM-replay) → Phase 6 (demos + README).

Pick up from here.
