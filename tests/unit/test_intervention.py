"""Unit tests for InterventionPrompter (T4.17).

All tests use injected input_fn/output_fn so no stdin/stdout is touched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from anneal.intervention.pause import Intervention, InterventionPrompter
from anneal.audit.base import AuditReport, Finding


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_report(summaries: list[str]) -> AuditReport:
    """Build a minimal AuditReport with one Finding per summary string."""
    findings = [
        Finding(
            severity="HIGH",
            summary=s,
            file="foo.py",
            impact="bad",
            recommended_fix="fix it",
        )
        for s in summaries
    ]
    return AuditReport(
        verdict="FAIL",
        findings=findings,
        silent_drops=[],
        logic_disagreements=[],
        summary="",
        raw_markdown="",
        tokens_used=0,
    )


def _prompter(inputs: list[str]) -> InterventionPrompter:
    """Build an InterventionPrompter whose input_fn returns items from *inputs* in order."""
    it = iter(inputs)
    return InterventionPrompter(
        input_fn=lambda _prompt: next(it),
        output_fn=lambda *_args, **_kwargs: None,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_prompt_at_oscillation_abort():
    """Option 1 → ABORT with empty payload."""
    report = _make_report(["SQL injection in login handler"])
    prompter = _prompter(["1"])  # user picks "Abort"
    choice, payload = prompter.prompt_at_oscillation(report, current_round=3)
    assert choice == Intervention.ABORT
    assert payload == {}


def test_prompt_at_oscillation_dismiss():
    """Option 2 → DISMISS_FINDING with a fingerprint in the payload."""
    report = _make_report(["SQL injection in login handler"])
    prompter = _prompter(["2"])  # user picks "Dismiss finding" (only one finding, no sub-prompt)
    choice, payload = prompter.prompt_at_oscillation(report, current_round=3)
    assert choice == Intervention.DISMISS_FINDING
    assert "fingerprint" in payload
    # fingerprint must be a 16-hex-char string (from finding_fingerprint)
    fp = payload["fingerprint"]
    assert isinstance(fp, str)
    assert len(fp) == 16
    assert all(c in "0123456789abcdef" for c in fp)


def test_prompt_at_budget_raise():
    """Option 2 + extra amount → RAISE_BUDGET with new_max_usd = current_max + extra."""
    current_cost = 0.95
    max_cost = 1.00
    extra = 5.00
    prompter = _prompter(["2", str(extra)])  # "Raise budget", then "5.0"
    choice, payload = prompter.prompt_at_budget(current_cost, max_cost)
    assert choice == Intervention.RAISE_BUDGET
    assert "new_max_usd" in payload
    assert abs(payload["new_max_usd"] - (max_cost + extra)) < 1e-9


def test_prompt_at_patch_conflict_abort():
    """Option 1 → ABORT with empty payload."""
    prompter = _prompter(["1"])  # user picks "Abort"
    choice, payload = prompter.prompt_at_patch_conflict(
        patch_excerpt="--- a/foo.py\n+++ b/foo.py\n@@...",
        conflict_files=["foo.py"],
    )
    assert choice == Intervention.ABORT
    assert payload == {}
