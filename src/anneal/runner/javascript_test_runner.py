"""Runs Red's generated vitest/jest test files inside a sandboxed subprocess.

Supports vitest and jest frameworks. Auto-detects from package.json when
framework="auto". Falls back gracefully if node/npx is not installed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Literal

from anneal.runner.sandbox import TestRunResult, run_subprocess

_log = logging.getLogger(__name__)

# Env vars forwarded to the node child. No API keys, no secrets.
_NODE_ENV_PASSTHROUGH = ["SYSTEMROOT", "PATH", "NODE_PATH"]


class JavaScriptTestRunner:
    """Run vitest or jest test files in an env-stripped subprocess.

    Args:
        framework: "vitest", "jest", or "auto". Auto-detects from package.json.
        node_path: Path to the node binary. Defaults to searching PATH.
    """

    def __init__(
        self,
        framework: Literal["vitest", "jest", "auto"] = "auto",
        node_path: str | None = None,
    ) -> None:
        self._framework = framework
        self._node_path = node_path

    def _npx_available(self) -> bool:
        """Return True if npx is found on PATH."""
        return shutil.which("npx") is not None

    def _detect_framework(self, worktree: Path) -> Literal["vitest", "jest"] | None:
        """Detect test framework from package.json in the worktree root.

        Prefers vitest if both are present. Returns None if neither is found.
        """
        pkg_json = worktree / "package.json"
        if not pkg_json.exists():
            _log.debug("No package.json in %s — defaulting to vitest", worktree)
            return "vitest"

        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _log.warning("Could not parse package.json: %s — defaulting to vitest", exc)
            return "vitest"

        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        has_vitest = "vitest" in all_deps
        has_jest = "jest" in all_deps

        if has_vitest:
            return "vitest"
        if has_jest:
            return "jest"

        _log.debug("Neither vitest nor jest in package.json — defaulting to vitest")
        return "vitest"

    def run(
        self,
        worktree: Path,
        test_file: Path | str,
        timeout_s: int = 30,
    ) -> TestRunResult:
        """Run a single JS/TS test file and return the result.

        Args:
            worktree: Absolute path to the git worktree root.
            test_file: Path to the test file (absolute or relative to worktree).
            timeout_s: Seconds before the child process is killed.

        Returns:
            TestRunResult where:
            - failed=True  → one or more tests failed (attack landed).
            - failed=False → all tests passed, file not found, or graceful error.
            - exit_code=-1 → npx/node not installed or pre-launch error.
        """
        if not self._npx_available():
            return TestRunResult(
                failed=False,
                exit_code=-1,
                stdout="",
                stderr="node/npx not installed",
                timed_out=False,
            )

        # Resolve framework
        if self._framework == "auto":
            framework = self._detect_framework(worktree)
        else:
            framework = self._framework

        # Resolve and validate test_file stays inside worktree (path traversal guard)
        _tf = Path(test_file)
        resolved = (_tf if _tf.is_absolute() else (worktree / _tf)).resolve()
        if not str(resolved).startswith(str(worktree.resolve())):
            raise ValueError(f"test_file {test_file!r} escapes worktree boundary")
        test_path_str = str(resolved)

        start = time.monotonic()

        if framework == "vitest":
            cmd = ["npx", "vitest", "run", test_path_str, "--reporter=json"]
        else:
            cmd = ["npx", "jest", test_path_str, "--json"]

        result = run_subprocess(
            cmd,
            cwd=worktree,
            timeout=float(timeout_s),
            env_passthrough=_NODE_ENV_PASSTHROUGH,
        )

        duration_s = time.monotonic() - start

        # Parse JSON output to determine pass/fail
        passed = self._parse_output(framework, result.stdout, result.exit_code)

        return TestRunResult(
            failed=not passed,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
        )

    def _parse_output(
        self,
        framework: Literal["vitest", "jest"],
        stdout: str,
        exit_code: int,
    ) -> bool:
        """Parse framework JSON output.  Returns True if all tests passed.

        Uses the ``numFailedTests == 0`` heuristic for both vitest and jest
        JSON reporters — they share the same top-level shape for this field.
        Falls back to exit_code == 0 if JSON parsing fails.
        """
        if not stdout.strip():
            return exit_code == 0

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # Output may contain non-JSON preamble; try to find the JSON object
            start_idx = stdout.find("{")
            if start_idx == -1:
                _log.debug("No JSON object found in %s output — using exit_code", framework)
                return exit_code == 0
            try:
                data = json.loads(stdout[start_idx:])
            except json.JSONDecodeError:
                _log.debug("Could not parse %s JSON output — using exit_code", framework)
                return exit_code == 0

        if not isinstance(data, dict):
            return exit_code == 0

        # Both vitest --reporter=json and jest --json expose numFailedTests
        num_failed = data.get("numFailedTests")
        if num_failed is not None:
            return int(num_failed) == 0

        # Fallback: check success field (jest) or status field
        success = data.get("success")
        if success is not None:
            return bool(success)

        return exit_code == 0
