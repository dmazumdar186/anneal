"""Pipeline auditor: mirrors the AM pipeline-auditor.md prompt and schema."""

from __future__ import annotations

from pathlib import Path

from anneal.audit.base import AuditReport
from anneal.llm.base import LLM


class PipelineAuditor:
    """Built-in auditor ported from the AntiGravity pipeline-auditor.md directive."""

    def __init__(self, llm: LLM) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def audit(self, diff: str, repo_root: Path) -> AuditReport:
        """Run the pipeline-auditor prompt against diff and parse findings."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
