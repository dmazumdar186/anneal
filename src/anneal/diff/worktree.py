"""Git worktree create, diff, commit, and cleanup — the only module that shells out to git."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


class GitOperationError(Exception):
    """Raised when a git shell command fails.

    Attributes:
        message: Human-readable description.
        stderr: Captured stderr from the failed subprocess, if available.
    """

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr


def _run(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command, return stdout. Raises GitOperationError on failure."""
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise GitOperationError(
            f"git command failed: {' '.join(args)}\n{exc.stderr}",
            stderr=exc.stderr,
        ) from exc


def make_worktree(repo: Path, base_ref: str, dest: Path | None = None) -> Path:
    """Create a git worktree at base_ref and return the absolute path to it.

    Args:
        repo: Path to the main git repository.
        base_ref: Git ref (branch, tag, SHA) to check out in the worktree.
        dest: Destination directory. If None, creates a timestamped directory
            under <cwd>/worktrees/<timestamp>/.

    Returns:
        Absolute path to the created worktree.

    Raises:
        GitOperationError: If `git worktree add` fails.
    """
    if dest is None:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        worktrees_root = Path.cwd() / "worktrees"
        worktrees_root.mkdir(parents=True, exist_ok=True)
        dest = worktrees_root / ts

    dest = dest.resolve()
    _run(["git", "-C", str(repo), "worktree", "add", str(dest), base_ref])
    return dest


def cleanup_worktree(repo: Path, worktree_path: Path, force: bool = False) -> None:
    """Remove a git worktree.

    Args:
        repo: Path to the main git repository.
        worktree_path: Absolute path to the worktree to remove.
        force: Pass --force to git worktree remove (removes even with dirty state).

    Raises:
        GitOperationError: If `git worktree remove` fails.
    """
    cmd = ["git", "-C", str(repo), "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(worktree_path))
    _run(cmd)


def git_diff(worktree: Path, base_ref: str) -> str:
    """Return the unified diff between base_ref and HEAD in the worktree.

    Args:
        worktree: Absolute path to the worktree.
        base_ref: Base git ref to diff against (e.g. "HEAD~1", a SHA, etc.).

    Returns:
        Unified diff as a string (may be empty if no changes).

    Raises:
        GitOperationError: If the git diff command fails.
    """
    return _run(["git", "-C", str(worktree), "diff", base_ref], cwd=worktree)


def git_commit_in_worktree(worktree: Path, message: str) -> str:
    """Stage all changes in the worktree and create a commit.

    Args:
        worktree: Absolute path to the worktree.
        message: Commit message.

    Returns:
        The new commit SHA (40 hex characters).

    Raises:
        GitOperationError: If there are no changes to commit, or if any git
            command fails.
    """
    # Stage everything
    _run(["git", "-C", str(worktree), "add", "-A"], cwd=worktree)

    # Commit — will fail if nothing staged
    try:
        _run(
            ["git", "-C", str(worktree), "commit", "-m", message],
            cwd=worktree,
        )
    except GitOperationError as exc:
        if "nothing to commit" in str(exc) or "nothing added to commit" in str(exc):
            raise GitOperationError(
                "git_commit_in_worktree: nothing to commit in worktree "
                f"'{worktree}'. Stage changes before committing.",
                stderr=exc.stderr,
            ) from exc
        raise

    sha = _run(["git", "-C", str(worktree), "rev-parse", "HEAD"], cwd=worktree)
    return sha.strip()
