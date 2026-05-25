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
from anneal.adversarial.base import Attack, AttackResult, BlueTurnOutput
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

    Directory layout (classic mode)::

        <log_dir>/
            manifest.json
            round_001/
                audit.json
                audit.md
                fix.json
                fix.diff

    Directory layout (adversarial mode)::

        <log_dir>/
            manifest.json
            round_001/
                blue.json
                blue.diff          (if Blue produced a patch)
                red.json
                red_tests/         (per-test bodies for kind=test attacks)
                    test_attack_001.py
                    ...

    transcript/ is a sink — no other module reads from it during a loop.
    """

    def __init__(
        self,
        log_dir: Path,
        mode: Literal["classic", "adversarial"],
        *,
        deterministic: bool = False,
        seed: int | None = None,
        models: dict | None = None,
        max_rounds: int | None = None,
        until_clean: int | None = None,
        max_cost_usd: float | None = None,
    ) -> None:
        self._log_dir = log_dir
        self._mode = mode
        self._started_at = datetime.now(tz=timezone.utc).isoformat()

        log_dir.mkdir(parents=True, exist_ok=True)
        # Run metadata block — written once at transcript start for replay traceability.
        manifest = {
            "mode": mode,
            "started_at": self._started_at,
            "finalized_at": None,
            "result": None,
            "run_metadata": {
                "deterministic": deterministic,
                "seed": seed,
                "models": models or {},
                "max_rounds": max_rounds,
                "until_clean": until_clean,
                "max_cost_usd": max_cost_usd,
            },
        }
        (log_dir / "manifest.json").write_text(_dumps(manifest), encoding="utf-8")

    def _round_dir(self, round_idx: int) -> Path:
        d = self._log_dir / f"round_{round_idx:03d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Classic mode
    # ------------------------------------------------------------------

    def write_audit(self, round_idx: int, report: AuditReport) -> None:
        """Write audit.json and audit.md for the given round."""
        d = self._round_dir(round_idx)
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

    # ------------------------------------------------------------------
    # Adversarial mode
    # ------------------------------------------------------------------

    def write_blue(self, round_idx: int, blue_output: BlueTurnOutput) -> None:
        """Write blue.json (and blue.diff if a patch was produced) for the given round.

        Args:
            round_idx: 1-based round number.
            blue_output: The BlueTurnOutput returned by Blue.harden().
        """
        d = self._round_dir(round_idx)
        blue_dict: dict = {
            "rationale": blue_output.rationale,
            "tokens_used": blue_output.tokens_used,
            "patch": None,
        }
        if blue_output.patch is not None:
            blue_dict["patch"] = {
                "rationale": blue_output.patch.rationale,
                "tokens_used": blue_output.patch.tokens_used,
                "diff_lines": blue_output.patch.unified_diff.count("\n"),
            }
            (d / "blue.diff").write_text(blue_output.patch.unified_diff, encoding="utf-8")

        (d / "blue.json").write_text(json.dumps(blue_dict, indent=2), encoding="utf-8")

    def write_red(
        self,
        round_idx: int,
        attacks: list[Attack],
        landed: list[AttackResult],
    ) -> None:
        """Write red.json and per-test files for kind=test attacks.

        Args:
            round_idx: 1-based round number.
            attacks: All attacks Red produced this round (landed + not-landed).
            landed: Subset of attacks that landed (verified by execution or Judge).
        """
        d = self._round_dir(round_idx)
        landed_fps = {r.attack.fingerprint: r for r in landed}

        serialised_attacks = []
        for atk in attacks:
            result = landed_fps.get(atk.fingerprint)
            entry: dict = {
                "kind": atk.kind,
                "fingerprint": atk.fingerprint,
                "target_files": list(atk.target_files),
                "rationale": atk.rationale,
                "landed": result is not None,
                "evidence": result.evidence if result else None,
            }
            if atk.kind == "test":
                entry["test_path"] = atk.test_path
            else:
                entry["severity"] = atk.severity
                entry["claim"] = atk.claim
                entry["evidence_claim"] = atk.evidence
            serialised_attacks.append(entry)

        red_dict = {
            "total_attacks": len(attacks),
            "landed_count": len(landed),
            "attacks": serialised_attacks,
        }
        (d / "red.json").write_text(json.dumps(red_dict, indent=2), encoding="utf-8")

        # Write test bodies for kind=test attacks into red_tests/
        test_attacks = [a for a in attacks if a.kind == "test" and a.test_body]
        if test_attacks:
            tests_dir = d / "red_tests"
            tests_dir.mkdir(exist_ok=True)
            for atk in test_attacks:
                # Use just the filename portion of test_path for the transcript copy
                file_name = Path(atk.test_path).name if atk.test_path else f"test_fp_{atk.fingerprint}.py"
                (tests_dir / file_name).write_text(atk.test_body, encoding="utf-8")  # type: ignore[arg-type]

    def red_history(self) -> list[dict]:
        """Scan round_*/red.json for all past attacks and return their latest status.

        Scans the log directory for all round subdirectories that contain a
        ``red.json`` file, reads each attack, and returns one dict per unique
        fingerprint with the **latest known** ``landed`` status.

        Returns:
            List of dicts, each with keys:
            ``fingerprint``, ``kind``, ``landed`` (latest), ``round`` (latest seen).
        """
        import re

        round_dirs = sorted(
            (p for p in self._log_dir.iterdir() if p.is_dir() and re.match(r"round_\d+", p.name)),
            key=lambda p: p.name,
        )

        # fingerprint -> latest {fingerprint, kind, landed, round}
        seen: dict[str, dict] = {}
        for rd in round_dirs:
            red_json = rd / "red.json"
            if not red_json.exists():
                continue
            try:
                data = json.loads(red_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            # Parse round number from directory name
            round_num = int(rd.name.split("_")[1])
            for atk in data.get("attacks", []):
                fp = atk.get("fingerprint", "")
                if not fp:
                    continue
                seen[fp] = {
                    "fingerprint": fp,
                    "kind": atk.get("kind", ""),
                    "landed": bool(atk.get("landed", False)),
                    "round": round_num,
                }

        return list(seen.values())

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
