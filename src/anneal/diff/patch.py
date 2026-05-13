"""Apply unified-diff patches to worktrees and record results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anneal.fix.base import Patch


@dataclass
class ApplyResult:
    """Outcome of applying a Patch to a worktree."""

    ok: bool
    conflict_files: list[str]
    message: str


def apply_patch(worktree_path: Path, patch: Patch) -> ApplyResult:
    """Apply patch.unified_diff to the worktree via `git apply`."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")


def apply_initial_diff(worktree_path: Path, diff_path: Path) -> ApplyResult:
    """Apply the initial input diff to the fresh worktree before loop starts."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
