"""Auditor Protocol, severity/verdict types, Finding and AuditReport dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Verdict = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class Finding:
    """A single issue identified by an auditor in the diff under review."""

    severity: Severity
    title: str
    description: str
    file_path: str
    line_start: int | None
    line_end: int | None
    suggestion: str
    fingerprint: str  # deterministic hash of (severity, file_path, title) for oscillation detection


@dataclass(frozen=True)
class AuditReport:
    """Complete output of one auditor pass over a diff."""

    verdict: Verdict
    findings: tuple[Finding, ...]
    summary: str
    tokens_used: int
    raw_response: str  # original LLM text, persisted to transcript


@runtime_checkable
class Auditor(Protocol):
    """Protocol that all auditor implementations must satisfy."""

    def audit(self, diff: str, repo_root: Path) -> AuditReport:
        """Audit a diff and return a structured AuditReport."""
        ...
