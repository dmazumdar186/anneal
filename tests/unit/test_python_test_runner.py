"""Unit tests for sandboxed python test runner and env-stripping.

Tests:
1. A passing pytest file yields failed=False, exit_code=0.
2. A failing pytest file yields failed=True, exit_code != 0.
3. A long-running pytest file is killed and timed_out=True.
4. The child env is stripped — FAKE_SECRET is not visible inside the subprocess.
5. A missing test file returns failed=False with stderr containing "not found".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from anneal.runner.python_test_runner import run_python_test


def _write(path: Path, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Passing test
# ---------------------------------------------------------------------------

def test_passing_test_yields_failed_false(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_pass.py"
    _write(test_file, "def test_ok():\n    assert 1 + 1 == 2\n")

    result = run_python_test(tmp_path, "tests/test_pass.py")

    assert result.failed is False
    assert result.exit_code == 0
    assert result.timed_out is False


# ---------------------------------------------------------------------------
# 2. Failing test
# ---------------------------------------------------------------------------

def test_failing_test_yields_failed_true(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_fail.py"
    _write(test_file, "def test_broken():\n    assert False\n")

    result = run_python_test(tmp_path, "tests/test_fail.py")

    assert result.failed is True
    assert result.exit_code != 0
    assert result.timed_out is False
    combined = result.stdout + result.stderr
    assert "FAILED" in combined or "assert" in combined.lower()


# ---------------------------------------------------------------------------
# 3. Timeout
# ---------------------------------------------------------------------------

def test_timeout_returns_timed_out_true(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_slow.py"
    _write(
        test_file,
        "import time\ndef test_slow():\n    time.sleep(60)\n",
    )

    result = run_python_test(tmp_path, "tests/test_slow.py", timeout=2.0)

    assert result.timed_out is True


# ---------------------------------------------------------------------------
# 4. Env stripping — secret must not leak into child
# ---------------------------------------------------------------------------

def test_env_strip_prevents_secret_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_SECRET", "leaky")

    test_file = tmp_path / "tests" / "test_env.py"
    _write(
        test_file,
        (
            "import os\n"
            "def test_secret_absent():\n"
            "    val = os.environ.get('FAKE_SECRET', 'absent')\n"
            "    print(f'SECRET_VALUE={val}')\n"
            "    assert val == 'absent', f'env leaked: {val}'\n"
        ),
    )

    result = run_python_test(tmp_path, "tests/test_env.py")

    # The test inside the subprocess asserts val == 'absent'.
    # If the env leaked, the subprocess test would fail and result.failed would be True.
    assert result.failed is False, (
        f"FAKE_SECRET leaked into child process.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "leaky" not in result.stdout
    assert "leaky" not in result.stderr


# ---------------------------------------------------------------------------
# 5. Missing test file
# ---------------------------------------------------------------------------

def test_missing_test_file_returns_failed_false(tmp_path: Path) -> None:
    result = run_python_test(tmp_path, "tests/red/nonexistent.py")

    assert result.failed is False
    assert result.exit_code == -1
    assert "not found" in result.stderr
