"""Unit tests for anneal.suppressions.store and loop_classic._apply_suppressions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from anneal.audit.base import AuditReport, Finding, finding_fingerprint
from anneal.loop_classic import _apply_suppressions
from anneal.suppressions.store import SuppressionStore


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_finding(summary: str, severity: str = "HIGH", file: str = "src/foo.py") -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        summary=summary,
        file=file,
        impact="test impact",
        recommended_fix="test fix",
    )


def _make_report(findings: list[Finding], verdict: str = "FAIL") -> AuditReport:
    return AuditReport(
        verdict=verdict,  # type: ignore[arg-type]
        findings=findings,
        silent_drops=[],
        logic_disagreements=[],
        summary="test summary",
        raw_markdown="## test",
        tokens_used=100,
    )


# ── SuppressionStore unit tests ────────────────────────────────────────────────


def test_add_then_is_suppressed_returns_true(tmp_path: Path) -> None:
    store_path = tmp_path / "suppressions.json"
    store = SuppressionStore(store_path)

    store.add("abcdef0123456789", "false positive — not a real bug")

    assert store.is_suppressed("abcdef0123456789") is True


def test_is_suppressed_unknown_fingerprint_returns_false(tmp_path: Path) -> None:
    store_path = tmp_path / "suppressions.json"
    store = SuppressionStore(store_path)

    assert store.is_suppressed("0000000000000000") is False


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    store_path = tmp_path / "nonexistent.json"
    store = SuppressionStore(store_path)

    assert store.list_all() == []


def test_load_malformed_json_returns_empty_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store_path = tmp_path / "suppressions.json"
    store_path.write_text("not { valid json !!!", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="anneal.suppressions.store"):
        store = SuppressionStore(store_path)

    assert store.list_all() == []
    assert any("could not parse" in rec.message for rec in caplog.records)


# ── _apply_suppressions integration test ──────────────────────────────────────


def test_apply_suppressions_drops_matching_findings_and_downgrades_verdict(
    tmp_path: Path,
) -> None:
    f1 = _make_finding("off-by-one in loop bound")
    f2 = _make_finding("unchecked None return", severity="CRITICAL")
    f3 = _make_finding("missing auth check", file="src/api.py")

    store_path = tmp_path / "suppressions.json"
    store = SuppressionStore(store_path)

    # Suppress all three findings
    for f in (f1, f2, f3):
        store.add(finding_fingerprint(f), "known false positive")

    report = _make_report([f1, f2, f3], verdict="FAIL")
    result = _apply_suppressions(report, store)

    assert result.findings == []
    assert result.verdict == "PASS"
    # Metadata preserved
    assert result.tokens_used == report.tokens_used
    assert result.raw_markdown == report.raw_markdown
