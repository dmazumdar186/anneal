"""Default fixer: generates minimal patches to address auditor findings."""

from __future__ import annotations

from pathlib import Path

from anneal.audit.base import AuditReport
from anneal.fix.base import Patch
from anneal.llm.base import LLM


class DefaultFixer:
    """Built-in fixer that turns AuditReport findings into unified-diff patches."""

    def __init__(self, llm: LLM) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def fix(self, report: AuditReport, current_diff: str, repo_root: Path) -> Patch:
        """Generate a Patch addressing the findings in report."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
