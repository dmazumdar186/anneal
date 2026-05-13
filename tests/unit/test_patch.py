"""Unit tests for patch application: apply_patch and conflict handling."""

from __future__ import annotations

import subprocess
from pathlib import Path

from anneal.diff.patch import apply_patch
from anneal.fix.base import Patch


def _init_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@anneal"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Anneal Test"], cwd=repo, check=True, capture_output=True)
    (repo / "target.py").write_text('x = 1\n', encoding="utf-8")
    subprocess.run(["git", "add", "target.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def test_apply_patch_valid(tmp_path: Path) -> None:
    """A valid unified diff applies cleanly and changes file content."""
    repo = _init_repo(tmp_path)

    valid_diff = (
        "--- a/target.py\n"
        "+++ b/target.py\n"
        "@@ -1,1 +1,2 @@\n"
        " x = 1\n"
        "+y = 2\n"
        "\n"
    )
    patch = Patch(unified_diff=valid_diff, rationale="add y", tokens_used=0, raw_response="")
    result = apply_patch(repo, patch)

    assert result.ok is True
    assert (repo / "target.py").read_text(encoding="utf-8") == "x = 1\ny = 2\n"


def test_apply_patch_conflict(tmp_path: Path) -> None:
    """A diff whose context lines don't match produces ok=False and non-empty stderr."""
    repo = _init_repo(tmp_path)

    broken_diff = (
        "--- a/target.py\n"
        "+++ b/target.py\n"
        "@@ -1,3 +1,3 @@\n"
        " this line does not exist\n"
        " neither does this\n"
        "-nor this\n"
        "+fixed\n"
        "\n"
    )
    patch = Patch(unified_diff=broken_diff, rationale="bad patch", tokens_used=0, raw_response="")
    result = apply_patch(repo, patch)

    assert result.ok is False
    assert result.stderr != ""
