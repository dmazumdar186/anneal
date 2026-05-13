"""Unit tests for the classic auditor+fixer loop using DeterministicMockLLM.

Tests termination conditions: convergence, max_rounds, oscillation, patch_conflict, budget.
Phase 1 — loop logic and termination conditions.
"""

import pytest

from anneal.loop_classic import anneal_classic, AnnealResult
from anneal.config import AnnealConfig
from anneal.llm.mock import DeterministicMockLLM


def test_placeholder():
    pytest.skip("Phase 1 — not yet implemented")
