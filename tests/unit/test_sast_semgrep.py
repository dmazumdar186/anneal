"""Unit tests for SemgrepRunner.

Tests:
1. Empty semgrep output → no findings returned.
2. Two findings parsed correctly: one ERROR (high) and one WARNING (medium).
3. semgrep not installed (shutil.which returns None) → empty list, no exception.
4. Non-supported extensions are filtered out before semgrep is invoked (subprocess never called).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anneal.sast.semgrep_runner import SemgrepRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_semgrep_result(
    check_id: str,
    message: str,
    path: str = "src/foo.py",
    line: int = 10,
    severity: str = "ERROR",
) -> dict:
    """Build a minimal semgrep JSON result dict (mirrors real semgrep --json output)."""
    return {
        "check_id": check_id,
        "path": path,
        "start": {"line": line, "col": 1},
        "end": {"line": line, "col": 20},
        "extra": {
            "severity": severity,
            "message": message,
            "lines": "",
            "metadata": {},
        },
    }


def _fake_run_returning(results: list[dict], exit_code: int = 0):
    """Return a factory that creates a fake subprocess.run result."""
    def _inner(*args, **kwargs):
        mock = MagicMock()
        mock.returncode = exit_code
        mock.stdout = json.dumps({"results": results, "errors": [], "version": "1.0.0"}).encode()
        mock.stderr = b""
        return mock
    return _inner


# ---------------------------------------------------------------------------
# 1. Empty output → no findings
# ---------------------------------------------------------------------------

def test_empty_semgrep_output_yields_no_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_run_returning([], exit_code=0))

    runner = SemgrepRunner(semgrep_path="/fake/semgrep")
    findings = runner.run(tmp_path, ["src/foo.py"])

    assert findings == []


# ---------------------------------------------------------------------------
# 2. Two findings parsed correctly (ERROR → high, WARNING → medium)
# ---------------------------------------------------------------------------

def test_two_findings_parsed_correctly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [
        _make_semgrep_result(
            "python.lang.security.audit.exec-use",
            "Use of exec() is a security risk",
            path="src/shell.py",
            line=55,
            severity="ERROR",
        ),
        _make_semgrep_result(
            "python.lang.correctness.unused-variable",
            "Variable assigned but never used",
            path="src/utils.py",
            line=12,
            severity="WARNING",
        ),
    ]
    monkeypatch.setattr(subprocess, "run", _fake_run_returning(results, exit_code=0))

    runner = SemgrepRunner(semgrep_path="/fake/semgrep")
    findings = runner.run(tmp_path, ["src/shell.py", "src/utils.py"])

    assert len(findings) == 2

    exec_finding = next(f for f in findings if "exec" in f.rule_id)
    assert exec_finding.severity == "high"
    assert exec_finding.file == "src/shell.py"
    assert exec_finding.line == 55
    assert exec_finding.tool == "semgrep"
    assert "exec" in exec_finding.message.lower()

    unused_finding = next(f for f in findings if "unused" in f.rule_id)
    assert unused_finding.severity == "medium"
    assert unused_finding.file == "src/utils.py"
    assert unused_finding.line == 12
    assert unused_finding.tool == "semgrep"


# ---------------------------------------------------------------------------
# 3. semgrep not installed → empty list, no exception
# ---------------------------------------------------------------------------

def test_semgrep_not_installed_returns_empty_no_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate shutil.which("semgrep") returning None (semgrep absent from PATH).
    import anneal.sast.semgrep_runner as semgrep_mod
    monkeypatch.setattr(semgrep_mod.shutil, "which", lambda _name: None)

    # SemgrepRunner() with no explicit path will call shutil.which at construction time.
    runner = SemgrepRunner()
    findings = runner.run(tmp_path, ["src/foo.py"])

    assert findings == []


# ---------------------------------------------------------------------------
# 4. Non-supported extensions filtered before subprocess is called
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 5. HOME/USERPROFILE fallback injected when env is empty
# ---------------------------------------------------------------------------

def test_semgrep_runner_sets_home_fallback_when_unset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HOME and USERPROFILE must be set in the child env even when _build_child_env()
    returns a dict that contains neither (sandboxed/restricted subprocess contexts)."""
    captured_env: dict = {}

    def _capture_env(*args, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = json.dumps({"results": [], "errors": [], "version": "1.0.0"}).encode()
        mock.stderr = b""
        return mock

    # Strip HOME/USERPROFILE from os.environ so _build_child_env() returns neither.
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(subprocess, "run", _capture_env)

    runner = SemgrepRunner(semgrep_path="/fake/semgrep")
    runner.run(tmp_path, ["src/foo.py"])

    assert "HOME" in captured_env, "HOME must be injected into child env when unset"


# ---------------------------------------------------------------------------
# 4. Non-supported extensions filtered before subprocess is called
# ---------------------------------------------------------------------------

def test_non_supported_extensions_filtered_before_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subprocess must NOT be called when changed_files has no supported extensions."""
    called: list[bool] = []

    def _should_not_be_called(*args, **kwargs):
        called.append(True)
        raise AssertionError("subprocess.run should not be called for unsupported files")

    monkeypatch.setattr(subprocess, "run", _should_not_be_called)

    runner = SemgrepRunner(semgrep_path="/fake/semgrep")
    findings = runner.run(tmp_path, ["README.md", "Makefile", "src/style.css", "data.json"])

    assert findings == []
    assert called == [], "subprocess.run was invoked despite no supported files"
