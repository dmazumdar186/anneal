"""Unit tests for the AM-key guard in config.load_env.

Verifies that anneal's load_env does NOT walk parent directories, and that
assert_not_am_workspace emits the expected warning when an AM workspace is detected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anneal.config import assert_not_am_workspace, load_env


def test_load_env_does_not_walk_parent_dirs(tmp_path: Path) -> None:
    """Plant a fake ANTHROPIC_API_KEY in a parent .env; child has no .env.

    load_env(repo_root=child) must return {} — it must NOT walk up to parent.
    """
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    # Plant a dangerous key in the parent .env
    (parent / ".env").write_text("ANTHROPIC_API_KEY=client_key_DO_NOT_USE\n", encoding="utf-8")

    # child has NO .env
    result = load_env(repo_root=child)

    assert result == {}, (
        f"load_env should return {{}} when there is no .env in repo_root, "
        f"but got: {result}"
    )
    assert "client_key_DO_NOT_USE" not in result.values()


def test_assert_not_am_workspace_warns(tmp_path: Path) -> None:
    """Plant a .env and an accessory_masters_* dir in tmp_path.

    assert_not_am_workspace(tmp_path) must emit a UserWarning containing
    "AM-key guard".
    """
    # Create the .env at the repo root
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=some_key\n", encoding="utf-8")

    # Create the AM-identifying directory structure
    am_dir = tmp_path / "directives" / "gtm_client_workflows"
    am_dir.mkdir(parents=True)
    (am_dir / "accessory_masters_gtm.md").write_text("# AM GTM\n", encoding="utf-8")

    with pytest.warns(UserWarning, match="AM-key guard"):
        assert_not_am_workspace(tmp_path)


def test_load_env_reads_own_env(tmp_path: Path) -> None:
    """.env in repo_root with ANTHROPIC_API_KEY=my_own_key is loaded correctly."""
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=my_own_key\n", encoding="utf-8")

    result = load_env(repo_root=tmp_path)

    assert result.get("ANTHROPIC_API_KEY") == "my_own_key"
