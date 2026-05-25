"""Unit tests for GoTestRunner.

Tests (all use monkeypatched subprocess — no real go invocation):
1. go test -json output with all PASS events → TestResult.failed = False
2. go test -json output with a FAIL event → TestResult.failed = True
3. go binary not installed → TestResult(failed=False, exit_code=-1), no exception
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anneal.runner.go_test_runner import GoTestRunner
from anneal.runner.sandbox import TestRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _go_events(*actions: str) -> str:
    """Build a newline-delimited go test -json event stream.

    Each action string becomes: {"Action": "<action>", "Test": "TestFoo", ...}
    A final package-level event is appended ("pass" or "fail" depending on
    whether any per-test "fail" was present).
    """
    lines = []
    has_fail = any(a == "fail" for a in actions)
    for action in actions:
        lines.append(json.dumps({
            "Time": "2024-01-01T00:00:00Z",
            "Action": action,
            "Package": "example.com/pkg",
            "Test": "TestFoo",
        }))
    # Package-level summary (no "Test" key)
    pkg_action = "fail" if has_fail else "pass"
    lines.append(json.dumps({
        "Time": "2024-01-01T00:00:00Z",
        "Action": pkg_action,
        "Package": "example.com/pkg",
    }))
    return "\n".join(lines)


def _result(stdout: str, exit_code: int) -> TestRunResult:
    return TestRunResult(
        failed=exit_code != 0,
        exit_code=exit_code,
        stdout=stdout,
        stderr="",
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# 1. All tests pass
# ---------------------------------------------------------------------------

def test_all_pass_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """go test -json output with run/pass events → failed=False."""
    import anneal.runner.go_test_runner as mod

    events = _go_events("run", "pass")
    monkeypatch.setattr(mod, "run_subprocess", lambda *a, **kw: _result(events, 0))
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/local/go/bin/go")

    runner = GoTestRunner()
    # Point test_file at a file inside tmp_path so parent dir = tmp_path
    test_file = tmp_path / "pkg_test.go"
    test_file.touch()
    result = runner.run(tmp_path, test_file)

    assert result.failed is False
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 2. One test fails
# ---------------------------------------------------------------------------

def test_fail_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """go test -json output with a fail event → failed=True."""
    import anneal.runner.go_test_runner as mod

    events = _go_events("run", "fail")
    monkeypatch.setattr(mod, "run_subprocess", lambda *a, **kw: _result(events, 1))
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/local/go/bin/go")

    runner = GoTestRunner()
    test_file = tmp_path / "pkg_test.go"
    test_file.touch()
    result = runner.run(tmp_path, test_file)

    assert result.failed is True


# ---------------------------------------------------------------------------
# 3. go binary not installed — graceful, no exception
# ---------------------------------------------------------------------------

def test_go_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When go is absent, returns failed=False, exit_code=-1, no exception."""
    import anneal.runner.go_test_runner as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: None)

    runner = GoTestRunner()
    result = runner.run(tmp_path, tmp_path / "pkg_test.go")

    assert result.failed is False
    assert result.exit_code == -1
    assert "not installed" in result.stderr
