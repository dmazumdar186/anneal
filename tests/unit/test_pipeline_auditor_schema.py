"""Unit tests for PipelineAuditor response parsing: schema validation and AuditReport construction.

Feed the parser example markdown from the AM pipeline-auditor.md and assert correct AuditReport.
Phase 2 — auditor parsing logic.
"""

import pytest

from anneal.audit.base import AuditReport, Finding, Severity, Verdict
from anneal.audit.pipeline_auditor import PipelineAuditor


def test_placeholder():
    pytest.skip("Phase 2 — not yet implemented")
