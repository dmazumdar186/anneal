"""Red agent: generates attacks (failing tests or structured findings) against the diff."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anneal.adversarial.base import Attack
from anneal.llm.base import LLM


@dataclass
class RedAttackSet:
    """Collection of attacks produced by Red in a single round."""

    attacks: list[Attack]
    tokens_used: int
    raw_response: str


class RedAgent:
    """Red attacker that tries to find issues the Blue agent failed to address."""

    def __init__(self, llm: LLM) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def attack(
        self,
        current_diff: str,
        repo_root: Path,
        history: list[RedAttackSet],
    ) -> RedAttackSet:
        """Generate a new set of attacks against the current state of the diff."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
