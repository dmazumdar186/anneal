"""Integration test: classic loop threads prior_attempts through to round N+1's auditor.

Verifies the end-to-end "loop with memory" wiring:
  - Round 1: auditor receives NO prior_attempts block (cold start).
  - Round 2: auditor receives a prior_attempts block containing round-1's
    finding summary AND the fixer's rationale.
  - Round 3: prior_attempts grows monotonically (round-1 + round-2 both shown).

Uses a RecordingMockLLM (inline) so the test can inspect every user message
the auditor LLM saw.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from anneal.audit.pipeline_auditor import PipelineAuditor
from anneal.config import AnnealConfig
from anneal.fix.default_fixer import DefaultFixer
from anneal.llm.base import CacheUsage
from anneal.llm.mock import DeterministicMockLLM
from anneal.loop_classic import anneal_classic


# ── Recording LLM (inline; not added to production code) ──────────────────────


class RecordingMockLLM:
    """DeterministicMockLLM variant that records every (system, user) pair.

    Same response-queue contract as ``DeterministicMockLLM`` so it slots into
    existing helpers, but exposes ``calls`` for test assertions.
    """

    def __init__(self, responses: list[str]) -> None:
        self._queue: list[str] = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.last_cache_usage = CacheUsage()

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",  # noqa: ARG002
        *,
        temperature: float | None = None,  # noqa: ARG002
        seed: int | None = None,  # noqa: ARG002
    ) -> tuple[str, int]:
        if not self._queue:
            raise IndexError("RecordingMockLLM response queue exhausted")
        self.calls.append((system, user))
        return self._queue.pop(0), 1000


# ── Git fixture (mirrors test_loop_classic.py) ────────────────────────────────


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


def _init_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "test@anneal"], repo)
    _git(["config", "user.name", "Anneal Test"], repo)
    (repo / "hello.py").write_text('print("hello")\n', encoding="utf-8")
    _git(["add", "hello.py"], repo)
    _git(["commit", "-m", "initial commit"], repo)
    return repo


# ── Response helpers ──────────────────────────────────────────────────────────


def _pass_response() -> str:
    return (
        "**Verdict:** PASS\n\n"
        "### Issues Found\n"
        "None detected\n\n"
        "### Silent Drops\n"
        "None detected\n\n"
        "### Logic Disagreements\n"
        "None detected\n\n"
        "### Summary\n"
        "All checks passed.\n"
    )


def _fail_response(severity: str, summary: str) -> str:
    return (
        "**Verdict:** FAIL\n\n"
        "### Issues Found\n"
        f"- [Severity: {severity}] {summary}\n"
        "  Impact: Something bad could happen.\n"
        "  Recommended fix: Fix the issue.\n\n"
        "### Silent Drops\nNone detected\n\n"
        "### Logic Disagreements\nNone detected\n\n"
        "### Summary\n1 issue found.\n"
    )


def _patch_response(filename: str, rationale: str) -> str:
    """Fixer response: creates a new file. Rationale is embedded as a # comment
    inside the fenced diff so it ends up in Patch.rationale via DefaultFixer
    parsing."""
    return (
        "```diff\n"
        f"# rationale: {rationale}\n"
        "--- /dev/null\n"
        f"+++ b/{filename}\n"
        "@@ -0,0 +1,1 @@\n"
        "+# fix line\n"
        "\n"
        "```\n"
    )


# ── Test ──────────────────────────────────────────────────────────────────────


def test_round2_receives_round1_findings_and_rationale(tmp_path: Path) -> None:
    """The auditor at round 2 must see round-1's findings + fixer rationale."""
    repo = _init_repo(tmp_path)

    # Round 1: FAIL ("sql injection") → fixer applies a fix with a distinctive rationale.
    # Round 2: FAIL again ("xss") → fixer applies again. We assert round 2 sees round 1.
    # Round 3: PASS twice → converged.
    round1_summary = "sql injection in query builder XX1"
    round2_summary = "xss in user-controlled output YY2"
    round1_rationale = "MARK_R1_RATIONALE_switched_to_parameterised_queries"
    round2_rationale = "MARK_R2_RATIONALE_html_escaped_user_input"

    auditor_llm = RecordingMockLLM(
        [
            _fail_response("HIGH", round1_summary),  # round 1
            _fail_response("HIGH", round2_summary),  # round 2
            _pass_response(),                         # round 3
            _pass_response(),                         # round 4 (until_clean=2)
        ]
    )
    fixer_llm = DeterministicMockLLM(
        [
            _patch_response("fix_r1.py", round1_rationale),
            _patch_response("fix_r2.py", round2_rationale),
        ]
    )

    auditor = PipelineAuditor(auditor_llm)  # type: ignore[arg-type]
    fixer = DefaultFixer(fixer_llm)

    cfg = AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=10,
        until_clean=2,
        max_cost_usd=99.0,
        dry_run=False,
        no_worktree=False,
        diff_path=None,
        log_dir=tmp_path / "log",
        auditor=auditor,
        fixer=fixer,
        model="claude-haiku-4-5-20251001",
        sast_runners=[],  # disable SAST so the user_msg is easy to inspect
    )

    result = anneal_classic(cfg)
    assert result.converged is True, f"loop did not converge: {result.reason}"

    # 4 audit calls happened (one per round).
    assert len(auditor_llm.calls) == 4

    _sys, round1_user = auditor_llm.calls[0]
    _sys, round2_user = auditor_llm.calls[1]
    _sys, round3_user = auditor_llm.calls[2]

    # ── Round 1: cold start, NO loop memory ─────────────────────────────────
    assert "## Prior round attempts" not in round1_user
    assert round1_summary not in round1_user.split("```diff")[0]  # not in pre-diff context

    # ── Round 2: round-1's findings + rationale must appear ────────────────
    assert "## Prior round attempts (loop memory)" in round2_user
    assert "### Round 1" in round2_user
    assert round1_summary in round2_user
    assert round1_rationale in round2_user

    # ── Round 3: round-1 AND round-2 both present (history grows) ──────────
    assert "### Round 1" in round3_user
    assert "### Round 2" in round3_user
    assert round1_summary in round3_user
    assert round2_summary in round3_user
    assert round1_rationale in round3_user
    assert round2_rationale in round3_user


def test_round1_has_no_prior_attempts_block(tmp_path: Path) -> None:
    """Single-round PASS run: round-1 user message contains no loop-memory block."""
    repo = _init_repo(tmp_path)
    auditor_llm = RecordingMockLLM([_pass_response(), _pass_response()])

    auditor = PipelineAuditor(auditor_llm)  # type: ignore[arg-type]
    fixer = DefaultFixer(DeterministicMockLLM([]))

    cfg = AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=10,
        until_clean=2,
        max_cost_usd=99.0,
        dry_run=False,
        no_worktree=False,
        diff_path=None,
        log_dir=tmp_path / "log",
        auditor=auditor,
        fixer=fixer,
        model="claude-haiku-4-5-20251001",
        sast_runners=[],
    )
    result = anneal_classic(cfg)
    assert result.converged is True

    for _sys, user in auditor_llm.calls:
        assert "## Prior round attempts" not in user
