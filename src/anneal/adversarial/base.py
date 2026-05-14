"""Shared adversarial types: AttackKind, Attack, AttackResult, fingerprint helpers,
and per-turn output dataclasses (RedTurnOutput, BlueTurnOutput, JudgeOutput).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from anneal.audit.base import Severity

if TYPE_CHECKING:
    from anneal.fix.base import Patch

AttackKind = Literal["test", "finding"]
JudgeVerdict = Literal["valid", "invalid", "uncertain"]


@dataclass(frozen=True)
class Attack:
    """An attack produced by Red.

    For kind == "test": test_path and test_body are populated. severity/claim/evidence/
    expected/actual are None.

    For kind == "finding": severity/claim/evidence/expected/actual are populated.
    test_path/test_body are None.

    Args:
        kind: "test" or "finding".
        fingerprint: Stable hash for dedup / blue_stuck. Derived from
            (kind, target_files tuple, summary-or-test-name hash).
        target_files: Files in the worktree the attack targets.
        rationale: Red's one-paragraph "why this matters".
        test_path: Relative path in worktree where the test file will be written
            (kind="test" only).
        test_body: pytest file contents (kind="test" only).
        severity: Finding severity (kind="finding" only).
        claim: Short one-line claim (kind="finding" only).
        evidence: Quoted evidence from the diff (kind="finding" only).
        expected: What the diff should say/do (kind="finding" only).
        actual: What the diff actually says/does (kind="finding" only).
    """

    kind: AttackKind
    fingerprint: str
    target_files: tuple[str, ...]
    rationale: str
    # if kind == "test":
    test_path: str | None = None      # relative path in worktree where the test file will be written
    test_body: str | None = None      # pytest file contents
    # if kind == "finding":
    severity: Severity | None = None
    claim: str | None = None
    evidence: str | None = None
    expected: str | None = None
    actual: str | None = None

    def with_evidence(self, evidence_data: object) -> "AttackResult":
        """Wrap this attack in a landed AttackResult.

        Args:
            evidence_data: Either a TestRunResult (kind="test") or a JudgeOutput
                (kind="finding"). The evidence string is derived from stdout/stderr
                or rationale respectively.

        Returns:
            AttackResult with landed=True and evidence extracted from evidence_data.
        """
        # Import locally to avoid cycles; evidence_data is duck-typed
        evidence_str: str
        if hasattr(evidence_data, "stdout"):
            # TestRunResult shape
            evidence_str = (
                (evidence_data.stdout or "") + "\n" + (evidence_data.stderr or "")
            ).strip()
        elif hasattr(evidence_data, "rationale"):
            # JudgeOutput shape
            evidence_str = str(evidence_data.rationale)
        else:
            evidence_str = str(evidence_data)
        return AttackResult(attack=self, landed=True, evidence=evidence_str)


@dataclass(frozen=True)
class AttackResult:
    """An attack paired with its verification outcome."""

    attack: Attack
    landed: bool
    evidence: str                    # test stderr/stdout, or judge's verdict text


def attack_fingerprint(
    kind: AttackKind,
    target_files: tuple[str, ...],
    identifier: str,
) -> str:
    """Return a stable 16-hex-char hash for dedup / blue_stuck detection.

    Uses sha256 of ``"{kind}|{','.join(target_files)}|{identifier}"``.

    The ``identifier`` should be:
    - ``test_path`` for kind="test"
    - A sha256 of ``"{severity}|{claim}"`` for kind="finding"

    Args:
        kind: "test" or "finding".
        target_files: Tuple of file paths targeted by the attack.
        identifier: Stable per-attack discriminator (see above).

    Returns:
        First 16 hex characters of the sha256 digest.

    Example::

        fp = attack_fingerprint("test", ("src/foo.py",), "tests/red/test_attack_001.py")
        assert len(fp) == 16
    """
    key = f"{kind}|{','.join(target_files)}|{identifier}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class RedTurnOutput:
    """What Red returns each round.

    Args:
        attacks: List of Attack objects produced this round (at most 5).
        tokens_used: Total input + output tokens consumed.
    """

    attacks: list[Attack]
    tokens_used: int


@dataclass(frozen=True)
class BlueTurnOutput:
    """What Blue returns each round.

    Args:
        patch: Unified diff patch from anneal.fix.base, or None if Blue has nothing
            to apply this round.
        rationale: One-line explanation of what Blue changed (or why nothing changed).
        tokens_used: Total input + output tokens consumed.
    """

    patch: "Patch | None"            # from anneal.fix.base; None if Blue has nothing to apply
    rationale: str                   # one-line explanation
    tokens_used: int


@dataclass(frozen=True)
class JudgeOutput:
    """Verdict from the Judge on a single non-executable Red finding.

    Args:
        verdict: "valid" — Red's claim is factually correct; "invalid" — claim is
            wrong or unsupported; "uncertain" — treated as functionally invalid by
            the calling loop.
        rationale: Short explanation quoting evidence from the diff.
        tokens_used: Total input + output tokens consumed.
    """

    verdict: JudgeVerdict
    rationale: str
    tokens_used: int
