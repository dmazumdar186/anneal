"""Unit tests for anneal.canary.runner — all using DeterministicMockLLM.

No real LLM calls.  A minimal fixture tree is built in tmp_path for each test
that needs it; the full 108-fixture suite is NOT exercised here (that is Phase 4c).

Test inventory:
    1.  test_planted_bug_caught_when_finding_matches_regex
    2.  test_planted_bug_missed_when_finding_doesnt_match
    3.  test_planted_bug_missed_when_verdict_pass_with_no_findings
    4.  test_clean_diff_passes_when_verdict_pass_no_findings
    5.  test_clean_diff_false_positive_when_findings_present
    6.  test_perturbation_pass_rate_threshold_met
    7.  test_perturbation_pass_rate_below_threshold
    8.  test_per_fixture_transcripts_written
    9.  test_aggregate_report_written
    10. test_subset_planted_skips_other_categories
    11. test_auditor_exception_recorded_as_error
    12. test_diff_synthesis_planted_uses_unified_diff_format
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anneal.audit.base import AuditReport, Finding
from anneal.audit.pipeline_auditor import PipelineAuditor, parse_audit_markdown
from anneal.canary.runner import (
    CanaryReport,
    FixtureResult,
    _synthesize_diff_planted,
    run_canary,
)
from anneal.llm.mock import DeterministicMockLLM


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_mock_audit_response(
    verdict: str,
    findings: list[tuple[str, str]],  # (severity, summary)
) -> str:
    """Build a minimal pipeline-auditor markdown blob that the parser will accept.

    Args:
        verdict: "PASS", "FAIL", or "WARNINGS".
        findings: List of (severity, summary) tuples.

    Returns:
        A markdown string the pipeline_auditor parser can parse into an AuditReport.
    """
    lines = [f"**Verdict:** {verdict}", "", "### Issues Found", ""]
    for severity, summary in findings:
        lines.append(f"- [Severity: {severity}] {summary}")
        lines.append("  Impact: test impact")
        lines.append("  Recommended fix: test fix")
        lines.append("")
    lines += [
        "### Silent Drops",
        "None detected",
        "",
        "### Logic Disagreements",
        "None detected",
        "",
        "### Summary",
        "Test summary.",
    ]
    return "\n".join(lines)


def _make_planted_fixture(
    base: Path,
    name: str,
    regex: str,
    code: str = 'x = 1\nfor i in range(1, n):\n    pass\n',
) -> Path:
    """Create a planted_bugs/<name>/ subdir with before.py and meta.json."""
    d = base / "planted_bugs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "before.py").write_text(code, encoding="utf-8")
    (d / "after.py").write_text("x = 1\nfor i in range(n):\n    pass\n", encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({
            "name": name,
            "category": "planted_bug",
            "severity": "MEDIUM",
            "bug_type": "test",
            "expected_finding_signature_regex": regex,
        }),
        encoding="utf-8",
    )
    return d


def _make_perturbation_fixture(
    base: Path,
    name: str,
    regex: str,
    num_variants: int = 3,
) -> Path:
    """Create a perturbations/<name>/ subdir with meta.json and N variant files."""
    d = base / "perturbations" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(
        json.dumps({
            "name": name,
            "category": "perturbation",
            "expected_finding_signature_regex": regex,
        }),
        encoding="utf-8",
    )
    for i in range(1, num_variants + 1):
        code = f"# variant {i}\nfor x in range(1, n):\n    pass\n"
        (d / f"v{i}_variant.py").write_text(code, encoding="utf-8")
    return d


def _make_clean_fixture(
    base: Path,
    name: str,
    before_code: str = "x = 1\n",
    after_code: str = "x = 1  # comment\n",
) -> Path:
    """Create a clean_diffs/<name>/ subdir with before.py, after.py, meta.json."""
    d = base / "clean_diffs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "before.py").write_text(before_code, encoding="utf-8")
    (d / "after.py").write_text(after_code, encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({
            "name": name,
            "category": "clean_diff",
            "expected_verdict": "PASS",
            "expected_findings_count": 0,
        }),
        encoding="utf-8",
    )
    return d


def _auditor_from_responses(responses: list[str | tuple[str, int]]) -> PipelineAuditor:
    """Build a PipelineAuditor backed by a DeterministicMockLLM."""
    mock_llm = DeterministicMockLLM(responses)
    return PipelineAuditor(mock_llm)


# ── Test 1: planted bug caught when finding matches regex ──────────────────────


def test_planted_bug_caught_when_finding_matches_regex(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one")

    response = _make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one in loop bound")])
    auditor = _auditor_from_responses([response])

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="planted",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.planted_bugs["total"] == 1
    assert report.planted_bugs["caught_round_1"] == 1
    assert report.planted_bugs["rate"] == 1.0
    assert report.overall_pass is True


# ── Test 2: planted bug missed when finding doesn't match regex ────────────────


def test_planted_bug_missed_when_finding_doesnt_match(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one")

    response = _make_mock_audit_response("FAIL", [("LOW", "unrelated style issue")])
    auditor = _auditor_from_responses([response])

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="planted",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.planted_bugs["total"] == 1
    assert report.planted_bugs["caught_round_1"] == 0
    assert report.planted_bugs["rate"] == 0.0
    assert report.overall_pass is False


# ── Test 3: planted bug missed when verdict PASS with no findings ──────────────


def test_planted_bug_missed_when_verdict_pass_with_no_findings(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one")

    response = _make_mock_audit_response("PASS", [])
    auditor = _auditor_from_responses([response])

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="planted",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.planted_bugs["caught_round_1"] == 0
    assert report.overall_pass is False


# ── Test 4: clean diff passes when verdict PASS, no findings ──────────────────


def test_clean_diff_passes_when_verdict_pass_no_findings(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_clean_fixture(fixtures, "refactor_only")

    response = _make_mock_audit_response("PASS", [])
    auditor = _auditor_from_responses([response])

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="clean",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.clean_diffs["total"] == 1
    assert report.clean_diffs["false_positives"] == 0
    assert report.clean_diffs["rate"] == 1.0
    assert report.overall_pass is True


# ── Test 5: clean diff false-positive when findings present ───────────────────


def test_clean_diff_false_positive_when_findings_present(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_clean_fixture(fixtures, "refactor_only")

    response = _make_mock_audit_response("FAIL", [("HIGH", "spurious finding")])
    auditor = _auditor_from_responses([response])

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="clean",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.clean_diffs["false_positives"] == 1
    assert report.overall_pass is False


# ── Test 6: perturbation pass rate threshold met (3/3 = 100%) ─────────────────


def test_perturbation_pass_rate_threshold_met(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_perturbation_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one", num_variants=3)

    responses = [
        _make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one detected")]),
        _make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one in loop")]),
        _make_mock_audit_response("FAIL", [("MEDIUM", "off by one error")]),
    ]
    auditor = _auditor_from_responses(responses)

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="perturb",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.perturbations["total"] == 3
    assert report.perturbations["caught"] == 3
    assert report.perturbations["rate"] == 1.0
    assert report.overall_pass is True


# ── Test 7: perturbation pass rate below 90% threshold (8/10 = 80%) ──────────


def test_perturbation_pass_rate_below_threshold(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    # Need 10 variants; use two groups of 5 since helper caps at the variant count
    _make_perturbation_fixture(fixtures, "bug_a", r"off[- ]?by[- ]?one", num_variants=5)
    _make_perturbation_fixture(fixtures, "bug_b", r"off[- ]?by[- ]?one", num_variants=5)

    # 8 catch, 2 miss → 80% < 90%
    responses = []
    for i in range(10):
        if i < 8:
            responses.append(_make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one")]))
        else:
            responses.append(_make_mock_audit_response("FAIL", [("LOW", "unrelated issue")]))
    auditor = _auditor_from_responses(responses)

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="perturb",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.perturbations["total"] == 10
    assert report.perturbations["caught"] == 8
    assert report.perturbations["rate"] == pytest.approx(0.8)
    assert report.overall_pass is False


# ── Test 8: per-fixture transcripts written ───────────────────────────────────


def test_per_fixture_transcripts_written(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one")
    _make_clean_fixture(fixtures, "refactor_only")

    responses = [
        _make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one in loop")]),
        _make_mock_audit_response("PASS", []),
    ]
    auditor = _auditor_from_responses(responses)
    log_dir = tmp_path / ".canary"

    run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="all",
        log_dir=log_dir,
        save_transcripts=True,
    )

    for fixture_slug in ("planted_bugs_off_by_one", "clean_diffs_refactor_only"):
        out_dir = log_dir / fixture_slug
        assert (out_dir / "audit.md").exists(), f"audit.md missing for {fixture_slug}"
        assert (out_dir / "audit.json").exists(), f"audit.json missing for {fixture_slug}"
        assert (out_dir / "result.json").exists(), f"result.json missing for {fixture_slug}"


# ── Test 9: aggregate report written ─────────────────────────────────────────


def test_aggregate_report_written(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one")

    response = _make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one in loop")])
    auditor = _auditor_from_responses([response])
    log_dir = tmp_path / ".canary"

    run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="planted",
        log_dir=log_dir,
        save_transcripts=True,
    )

    report_path = log_dir / "canary_report.json"
    assert report_path.exists(), "canary_report.json was not written"

    data = json.loads(report_path.read_text(encoding="utf-8"))
    # Check required top-level keys
    for key in ("ran_at", "tier", "models", "planted_bugs", "perturbations", "clean_diffs",
                 "total_cost_usd", "overall_pass"):
        assert key in data, f"Missing key '{key}' in canary_report.json"

    # Check planted_bugs sub-shape
    pb = data["planted_bugs"]
    assert "total" in pb
    assert "caught_round_1" in pb
    assert "rate" in pb
    assert "details" in pb


# ── Test 10: subset=planted skips other categories ────────────────────────────


def test_subset_planted_skips_other_categories(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "off_by_one", r"off[- ]?by[- ]?one")
    _make_perturbation_fixture(fixtures, "perturb_bug", r"off[- ]?by[- ]?one", num_variants=2)
    _make_clean_fixture(fixtures, "clean_refactor")

    response = _make_mock_audit_response("FAIL", [("MEDIUM", "off-by-one")])
    auditor = _auditor_from_responses([response])  # Only 1 response needed for 1 planted

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="planted",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    assert report.planted_bugs["total"] == 1
    assert report.perturbations["total"] == 0
    assert report.clean_diffs["total"] == 0


# ── Test 11: auditor exception recorded as error ──────────────────────────────


def test_auditor_exception_recorded_as_error(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    _make_planted_fixture(fixtures, "bug_a", r"off[- ]?by[- ]?one")
    _make_planted_fixture(fixtures, "bug_b", r"null[- ]?deref")

    # bug_a's auditor call raises; bug_b succeeds
    from anneal.llm.base import LLMError

    class _ErrorThenOkLLM:
        def __init__(self) -> None:
            self._call = 0

        def complete(self, system: str, user: str, response_format: str = "text") -> tuple[str, int]:
            self._call += 1
            if self._call == 1:
                raise LLMError("simulated timeout")
            return _make_mock_audit_response("FAIL", [("HIGH", "null dereference found")]), 500

    auditor = PipelineAuditor(_ErrorThenOkLLM())  # type: ignore[arg-type]

    report = run_canary(
        auditor=auditor,
        fixtures_dir=fixtures,
        subset="planted",
        log_dir=tmp_path / ".canary",
        save_transcripts=False,
    )

    # Total = 2, exactly 1 errored
    details = report.planted_bugs["details"]
    assert len(details) == 2
    errored = [d for d in details if d["error"]]
    ok = [d for d in details if not d["error"]]
    assert len(errored) == 1
    assert len(ok) == 1
    # The error fixture is not caught
    assert not errored[0]["caught"]
    # The ok fixture is caught (null dereference regex matched)
    assert ok[0]["caught"]
    # Run continues despite error → overall_pass is False (1/2 = 50% < 100%)
    assert report.overall_pass is False


# ── Test 12: diff synthesis uses unified-diff format ─────────────────────────


def test_diff_synthesis_planted_uses_unified_diff_format(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\nfor i in range(1, n):\n    pass\n", encoding="utf-8")

    diff = _synthesize_diff_planted(sample)

    assert "--- /dev/null" in diff, "Expected '--- /dev/null' in unified diff header"
    assert "+++ b/" in diff, "Expected '+++ b/<filename>' in unified diff header"
    assert "@@" in diff, "Expected '@@ ... @@' hunk header in unified diff"
    # Every content line should be prefixed with '+'
    content_lines = [l for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    assert len(content_lines) > 0, "No '+' content lines found in diff"
