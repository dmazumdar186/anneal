"""Subprocess isolation: cwd=worktree, timeout-capped, env-stripped."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubprocessResult:
    """Result of a sandboxed subprocess execution."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def run_sandboxed(
    cmd: list[str],
    cwd: Path,
    timeout_seconds: int = 30,
    allow_network: bool = False,
) -> SubprocessResult:
    """Run cmd in a restricted subprocess: env-stripped, cwd-locked, timeout-capped.

    Strips ANTHROPIC_API_KEY, OPENAI_API_KEY, and all other sensitive env vars.
    Not a security sandbox — documented limitation; v2 will use Docker.
    """
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
