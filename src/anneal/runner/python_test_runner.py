"""Runs Red's generated pytest files inside a sandboxed subprocess.

Uses sys.executable so the same Python / venv that anneal is running under
is used to execute the generated test file.  The child process receives only
``SYSTEMROOT``, ``PATH``, and ``PYTHONPATH`` — no secrets are forwarded.
"""

from __future__ import annotations

import sys
from pathlib import Path

from anneal.adversarial.base import Attack
from anneal.runner.sandbox import TestRunResult, run_subprocess

# Env vars forwarded to the pytest child.  No API keys, no secrets.
_PYTEST_ENV_PASSTHROUGH = ["SYSTEMROOT", "PATH", "PYTHONPATH"]


def run_python_test(
    worktree: Path,
    test_path: str,
    timeout: float = 30.0,
) -> TestRunResult:
    """Execute a single pytest file inside the worktree sandbox.

    Uses ``sys.executable`` (the current Python interpreter / venv) so that
    the test can import ``anneal`` and any other packages already installed.

    The child process receives **only** ``SYSTEMROOT``, ``PATH``, and
    ``PYTHONPATH`` — API keys and other secrets are stripped.

    Args:
        worktree: Absolute path to the git worktree root.
        test_path: Relative path (from ``worktree``) to the pytest file to run.
        timeout: Seconds before the process is killed.  Default 30.

    Returns:
        TestRunResult where:
        - ``failed=True``  → test suite failed (attack landed).
        - ``failed=False`` → test suite passed OR the file was not found.
        - ``timed_out=True`` → process killed after ``timeout`` seconds.

    Notes:
        If the test file does not exist (Red was supposed to write it but did
        not), the function returns ``failed=False`` with exit_code=-1 and a
        ``stderr`` message containing "not found".  This counts as
        attack-did-not-land.
    """
    abs_test_path = worktree / test_path
    if not abs_test_path.exists():
        return TestRunResult(
            failed=False,
            exit_code=-1,
            stdout="",
            stderr=f"test file not found: {test_path}",
            timed_out=False,
        )

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(abs_test_path),
        "-x",
        "--tb=short",
        "-q",
    ]
    return run_subprocess(
        cmd,
        cwd=worktree,
        timeout=timeout,
        env_passthrough=_PYTEST_ENV_PASSTHROUGH,
    )


def _security_check_test_path(worktree: Path, test_path: str) -> Path:
    """Verify test_path resolves inside worktree (no path traversal escape).

    Args:
        worktree: Absolute path to the git worktree root.
        test_path: Relative path as provided by Red (may contain ../ sequences).

    Returns:
        Absolute resolved path inside worktree.

    Raises:
        ValueError: If the resolved path escapes the worktree root.
    """
    worktree_resolved = worktree.resolve()
    candidate = (worktree_resolved / test_path).resolve()
    try:
        candidate.relative_to(worktree_resolved)
    except ValueError:
        raise ValueError(
            f"Security check failed: test_path '{test_path}' resolves to '{candidate}', "
            f"which is outside the worktree '{worktree_resolved}'. Attack skipped."
        )
    return candidate


def write_test_file(worktree: Path, attack: Attack) -> Path:
    """Write Red's test body to the worktree at the path specified in the attack.

    Creates all intermediate parent directories as needed.
    Performs a path-traversal security check before writing.

    Args:
        worktree: Absolute path to the git worktree root.
        attack: An Attack with ``kind="test"``, non-None ``test_path``, and
            non-None ``test_body``.

    Returns:
        Absolute path to the written test file.

    Raises:
        ValueError: If ``attack.kind != "test"``, ``attack.test_body`` is None,
            or ``attack.test_path`` escapes the worktree root (path traversal).
    """
    if attack.kind != "test":
        raise ValueError(
            f"write_test_file requires kind='test', got kind='{attack.kind}'"
        )
    if attack.test_body is None:
        raise ValueError("write_test_file requires attack.test_body to be non-None")
    if attack.test_path is None:
        raise ValueError("write_test_file requires attack.test_path to be non-None")

    # Security check: reject paths that would escape the worktree
    abs_path = _security_check_test_path(worktree, attack.test_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(attack.test_body, encoding="utf-8")
    return abs_path
