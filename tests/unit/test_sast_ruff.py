"""Unit tests for RuffRunner and SAST base helpers.

Tests:
1. Empty ruff output → no findings returned.
2. Two findings parsed correctly: one S-class (high) and one F-class (low).
3. ruff not installed (shutil.which returns None) → empty list, no exception.
4. Non-Python files are filtered out before ruff is invoked (subprocess never called).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anneal.sast.base import SastFinding, format_findings_as_markdown
from anneal.sast.ruff_runner import RuffRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ruff_item(
    code: str,
    message: str,
    filename: str = "src/foo.py",
    row: int = 10,
) -> dict:
    """Build a minimal ruff JSON finding dict (mirrors real ruff output shape)."""
    return {
        "code": code,
        "message": message,
        "filename": filename,
        "location": {"row": row, "column": 1},
        "end_location": {"row": row, "column": 5},
        "url": f"https://docs.astral.sh/ruff/rules/{code}",
        "fix": None,
        "noqa_row": None,
    }


def _fake_run_returning(items: list[dict], exit_code: int = 0):
    """Return a factory that creates a fake subprocess.run result."""
    def _inner(*args, **kwargs):
        result = MagicMock()
        result.returncode = exit_code
        result.stdout = json.dumps(items).encode()
        result.stderr = b""
        return result
    return _inner


# ---------------------------------------------------------------------------
# 1. Empty output → no findings
# ---------------------------------------------------------------------------

def test_empty_ruff_output_yields_no_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run_returning([], exit_code=0))

    runner = RuffRunner(ruff_path="/fake/ruff")
    findings = runner.run(tmp_path, ["src/foo.py"])

    assert findings == []


# ---------------------------------------------------------------------------
# 2. Two findings parsed correctly (S → high, F → low)
# ---------------------------------------------------------------------------

def test_two_findings_parsed_correctly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        _make_ruff_item("S101", "Use of `assert` detected", filename="src/auth.py", row=42),
        _make_ruff_item("F401", "`os` imported but unused", filename="src/utils.py", row=3),
    ]
    monkeypatch.setattr(subprocess, "run", _fake_run_returning(items, exit_code=1))

    runner = RuffRunner(ruff_path="/fake/ruff")
    findings = runner.run(tmp_path, ["src/auth.py", "src/utils.py"])

    assert len(findings) == 2

    security_finding = next(f for f in findings if f.rule_id == "S101")
    assert security_finding.severity == "high"
    assert security_finding.file == "src/auth.py"
    assert security_finding.line == 42
    assert security_finding.tool == "ruff"
    assert "assert" in security_finding.message

    unused_finding = next(f for f in findings if f.rule_id == "F401")
    assert unused_finding.severity == "low"
    assert unused_finding.file == "src/utils.py"
    assert unused_finding.line == 3
    assert unused_finding.tool == "ruff"


# ---------------------------------------------------------------------------
# 3. ruff not installed → empty list, no exception
# ---------------------------------------------------------------------------

def test_ruff_not_installed_returns_empty_no_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate shutil.which("ruff") returning None (ruff absent from PATH).
    import anneal.sast.ruff_runner as ruff_mod
    monkeypatch.setattr(ruff_mod.shutil, "which", lambda _name: None)

    # RuffRunner() with no explicit path will call shutil.which at construction time.
    runner = RuffRunner()
    findings = runner.run(tmp_path, ["src/foo.py"])

    assert findings == []


# ---------------------------------------------------------------------------
# 4. Non-Python files filtered before subprocess is called
# ---------------------------------------------------------------------------

def test_non_python_files_filtered_before_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subprocess must NOT be called when changed_files has no .py entries."""
    called: list[bool] = []

    def _should_not_be_called(*args, **kwargs):
        called.append(True)
        raise AssertionError("subprocess.run should not be called for non-Python files")

    monkeypatch.setattr(subprocess, "run", _should_not_be_called)

    runner = RuffRunner(ruff_path="/fake/ruff")
    findings = runner.run(tmp_path, ["README.md", "Makefile", "src/style.css"])

    assert findings == []
    assert called == [], "subprocess.run was invoked despite no Python files"


# ---------------------------------------------------------------------------
# Bonus: format_findings_as_markdown helper
# ---------------------------------------------------------------------------

def test_format_findings_as_markdown_empty() -> None:
    assert format_findings_as_markdown([]) == ""


def test_format_findings_as_markdown_renders_correctly() -> None:
    findings = [
        SastFinding(
            severity="high",
            file="src/auth.py",
            line=12,
            rule_id="S101",
            message="Use of `assert` detected",
            tool="ruff",
        ),
    ]
    md = format_findings_as_markdown(findings)

    assert "## SAST Pre-pass Findings (1 issue)" in md
    assert "[high]" in md
    assert "src/auth.py:12" in md
    assert "S101" in md
    assert "ruff" in md
