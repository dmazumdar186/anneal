"""Subprocess isolation: cwd=worktree, timeout-capped, env-stripped.

NOT a security sandbox in the Docker/VM sense — documented limitation.
v2 will use Docker-based isolation. See plan §Risks item 5.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


# Keys that must always be present on Windows for Python / pytest to run at all.
_WINDOWS_REQUIRED = {"SYSTEMROOT", "PATH"}


@dataclass
class TestRunResult:
    """Result of running a sandboxed subprocess (typically a pytest file).

    Attributes:
        failed: True when the test suite reported failures (attack landed).
            For pytest: exit code != 0.  For missing files: False (attack did
            not land — Red failed to write the file).
        exit_code: Raw process exit code, or -1 for pre-launch errors.
        stdout: Captured standard output (UTF-8, errors replaced).
        stderr: Captured standard error (UTF-8, errors replaced).
        timed_out: True when the process was killed due to timeout.
    """

    failed: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


class SandboxedSubprocess:
    """Context manager that runs a command in an isolated subprocess.

    The child process receives **only** the environment variables listed in
    ``env_passthrough`` plus the mandatory Windows keys ``SYSTEMROOT`` and
    ``PATH`` (needed for Python to locate the stdlib and DLLs).  Everything
    else — including ``ANTHROPIC_API_KEY``, ``OPENROUTER_API_KEY``, and any
    other secret — is stripped.

    Args:
        cmd: Command + arguments list (e.g. ``[sys.executable, "-m", "pytest", ...]``).
        cwd: Working directory for the child process (normally the git worktree).
        timeout: Seconds before the process is forcibly killed.  Default 30.
        env_passthrough: Names of environment variables to forward to the child.
            ``SYSTEMROOT`` and ``PATH`` are always included regardless of this list.
    """

    def __init__(
        self,
        cmd: list[str],
        cwd: Path,
        timeout: float = 30.0,
        env_passthrough: list[str] = (),
    ) -> None:
        self._cmd = cmd
        self._cwd = cwd
        self._timeout = timeout
        self._env_passthrough = list(env_passthrough)
        self._proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> "SandboxedSubprocess":
        import os

        allowed = set(self._env_passthrough) | _WINDOWS_REQUIRED
        child_env = {k: v for k, v in os.environ.items() if k in allowed}

        self._proc = subprocess.Popen(
            self._cmd,
            cwd=self._cwd,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return self

    def __exit__(self, *_: object) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def wait(self) -> TestRunResult:
        """Block until the process finishes (or timeout fires) and return the result.

        Returns:
            TestRunResult populated from the process exit code and output streams.
        """
        assert self._proc is not None, "Must be used as a context manager"
        timed_out = False
        try:
            stdout_b, stderr_b = self._proc.communicate(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._proc.kill()
            stdout_b, stderr_b = self._proc.communicate()

        exit_code = self._proc.returncode if not timed_out else -1
        return TestRunResult(
            failed=not timed_out and exit_code != 0,
            exit_code=exit_code,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            timed_out=timed_out,
        )


def run_subprocess(
    cmd: list[str],
    cwd: Path,
    timeout: float = 30.0,
    env_passthrough: list[str] = (),
) -> TestRunResult:
    """Synchronous wrapper around SandboxedSubprocess.

    Runs ``cmd`` in ``cwd`` with an env-stripped child process, waits for
    completion (or timeout), and returns a :class:`TestRunResult`.

    Args:
        cmd: Command and argument list.
        cwd: Working directory for the child.
        timeout: Seconds before the process is killed.
        env_passthrough: Env var names to forward (always includes SYSTEMROOT/PATH).

    Returns:
        TestRunResult with failed/exit_code/stdout/stderr/timed_out populated.
    """
    with SandboxedSubprocess(cmd, cwd, timeout=timeout, env_passthrough=env_passthrough) as s:
        return s.wait()
