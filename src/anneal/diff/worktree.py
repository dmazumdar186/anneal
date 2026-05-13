"""Git worktree create, diff, commit, and cleanup — the only module that shells out to git."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Worktree:
    """Handle to a git worktree created for one anneal run."""

    path: Path
    repo: Path
    base_ref: str


def make_worktree(repo: Path, base_ref: str, dest: Path | None = None) -> Worktree:
    """Create a git worktree at base_ref and return a handle to it."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")


def git_diff(worktree: Worktree, base_ref: str) -> str:
    """Return the unified diff between base_ref and HEAD in the worktree."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")


def git_commit_in_worktree(worktree: Worktree, message: str) -> str:
    """Stage all changes in worktree and create a commit; return the new SHA."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")


def remove_worktree(worktree: Worktree) -> None:
    """Clean up the worktree via `git worktree remove`."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
