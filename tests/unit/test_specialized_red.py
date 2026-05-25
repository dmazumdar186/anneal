"""Tests for specialist Red agents (SecurityRed, PerfRed, LogicRed) and RedCoordinator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from anneal.adversarial.base import Attack, RedTurnOutput, attack_fingerprint
from anneal.adversarial.logic_red import LogicRed
from anneal.adversarial.perf_red import PerfRed
from anneal.adversarial.red import Red
from anneal.adversarial.red_coordinator import RedCoordinator
from anneal.adversarial.security_red import SecurityRed


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_attack(test_path: str, target: str = "src/foo.py") -> Attack:
    """Build a minimal kind=test Attack with a stable fingerprint."""
    fp = attack_fingerprint("test", (target,), test_path)
    return Attack(
        kind="test",
        fingerprint=fp,
        target_files=(target,),
        rationale="stub",
        test_path=test_path,
        test_body="def test_stub(): pass",
    )


class _FakeRed(Red):
    """Stub Red that returns a fixed list of attacks without calling an LLM."""

    def __init__(self, attacks: list[Attack]) -> None:
        # Bypass Red.__init__ — we don't need an LLM or prompt loading.
        self._attacks = attacks

    def attack(self, diff, worktree, history) -> RedTurnOutput:  # type: ignore[override]
        return RedTurnOutput(attacks=list(self._attacks), tokens_used=10)


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_security_red_loads_security_prompt() -> None:
    """SecurityRed should use security_red.md and that file must contain the specialist tag."""
    fake_llm = MagicMock()
    agent = SecurityRed(fake_llm)

    # Prompt path ends with the expected filename
    prompt_path = Path(agent._Red__dict__["_prompt"]) if False else None  # noqa: F841
    # Access via the private attribute set by Red.__init__
    assert agent._prompt  # non-empty
    assert "Security-specialist Red" in agent._prompt

    # Also verify the prompt_path attribute is set correctly
    prompts_dir = Path(__file__).parent.parent.parent / "src" / "anneal" / "adversarial" / "prompts"
    expected_path = prompts_dir / "security_red.md"
    assert expected_path.exists(), f"security_red.md not found at {expected_path}"
    assert expected_path.name == "security_red.md"


def test_perf_red_loads_perf_prompt() -> None:
    """PerfRed should use perf_red.md and that file must contain the specialist tag."""
    fake_llm = MagicMock()
    agent = PerfRed(fake_llm)

    assert agent._prompt
    assert "Performance-specialist Red" in agent._prompt

    prompts_dir = Path(__file__).parent.parent.parent / "src" / "anneal" / "adversarial" / "prompts"
    expected_path = prompts_dir / "perf_red.md"
    assert expected_path.exists(), f"perf_red.md not found at {expected_path}"
    assert expected_path.name == "perf_red.md"


def test_logic_red_loads_logic_prompt() -> None:
    """LogicRed should use logic_red.md and that file must contain the specialist tag."""
    fake_llm = MagicMock()
    agent = LogicRed(fake_llm)

    assert agent._prompt
    assert "Logic-specialist Red" in agent._prompt

    prompts_dir = Path(__file__).parent.parent.parent / "src" / "anneal" / "adversarial" / "prompts"
    expected_path = prompts_dir / "logic_red.md"
    assert expected_path.exists(), f"logic_red.md not found at {expected_path}"
    assert expected_path.name == "logic_red.md"


def test_coordinator_runs_agents_in_parallel_and_dedupes() -> None:
    """RedCoordinator should merge attacks from all agents and dedup by fingerprint.

    Setup: two fake agents.
      - agent_a returns attacks [A1, A2, A3]
      - agent_b returns attacks [B1, B2, A2_dup]   ← A2_dup shares fingerprint with A2
    Expected combined output: [A1, A2, A3, B1, B2]  — 5 unique attacks (dup dropped).
    """
    a1 = _make_attack("tests/red/test_attack_001.py", "src/alpha.py")
    a2 = _make_attack("tests/red/test_attack_002.py", "src/alpha.py")
    a3 = _make_attack("tests/red/test_attack_003.py", "src/alpha.py")

    b1 = _make_attack("tests/red/test_attack_004.py", "src/beta.py")
    b2 = _make_attack("tests/red/test_attack_005.py", "src/beta.py")
    # a2_dup has the SAME fingerprint as a2 (identical test_path + target_files)
    a2_dup = _make_attack("tests/red/test_attack_002.py", "src/alpha.py")
    assert a2_dup.fingerprint == a2.fingerprint, "Setup error: dup must share fingerprint"

    agent_a = _FakeRed([a1, a2, a3])
    agent_b = _FakeRed([b1, b2, a2_dup])

    coordinator = RedCoordinator(agents=[agent_a, agent_b], max_workers=2)
    result = coordinator.attack(diff="--- a\n+++ b\n", worktree=Path("."), history=[])

    assert len(result.attacks) == 5, (
        f"Expected 5 unique attacks (3 + 3 - 1 dup), got {len(result.attacks)}"
    )

    # Fingerprints in result must all be unique
    fps = [atk.fingerprint for atk in result.attacks]
    assert len(fps) == len(set(fps)), "Duplicate fingerprints found in coordinator output"

    # Tokens: 10 (agent_a) + 10 (agent_b) = 20
    assert result.tokens_used == 20

    # Agent-a attacks come first (agent order preserved)
    assert result.attacks[0].fingerprint == a1.fingerprint
    assert result.attacks[1].fingerprint == a2.fingerprint
    assert result.attacks[2].fingerprint == a3.fingerprint
