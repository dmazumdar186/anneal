"""JSONL round-log writer and manifest.json producer for a single anneal run.

transcript/ is a sink — no other module reads from it during a loop.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from anneal.audit.base import AuditReport
from anneal.adversarial.base import Attack, AttackResult
from anneal.adversarial.red import RedAttackSet
from anneal.adversarial.blue import BlueReport
from anneal.diff.patch import ApplyResult
from anneal.fix.base import Patch


def _to_dict(obj: object) -> object:
    """Recursively convert dataclasses / paths to JSON-serialisable types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [_to_dict(i) for i in obj]
    return obj


def _dumps(obj: object) -> str:
    return json.dumps(_to_dict(obj), default=str, indent=2)


class TranscriptWriter:
    """Writes per-round JSON files plus manifest.json to log_dir.

    Directory layout::

        <log_dir>/
            manifest.json          # mode, started_at, finalized_at, result
            round_001/
                audit.json
                audit.md
                fix.json
                fix.diff
            round_002/
                ...

    transcript/ is a sink — no other module reads from it during a loop.
    """

    def __init__(self, log_dir: Path, mode: Literal["classic", "adversarial"]) -> None:
        self._log_dir = log_dir
        self._mode = mode
        self._started_at = datetime.now(tz=timezone.utc).isoformat()
        self._red_history: list[RedAttackSet] = []

        log_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "mode": mode,
            "started_at": self._started_at,
            "finalized_at": None,
            "result": None,
        }
        (log_dir / "manifest.json").write_text(_dumps(manifest), encoding="utf-8")

    def _round_dir(self, round_idx: int) -> Path:
        d = self._log_dir / f"round_{round_idx:03d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_audit(self, round_idx: int, report: AuditReport) -> None:
        """Write audit.json and audit.md for the given round."""
        d = self._round_dir(round_idx)
        # Structured JSON (without raw_markdown to avoid duplication)
        audit_dict = {
            "verdict": report.verdict,
            "findings": [_to_dict(f) for f in report.findings],
            "silent_drops": report.silent_drops,
            "logic_disagreements": report.logic_disagreements,
            "summary": report.summary,
            "tokens_used": report.tokens_used,
        }
        (d / "audit.json").write_text(json.dumps(audit_dict, indent=2), encoding="utf-8")
        (d / "audit.md").write_text(report.raw_markdown, encoding="utf-8")

    def write_fix(self, round_idx: int, patch: Patch, apply_result: ApplyResult) -> None:
        """Write fix.json and fix.diff for the given round."""
        d = self._round_dir(round_idx)
        fix_dict = {
            "rationale": patch.rationale,
            "tokens_used": patch.tokens_used,
            "apply_result": {
                "ok": apply_result.ok,
                "conflicts": apply_result.conflicts,
                "stderr": apply_result.stderr,
            },
        }
        (d / "fix.json").write_text(json.dumps(fix_dict, indent=2), encoding="utf-8")
        (d / "fix.diff").write_text(patch.unified_diff, encoding="utf-8")

    def write_blue(self, round_idx: int, blue_report: BlueReport) -> None:  # noqa: ARG002
        """Stub for Phase 3 (adversarial mode Blue agent logging)."""
        raise NotImplementedError("write_blue is implemented in Phase 3 (adversarial mode)")

    def write_red(
        self,
        round_idx: int,  # noqa: ARG002
        all_attacks: list[Attack],  # noqa: ARG002
        landed: list[AttackResult],  # noqa: ARG002
    ) -> None:
        """Stub for Phase 3 (adversarial mode Red agent logging)."""
        raise NotImplementedError("write_red is implemented in Phase 3 (adversarial mode)")

    def red_history(self) -> list[RedAttackSet]:
        """Return all Red attack sets recorded so far. Empty list in Phase 2."""
        return list(self._red_history)

    def finalize(self, result: object) -> Path:
        """Write final outcome to manifest.json and return its path.

        Args:
            result: Any dict-like or dataclass representing the AnnealResult.
                    Uses default=str serialisation so no import of AnnealResult
                    is needed here.

        Returns:
            Path to the written manifest.json.
        """
        manifest = {
            "mode": self._mode,
            "started_at": self._started_at,
            "finalized_at": datetime.now(tz=timezone.utc).isoformat(),
            "result": _to_dict(result),
        }
        manifest_path = self._log_dir / "manifest.json"
        manifest_path.write_text(_dumps(manifest), encoding="utf-8")
        return manifest_path
