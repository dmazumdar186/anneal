"""Apply unified-diff patches to worktrees and record results."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from anneal.fix.base import Patch


@dataclass
class ApplyResult:
    """Outcome of applying a Patch to a worktree."""

    ok: bool
    conflicts: list[str] = field(default_factory=list)
    stderr: str = ""


def apply_patch(worktree: Path, patch: Patch) -> ApplyResult:
    """Apply patch.unified_diff to the worktree via `git apply`.

    Uses ``--reject --whitespace=nowarn`` so that failed hunks produce .rej
    files rather than aborting immediately. After the apply attempt, we scan
    for any .rej files to detect partial failures.

    Args:
        worktree: Absolute path to the worktree.
        patch: Patch whose unified_diff will be applied.

    Returns:
        ApplyResult(ok=True, ...) if the patch applied cleanly.
        ApplyResult(ok=False, conflicts=[...], stderr=...) if any hunk failed.
    """
    if not patch.unified_diff.strip():
        # Empty diff — nothing to apply, treat as success
        return ApplyResult(ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".patch",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        tmp.write(patch.unified_diff)
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(worktree),
                "apply",
                "--reject",
                "--whitespace=nowarn",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        stderr = result.stderr

        # Scan for .rej files left behind by failed hunks
        rej_files = [str(p.relative_to(worktree)) for p in worktree.rglob("*.rej")]

        if result.returncode != 0 or rej_files:
            return ApplyResult(ok=False, conflicts=rej_files, stderr=stderr)

        return ApplyResult(ok=True, stderr=stderr)
    finally:
        tmp_path.unlink(missing_ok=True)


def apply_initial_diff(worktree_path: Path, diff_path: Path) -> ApplyResult:
    """Apply the initial input diff to the fresh worktree before the loop starts.

    Args:
        worktree_path: Absolute path to the worktree.
        diff_path: Path to a unified diff file on disk.

    Returns:
        ApplyResult indicating success or failure.

    Raises:
        FileNotFoundError: If diff_path does not exist.
    """
    if not diff_path.exists():
        raise FileNotFoundError(f"Initial diff not found: {diff_path}")

    diff_text = diff_path.read_text(encoding="utf-8")
    dummy_patch = Patch(
        unified_diff=diff_text,
        rationale="initial diff",
        tokens_used=0,
        raw_response="",
    )
    return apply_patch(worktree_path, dummy_patch)
