"""AM-replay: runs anneal classic against a historical AntiGravity commit (read-only)."""

from __future__ import annotations

from pathlib import Path

from anneal.config import AnnealConfig
from anneal.loop_classic import AnnealResult


def build_replay_config(
    commit: str,
    repo: Path,
    log_dir: Path,
    base_model: str = "claude-sonnet-4-6",
    max_rounds: int = 10,
    until_clean: int = 2,
    max_cost_usd: float = 5.0,
) -> AnnealConfig:
    """Build an AnnealConfig targeting a specific AntiGravity historical commit.

    Uses git worktree against the external repo (read-only).
    Never modifies any file in repo.
    """
    raise NotImplementedError("anneal v0.0.1: not yet implemented")


def run_am_replay(commit: str, repo: Path, log_dir: Path, **kwargs: object) -> AnnealResult:
    """Convenience: build config and run classic mode for the AM-replay demo."""
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
