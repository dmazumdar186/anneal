"""Judge agent: verifies non-executable Red findings, defaults to invalid if unsure."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anneal.adversarial.base import Attack
from anneal.llm.base import LLM


@dataclass(frozen=True)
class Judgment:
    """Verdict from the Judge on a single non-executable Red finding."""

    valid: bool
    verdict_text: str           # judge's reasoning, quoted from the diff where possible
    tokens_used: int


class Judge:
    """Independent LLM judge that evaluates Red's non-executable (kind=finding) attacks."""

    def __init__(self, llm: LLM) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def judge(self, attack: Attack, current_diff: str, repo_root: Path) -> Judgment:
        """Evaluate whether a Red finding is factually correct.

        Defaults to invalid=False when evidence is ambiguous.
        """
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
