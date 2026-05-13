"""Shared adversarial types: AttackKind, Attack, and AttackResult dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from anneal.audit.base import Severity

AttackKind = Literal["test", "finding"]


@dataclass(frozen=True)
class Attack:
    """A single attack produced by the Red agent targeting the current diff."""

    kind: AttackKind
    fingerprint: str            # hash of (kind, target, claim) for dedup / blue_stuck detection
    target_files: tuple[str, ...]
    rationale: str              # Red's one-paragraph "why this matters"
    # kind == "test" fields
    test_path: str | None       # relative path in worktree to the pytest file Red wrote
    # kind == "finding" fields
    severity: Severity | None
    claim: str | None
    evidence: str | None
    expected: str | None
    actual: str | None

    def with_evidence(self, evidence_data: object) -> "AttackResult":
        """Convenience method to wrap this attack in a landed AttackResult."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")


@dataclass(frozen=True)
class AttackResult:
    """An attack paired with its verification outcome."""

    attack: Attack
    landed: bool
    evidence: str               # test stderr, or judge's verdict text
