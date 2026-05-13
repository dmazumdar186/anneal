"""Fixer Protocol and Patch dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from anneal.audit.base import AuditReport


@dataclass(frozen=True)
class Patch:
    """A set of file changes produced by a Fixer to address findings."""

    unified_diff: str           # unified diff text to apply
    tokens_used: int
    raw_response: str           # original LLM text, persisted to transcript
    rationale: str              # fixer's explanation of what was changed and why


@runtime_checkable
class Fixer(Protocol):
    """Protocol that all fixer implementations must satisfy."""

    def fix(self, report: AuditReport, current_diff: str, repo_root: Path) -> Patch:
        """Produce a Patch that addresses the findings in report."""
        ...
