"""Unit tests for JavaScriptTestRunner.

Tests (all use monkeypatched subprocess — no real npx invocation):
1. Vitest JSON output with all tests passing → TestResult.failed = False
2. Vitest JSON output with 1 failing test → TestResult.failed = True
3. npx not on PATH → TestResult(failed=False, exit_code=-1), no exception
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anneal.runner.javascript_test_runner import JavaScriptTestRunner
from anneal.runner.sandbox import TestRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vitest_json(num_failed: int) -> str:
    """Return a minimal vitest --reporter=json payload."""
    return json.dumps({
        "numTotalTests": 3,
        "numPassedTests": 3 - num_failed,
        "numFailedTests": num_failed,
        "numPendingTests": 0,
        "success": num_failed == 0,
        "testResults": [],
    })


def _make_passing_result(stdout: str) -> TestRunResult:
    return TestRunResult(
        failed=False,
        exit_code=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
    )


def _make_failing_result(stdout: str) -> TestRunResult:
    return TestRunResult(
        failed=True,
        exit_code=1,
        stdout=stdout,
        stderr="",
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# 1. All tests pass
# ---------------------------------------------------------------------------

def test_passing_vitest_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked subprocess returns vitest JSON with 0 failures → failed=False."""
    import anneal.runner.javascript_test_runner as mod

    passing_result = _make_passing_result(_vitest_json(num_failed=0))
    monkeypatch.setattr(mod, "run_subprocess", lambda *a, **kw: passing_result)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/npx")

    runner = JavaScriptTestRunner(framework="vitest")
    result = runner.run(tmp_path, "src/__tests__/foo.test.ts")

    assert result.failed is False
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 2. One test fails
# ---------------------------------------------------------------------------

def test_failing_vitest_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked subprocess returns vitest JSON with 1 failure → failed=True."""
    import anneal.runner.javascript_test_runner as mod

    failing_result = _make_failing_result(_vitest_json(num_failed=1))
    monkeypatch.setattr(mod, "run_subprocess", lambda *a, **kw: failing_result)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/npx")

    runner = JavaScriptTestRunner(framework="vitest")
    result = runner.run(tmp_path, "src/__tests__/foo.test.ts")

    assert result.failed is True


# ---------------------------------------------------------------------------
# 3. npx not installed — graceful, no exception
# ---------------------------------------------------------------------------

def test_npx_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When npx is absent, returns failed=False, exit_code=-1, no exception."""
    import anneal.runner.javascript_test_runner as mod

    monkeypatch.setattr(mod.shutil, "which", lambda name: None)

    runner = JavaScriptTestRunner(framework="vitest")
    result = runner.run(tmp_path, "src/__tests__/foo.test.ts")

    assert result.failed is False
    assert result.exit_code == -1
    assert "not installed" in result.stderr
