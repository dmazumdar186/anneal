"""Unit tests for PipelineAuditor response parsing: schema validation and AuditReport construction."""

from __future__ import annotations

from anneal.audit.pipeline_auditor import parse_audit_markdown


def test_parse_pass_no_findings() -> None:
    """PASS verdict + no findings + 'None detected' silent drops → empty lists."""
    md = (
        "## Audit Report: test\n\n"
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
    report = parse_audit_markdown(md, tokens_used=200)

    assert report.verdict == "PASS"
    assert report.findings == []
    assert report.silent_drops == []
    assert report.summary == "All checks passed."
    assert report.raw_markdown == md


def test_parse_fail_three_findings() -> None:
    """FAIL with HIGH/MEDIUM/LOW findings all parsed with correct fields."""
    md = (
        "**Verdict:** FAIL\n\n"
        "### Issues Found\n"
        "- [Severity: HIGH] SQL injection in query builder\n"
        "  Impact: Attacker can exfiltrate entire database.\n"
        "  Recommended fix: Use parameterised queries.\n"
        "- [Severity: MEDIUM] Off-by-one in pagination\n"
        "  Impact: Last page is skipped.\n"
        "  Recommended fix: Change range(n) to range(n+1).\n"
        "- [Severity: LOW] Missing docstring on public method\n"
        "  Impact: Reduced maintainability.\n"
        "  Recommended fix: Add a docstring.\n"
        "\n"
        "### Silent Drops\n"
        "None detected\n\n"
        "### Logic Disagreements\n"
        "None detected\n\n"
        "### Summary\n"
        "Three issues found.\n"
    )
    report = parse_audit_markdown(md, tokens_used=1500)

    assert report.verdict == "FAIL"
    assert len(report.findings) == 3

    high = report.findings[0]
    assert high.severity == "HIGH"
    assert "SQL injection" in high.summary
    assert "exfiltrate" in high.impact
    assert "parameterised" in high.recommended_fix

    med = report.findings[1]
    assert med.severity == "MEDIUM"
    assert "Off-by-one" in med.summary

    low = report.findings[2]
    assert low.severity == "LOW"
    assert "docstring" in low.summary

    assert report.tokens_used == 1500


def test_parse_degenerate_no_headings() -> None:
    """A response with no headings at all: verdict defaults to FAIL, lists empty, raw_markdown set."""
    md = "Something went wrong, no structured output here."
    report = parse_audit_markdown(md, tokens_used=50)

    assert report.verdict == "FAIL"
    assert report.findings == []
    assert report.silent_drops == []
    assert report.logic_disagreements == []
    assert report.raw_markdown == md
