"""Integration test: classic mode on examples/synthetic_buggy/ with real Claude.

Asserts: converges <=4 rounds, final diff fixes the planted bug, no unrelated changes.
Requires ANTHROPIC_API_KEY. Skipped without it.
Phase 4 — integration with real LLM.
"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.live_api]

from anneal.loop_classic import anneal_classic, AnnealResult
from anneal.config import AnnealConfig


def test_placeholder():
    pytest.skip("Phase 4 — not yet implemented")
