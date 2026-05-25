"""Persistent suppression store: per-repo .anneal/suppressions.json."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class Suppression:
    """A single suppressed finding."""

    fingerprint: str   # 16-hex-char hash from finding_fingerprint()
    reason: str        # user-supplied explanation
    created_at: str    # ISO 8601
    last_seen_at: str  # ISO 8601 — updated when the finding is encountered again


class SuppressionStore:
    """Read/write .anneal/suppressions.json atomically.

    Args:
        path: Full path to the suppressions.json file (e.g.
              ``worktree / ".anneal" / "suppressions.json"``).
              The parent directory is created on first ``save()``.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        # In-memory dict: fingerprint → Suppression
        self._data: dict[str, Suppression] = {}
        self.load()

    # ── Persistence ────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Read suppressions.json; silently returns empty on missing/malformed file."""
        if not self._path.exists():
            self._data = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("top-level value is not a JSON object")
            result: dict[str, Suppression] = {}
            for fp, entry in raw.items():
                result[fp] = Suppression(
                    fingerprint=fp,
                    reason=entry.get("reason", ""),
                    created_at=entry.get("created_at", ""),
                    last_seen_at=entry.get("last_seen_at", ""),
                )
            self._data = result
        except (json.JSONDecodeError, ValueError, KeyError, AttributeError) as exc:
            logger.warning(
                "suppressions: could not parse %s (%s) — treating as empty",
                self._path,
                exc,
            )
            self._data = {}

    def save(self) -> None:
        """Write suppressions.json atomically (write to .tmp then rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        payload = {
            fp: {
                "reason": s.reason,
                "created_at": s.created_at,
                "last_seen_at": s.last_seen_at,
            }
            for fp, s in self._data.items()
        }
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Atomic rename (works cross-platform for same filesystem)
        try:
            tmp.replace(self._path)
        except OSError:
            # Fallback for Windows if replace fails (rare edge case)
            os.replace(str(tmp), str(self._path))

    # ── Mutation ───────────────────────────────────────────────────────────────

    def add(self, fingerprint: str, reason: str) -> None:
        """Add or refresh a suppression entry."""
        now = _now_iso()
        existing = self._data.get(fingerprint)
        self._data[fingerprint] = Suppression(
            fingerprint=fingerprint,
            reason=reason,
            created_at=existing.created_at if existing else now,
            last_seen_at=now,
        )
        self.save()

    def remove(self, fingerprint: str) -> None:
        """Remove a suppression entry. No-op if not present."""
        if fingerprint in self._data:
            del self._data[fingerprint]
            self.save()

    # ── Query ──────────────────────────────────────────────────────────────────

    def is_suppressed(self, fingerprint: str) -> bool:
        """Return True if fingerprint is suppressed; also refreshes last_seen_at."""
        if fingerprint not in self._data:
            return False
        # Refresh last_seen_at
        s = self._data[fingerprint]
        self._data[fingerprint] = Suppression(
            fingerprint=fingerprint,
            reason=s.reason,
            created_at=s.created_at,
            last_seen_at=_now_iso(),
        )
        self.save()
        return True

    def list_all(self) -> list[Suppression]:
        """Return all suppressions sorted by fingerprint."""
        return sorted(self._data.values(), key=lambda s: s.fingerprint)
