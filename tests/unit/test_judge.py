"""Unit tests for the Judge LLM — strict adversarial finding verification.

Phase 3b1 step 8.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anneal.adversarial.base import Attack, attack_fingerprint
from anneal.adversarial.judge import Judge
from anneal.llm.mock import DeterministicMockLLM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding_attack(claim: str = "Goal #2 has no metric.", severity: str = "HIGH") -> Attack:
    fp = attack_fingerprint("finding", ("docs/PRD.md",), f"{severity}|{claim}")
    return Attack(
        kind="finding",
        fingerprint=fp,
        target_files=("docs/PRD.md",),
        rationale="Without a metric this goal is unfalsifiable.",
        severity=severity,  # type: ignore[arg-type]
        claim=claim,
        evidence="PRD §3.2 lists Goal #2 with no measurable outcome.",
        expected="A quantitative target.",
        actual="Aspirational language, no numbers.",
    )


def _make_test_attack() -> Attack:
    fp = attack_fingerprint("test", ("src/foo.py",), "tests/red/test_attack_001.py")
    return Attack(
        kind="test",
        fingerprint=fp,
        target_files=("src/foo.py",),
        rationale="Off-by-one.",
        test_path="tests/red/test_attack_001.py",
        test_body="def test_off_by_one():\n    assert False\n",
    )


_DIFF = "--- a/docs/PRD.md\n+++ b/docs/PRD.md\n@@ -10,4 +10,6 @@\n+## Goal #2\n+Improve user satisfaction.\n"


# ---------------------------------------------------------------------------
# 1. Valid finding
# ---------------------------------------------------------------------------

def test_judge_valid_finding() -> None:
    response = '{"verdict": "valid", "rationale": "The diff adds \'## Goal #2 / Improve user satisfaction\' — no measurable target."}'
    llm = DeterministicMockLLM([response])
    judge = Judge(llm)

    output = judge.judge(_make_finding_attack(), _DIFF, Path("/fake/worktree"))

    assert output.verdict == "valid"
    assert "Goal #2" in output.rationale or "measurable" in output.rationale


# ---------------------------------------------------------------------------
# 2. Invalid finding
# ---------------------------------------------------------------------------

def test_judge_invalid_finding() -> None:
    response = '{"verdict": "invalid", "rationale": "The diff at line +14 adds NPS ≥ 50 — Red\'s claim is wrong."}'
    llm = DeterministicMockLLM([response])
    judge = Judge(llm)

    output = judge.judge(_make_finding_attack(), _DIFF, Path("/fake/worktree"))

    assert output.verdict == "invalid"


# ---------------------------------------------------------------------------
# 3. Calling judge() with kind=test raises ValueError
# ---------------------------------------------------------------------------

def test_judge_test_attack_raises() -> None:
    llm = DeterministicMockLLM([])
    judge = Judge(llm)

    with pytest.raises(ValueError, match="kind='finding'"):
        judge.judge(_make_test_attack(), _DIFF, Path("/fake/worktree"))


# ---------------------------------------------------------------------------
# 4. Malformed (non-JSON) response defaults to invalid
# ---------------------------------------------------------------------------

def test_judge_malformed_response_defaults_invalid() -> None:
    llm = DeterministicMockLLM(["garbage not json }{"])
    judge = Judge(llm)

    output = judge.judge(_make_finding_attack(), _DIFF, Path("/fake/worktree"))

    assert output.verdict == "invalid"
    assert "unparseable" in output.rationale
