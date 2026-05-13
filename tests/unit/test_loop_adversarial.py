"""Unit tests for the adversarial Red-vs-Blue loop using DeterministicMockLLM.

Tests: Blue wins (Red empty x2), blue_cannot_defend (same attack x3),
mixed kind=test + kind=finding rounds, Judge accept/reject.
Phase 3 — adversarial loop logic.
"""

import pytest

from anneal.loop_adversarial import anneal_adversarial
from anneal.loop_classic import AnnealResult
from anneal.config import AnnealConfig
from anneal.llm.mock import DeterministicMockLLM
from anneal.adversarial.base import Attack, AttackResult, AttackKind
from anneal.adversarial.red import RedAgent
from anneal.adversarial.blue import BlueAgent
from anneal.adversarial.judge import Judge


def test_placeholder():
    pytest.skip("Phase 3 — not yet implemented")
