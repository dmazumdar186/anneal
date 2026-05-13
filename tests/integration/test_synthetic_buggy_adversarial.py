"""Integration test: adversarial Red-vs-Blue on examples/adversarial_demo/ with real Claude.

Asserts: Blue wins within max_rounds, transcript shows >=1 landed attack across rounds.
Requires ANTHROPIC_API_KEY. Skipped without it.
Phase 4 — integration with real LLM.
"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.live_api]

from anneal.loop_adversarial import anneal_adversarial
from anneal.loop_classic import AnnealResult
from anneal.config import AnnealConfig


def test_placeholder():
    pytest.skip("Phase 4 — not yet implemented")
