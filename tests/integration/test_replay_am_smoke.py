"""Integration smoke test: AM-replay with real Claude against cc4fca1.

Asserts: worktree created and cleaned, >=1 round completes, transcript files exist,
and git status in the AntiGravity workspace is clean (zero AM mutations).
Requires ANTHROPIC_API_KEY and the AntiGravity repo on disk. Skipped without either.
Phase 5 — AM-replay demo validation.
"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.live_api]

from anneal.replay.am import run_am_replay, build_replay_config
from anneal.loop_classic import AnnealResult


def test_placeholder():
    pytest.skip("Phase 5 — not yet implemented")
