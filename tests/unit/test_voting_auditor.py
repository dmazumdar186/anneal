"""Unit tests for VotingAuditor: consensus voting, verdict majority, and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anneal.audit.base import AuditReport, Finding, finding_fingerprint
from anneal.audit.voting import VotingAuditor


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_finding(severity: str = "HIGH", summary: str = "test finding", file: str = "") -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        summary=summary,
        file=file,
        impact="some impact",
        recommended_fix="fix it",
    )


def _make_report(
    verdict: str = "FAIL",
    findings: list[Finding] | None = None,
    tokens_used: int = 100,
) -> AuditReport:
    return AuditReport(
        verdict=verdict,  # type: ignore[arg-type]
        findings=findings or [],
        silent_drops=[],
        logic_disagreements=[],
        summary="test summary",
        raw_markdown="**Verdict:** FAIL\n### Issues Found\n### Summary\ntest summary",
        tokens_used=tokens_used,
    )


def _mock_auditor(*reports: AuditReport) -> MagicMock:
    """Build a mock Auditor that returns *reports in sequence on each audit() call."""
    m = MagicMock()
    m.audit.side_effect = list(reports)
    return m


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_single_sample_passthrough() -> None:
    """samples=1, threshold=1 → identical to calling base auditor once, all findings kept."""
    finding = _make_finding(summary="off-by-one in loop")
    base_report = _make_report(verdict="FAIL", findings=[finding], tokens_used=200)
    mock = _mock_auditor(base_report)

    voter = VotingAuditor(mock, samples=1, vote_threshold=1)
    result = voter.audit("diff text", Path("/repo"))

    mock.audit.assert_called_once()
    # With samples=1 the fast path returns the report unchanged
    assert result is base_report
    assert result.verdict == "FAIL"
    assert len(result.findings) == 1
    assert result.tokens_used == 200


def test_consensus_filtering() -> None:
    """samples=3, threshold=2: finding in 2/3 samples survives; finding in only 1 is dropped."""
    shared = _make_finding(summary="shared bug")          # appears in samples 1 & 2
    rare = _make_finding(summary="hallucinated finding")  # appears only in sample 3

    report1 = _make_report(verdict="FAIL", findings=[shared], tokens_used=100)
    report2 = _make_report(verdict="FAIL", findings=[shared], tokens_used=100)
    report3 = _make_report(verdict="FAIL", findings=[rare], tokens_used=100)

    mock = _mock_auditor(report1, report2, report3)
    voter = VotingAuditor(mock, samples=3, vote_threshold=2)
    result = voter.audit("diff", Path("/repo"))

    assert mock.audit.call_count == 3
    assert result.verdict == "FAIL"
    assert len(result.findings) == 1
    # The surviving finding is the shared one
    assert result.findings[0].summary == "shared bug"
    # Rare finding (only 1 vote) is dropped
    assert all(f.summary != "hallucinated finding" for f in result.findings)
    assert result.tokens_used == 300


def test_verdict_majority_fail() -> None:
    """2 of 3 samples return FAIL → merged verdict is FAIL."""
    finding = _make_finding(summary="real bug")
    report_fail1 = _make_report(verdict="FAIL", findings=[finding], tokens_used=100)
    report_fail2 = _make_report(verdict="FAIL", findings=[finding], tokens_used=100)
    report_pass = _make_report(verdict="PASS", findings=[], tokens_used=100)

    mock = _mock_auditor(report_fail1, report_fail2, report_pass)
    voter = VotingAuditor(mock, samples=3, vote_threshold=2)
    result = voter.audit("diff", Path("/repo"))

    assert result.verdict == "FAIL"
    # The shared finding appears in 2/3 samples and survives threshold=2
    assert len(result.findings) == 1


def test_validation_threshold_exceeds_samples() -> None:
    """vote_threshold > samples raises ValueError at construction time."""
    mock = MagicMock()
    with pytest.raises(ValueError, match="vote_threshold"):
        VotingAuditor(mock, samples=3, vote_threshold=4)


def test_parallel_execution_same_vote_totals() -> None:
    """Parallel sampling (N=3) produces the same vote totals as sequential execution.

    The VotingAuditor now runs samples in parallel via ThreadPoolExecutor.
    This test verifies that the consensus result is identical to what a
    sequential loop would produce: same surviving findings, same verdict,
    same token count.
    """
    shared = _make_finding(summary="shared bug")   # appears in samples 1 & 2
    rare = _make_finding(summary="rare bug")        # appears only in sample 3

    report1 = _make_report(verdict="FAIL", findings=[shared], tokens_used=100)
    report2 = _make_report(verdict="FAIL", findings=[shared], tokens_used=100)
    report3 = _make_report(verdict="WARNINGS", findings=[rare], tokens_used=100)

    # Use side_effect list — ThreadPoolExecutor calls audit() in any order, but
    # since the mock is shared, the 3 calls will consume the 3 reports in the
    # order they are dispatched.  The consensus (fingerprint counting) is
    # order-independent, so the outcome is deterministic regardless of
    # which thread grabs which report.
    mock = _mock_auditor(report1, report2, report3)

    voter = VotingAuditor(mock, samples=3, vote_threshold=2)
    result = voter.audit("diff", Path("/repo"))

    # All 3 samples must have been called
    assert mock.audit.call_count == 3

    # "shared bug" appears in 2/3 samples → survives threshold=2
    # "rare bug" appears in 1/3 samples → dropped
    assert len(result.findings) == 1
    assert result.findings[0].summary == "shared bug"

    # Verdict: 2× FAIL, 1× WARNINGS → majority is FAIL
    assert result.verdict == "FAIL"

    # Token sum unchanged
    assert result.tokens_used == 300
