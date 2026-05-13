"""Blue agent: extends the fixer to also address open Red attacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anneal.adversarial.base import Attack
from anneal.fix.base import Patch
from anneal.llm.base import LLM


@dataclass
class BlueReport:
    """Output of a single Blue hardening pass."""

    patch: Patch | None         # None if no changes needed this round
    tokens_used: int
    raw_response: str


class BlueAgent:
    """Blue defender that audits, fixes, and addresses open Red attacks."""

    def __init__(self, llm: LLM) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def harden(
        self,
        current_diff: str,
        repo_root: Path,
        open_attacks: list[Attack],
    ) -> BlueReport:
        """Audit the diff, address open_attacks, and produce a patch if needed."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
