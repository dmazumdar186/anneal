"""Runs Red's generated pytest files inside a sandboxed subprocess."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestRunResult:
    """Result of running a single pytest file."""

    failed: bool
    passed: int
    errors: int
    stderr: str
    stdout: str
    timed_out: bool


def run_python_test(
    worktree: Path,
    test_path: str,
    timeout: int = 30,
    allow_network: bool = False,
) -> TestRunResult:
    """Execute a pytest file in the worktree sandbox and return structured results."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
