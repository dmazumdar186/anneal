"""JSONL round-log writer and manifest.json producer for a single anneal run."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from anneal.audit.base import AuditReport
from anneal.adversarial.base import Attack, AttackResult
from anneal.adversarial.red import RedAttackSet
from anneal.adversarial.blue import BlueReport
from anneal.fix.base import Patch
from anneal.diff.patch import ApplyResult


class TranscriptWriter:
    """Writes one JSONL file per round plus manifest.json to log_dir.

    transcript/ is a sink — no other module reads from it during a loop.
    """

    def __init__(self, log_dir: Path, mode: Literal["classic", "adversarial"]) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def write_audit(self, round_num: int, report: AuditReport) -> None:
        """Append the audit report for round_num to the JSONL log."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def write_fix(self, round_num: int, patch: Patch, apply_result: ApplyResult) -> None:
        """Append the fix patch and apply result for round_num."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def write_blue(self, round_num: int, report: BlueReport) -> None:
        """Append Blue's hardening report for round_num."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def write_red(
        self,
        round_num: int,
        all_attacks: list[Attack],
        landed: list[AttackResult],
    ) -> None:
        """Append Red's attacks and which ones landed for round_num."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def red_history(self) -> list[RedAttackSet]:
        """Return all Red attack sets recorded so far (for Red's history context)."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def finalize(self, result: object) -> Path:
        """Write manifest.json and return its path."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
