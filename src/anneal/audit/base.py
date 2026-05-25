"""Auditor Protocol, severity/verdict types, Finding and AuditReport dataclasses."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Verdict = Literal["PASS", "FAIL", "WARNINGS"]


@dataclass(frozen=True)
class Finding:
    """A single issue identified by an auditor in the diff under review."""

    severity: Severity
    summary: str           # one-line description (used for fingerprinting)
    file: str              # file path or "" if not file-specific
    impact: str            # what goes wrong if not fixed
    recommended_fix: str   # concrete suggestion
    # Optional location info
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class AuditReport:
    """Complete output of one auditor pass over a diff.

    Fields
    ------
    verdict         PASS / FAIL / WARNINGS
    findings        Structured list of issues found.
    silent_drops    Items that entered a step but never came out (parsed from
                    the "### Silent Drops" section).
    logic_disagreements  Disagreements between agent and auditor (parsed from
                    the "### Logic Disagreements" section).
    summary         Full text of the "### Summary" section.
    raw_markdown    The complete unmodified LLM response, persisted to transcript.
    tokens_used     Total input + output tokens for this audit call.
    """

    verdict: Verdict
    findings: list[Finding]
    silent_drops: list[str]
    logic_disagreements: list[str]
    summary: str
    raw_markdown: str
    tokens_used: int


def finding_fingerprint(f: Finding) -> str:
    """Return a stable 16-hex-char hash of (severity, file, summary).

    Used by the loop to detect oscillation: if the same fingerprint appears
    in three consecutive rounds without being fixed, the loop aborts.

    Example::

        fp = finding_fingerprint(Finding(severity="HIGH", file="src/foo.py",
                                         summary="off-by-one in loop bound", ...))
        assert len(fp) == 16
    """
    key = f"{f.severity}|{f.file}|{f.summary}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@runtime_checkable
class Auditor(Protocol):
    """Protocol that all auditor implementations must satisfy."""

    def audit(self, diff: str, repo_root: Path, *, sast_findings: str = "") -> AuditReport:
        """Audit a diff and return a structured AuditReport.

        Args:
            diff:         Unified diff string to audit.
            repo_root:    Path to the repository root.
            sast_findings: Optional pre-pass SAST output as a markdown string.
                           When non-empty, the auditor should treat these as
                           known issues and focus on what SAST cannot catch.
        """
        ...
