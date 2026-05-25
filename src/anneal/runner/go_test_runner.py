"""Runs Red's generated Go test files inside a sandboxed subprocess.

Uses ``go test -json`` for machine-readable output. Falls back gracefully
if the ``go`` binary is not installed.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from anneal.runner.sandbox import TestRunResult, run_subprocess

_log = logging.getLogger(__name__)

# Env vars forwarded to the go child. No API keys, no secrets.
_GO_ENV_PASSTHROUGH = ["SYSTEMROOT", "PATH", "GOPATH", "GOROOT", "HOME", "USERPROFILE"]


class GoTestRunner:
    """Run Go test files using ``go test -json`` in an env-stripped subprocess.

    Args:
        go_path: Path to the ``go`` binary. Defaults to searching PATH.
    """

    def __init__(self, go_path: str | None = None) -> None:
        self._go_path = go_path or "go"

    def _go_available(self) -> bool:
        """Return True if the go binary is found on PATH (or at go_path)."""
        if self._go_path != "go":
            import os
            return os.path.isfile(self._go_path)
        return shutil.which("go") is not None

    def run(
        self,
        worktree: Path,
        test_file: Path | str,
        timeout_s: int = 30,
    ) -> TestRunResult:
        """Run Go tests for the package containing ``test_file``.

        Derives the package directory from the parent of ``test_file`` and runs
        ``go test -json ./...`` relative to that directory.

        Args:
            worktree: Absolute path to the git worktree root.
            test_file: Path to the Go test file (absolute or relative to worktree).
                The package dir is derived as the parent of this file.
            timeout_s: Seconds before the child process is killed.

        Returns:
            TestRunResult where:
            - failed=True  → one or more tests failed (attack landed).
            - failed=False → all tests passed or graceful error.
            - exit_code=-1 → go binary not installed or pre-launch error.
        """
        if not self._go_available():
            return TestRunResult(
                failed=False,
                exit_code=-1,
                stdout="",
                stderr="go binary not installed",
                timed_out=False,
            )

        # Resolve and validate test_file stays inside worktree (path traversal guard)
        test_path = Path(test_file)
        resolved = (test_path if test_path.is_absolute() else (worktree / test_path)).resolve()
        if not str(resolved).startswith(str(worktree.resolve())):
            raise ValueError(f"test_file {test_file!r} escapes worktree boundary")
        pkg_dir = resolved.parent

        cmd = [self._go_path, "test", "-json", "./..."]

        result = run_subprocess(
            cmd,
            cwd=pkg_dir,
            timeout=float(timeout_s),
            env_passthrough=_GO_ENV_PASSTHROUGH,
        )

        # Parse line-delimited JSON events
        passed = self._parse_output(result.stdout, result.exit_code)

        return TestRunResult(
            failed=not passed,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
        )

    def _parse_output(self, stdout: str, exit_code: int) -> bool:
        """Parse ``go test -json`` line-delimited output.

        ``go test -json`` emits one JSON object per event line. We look for
        any top-level test event with ``"Action": "fail"``; if found → failed.
        If no events are parseable, falls back to ``exit_code == 0``.

        Returns:
            True if all tests passed, False if any test failed.
        """
        if not stdout.strip():
            return exit_code == 0

        found_any = False
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(event, dict):
                continue

            found_any = True
            action = event.get("Action")
            test_name = event.get("Test")  # present only on per-test events

            # A top-level package "fail" — the whole package failed
            if action == "fail" and test_name is None:
                return False

            # A per-test "fail" event
            if action == "fail" and test_name is not None:
                return False

        if not found_any:
            # No parseable events — trust exit code
            return exit_code == 0

        # No fail events seen → all passed
        return True
