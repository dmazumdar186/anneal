"""Unit tests for prior_attempts injection in PipelineAuditor.audit().

Covers:
  - prior_attempts kwarg defaults to "" (back-compat for any existing caller)
  - When non-empty, the block is injected at the TOP of the user message
    (ahead of SAST, repograph, semantic — so loop memory frames everything)
  - The diff itself is still in the user message
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from anneal.audit.pipeline_auditor import PipelineAuditor
from anneal.llm.base import CacheUsage


class RecordingMockLLM:
    """Captures (system, user) pairs so the test can verify what was sent."""

    def __init__(self, response_text: str = "**Verdict:** PASS\n### Issues Found\nNone detected\n") -> None:
        self._response = response_text
        self.calls: list[tuple[str, str]] = []
        self.last_cache_usage = CacheUsage()

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",  # noqa: ARG002
        *,
        temperature: float | None = None,  # noqa: ARG002
        seed: int | None = None,  # noqa: ARG002
    ) -> tuple[str, int]:
        self.calls.append((system, user))
        return self._response, 500


def _make_auditor() -> tuple[PipelineAuditor, RecordingMockLLM]:
    """Build a PipelineAuditor wrapping a RecordingMockLLM."""
    llm = RecordingMockLLM()
    return PipelineAuditor(llm), llm  # type: ignore[arg-type]


def test_prior_attempts_default_is_empty_string_no_injection() -> None:
    """Default kwarg: no prior_attempts block appears in the user message."""
    auditor, llm = _make_auditor()
    auditor.audit("--- a/x.py\n+++ b/x.py\n@@ +1\n+pass\n", Path("/tmp"))
    assert len(llm.calls) == 1
    _system, user = llm.calls[0]
    assert "Prior round attempts" not in user


def test_prior_attempts_when_provided_appears_at_top() -> None:
    """Non-empty prior_attempts is injected at the TOP of the user message."""
    auditor, llm = _make_auditor()
    prior_md = (
        "## Prior round attempts (loop memory)\n\n"
        "### Round 1\n"
        "**Verdict:** FAIL\n"
        "**Findings raised:**\n"
        "- [HIGH] sql injection\n"
        "**Fixer rationale:** switched to parameterised queries\n"
    )
    auditor.audit(
        "--- a/x.py\n+++ b/x.py\n@@ +1\n+pass\n",
        Path("/tmp"),
        prior_attempts=prior_md,
    )
    _system, user = llm.calls[0]

    # Block is present.
    assert "## Prior round attempts (loop memory)" in user
    assert "sql injection" in user
    assert "switched to parameterised queries" in user

    # And it comes BEFORE the diff fence (so the auditor sees memory first).
    prior_pos = user.find("## Prior round attempts")
    diff_pos = user.find("```diff")
    assert prior_pos != -1
    assert diff_pos != -1
    assert prior_pos < diff_pos


def test_prior_attempts_precedes_sast_block() -> None:
    """When both prior_attempts and sast_findings are passed, prior comes first."""
    auditor, llm = _make_auditor()
    auditor.audit(
        "--- a/x.py\n+++ b/x.py\n@@ +1\n+pass\n",
        Path("/tmp"),
        sast_findings="- ruff E501: line too long",
        prior_attempts="## Prior round attempts (loop memory)\n\n### Round 1\n**Verdict:** FAIL\n",
    )
    _system, user = llm.calls[0]
    prior_pos = user.find("## Prior round attempts")
    sast_pos = user.find("## Pre-pass findings")
    assert prior_pos != -1
    assert sast_pos != -1
    assert prior_pos < sast_pos


def test_prior_attempts_does_not_break_diff_passthrough() -> None:
    """Diff is still present in the user message when prior_attempts is set."""
    auditor, llm = _make_auditor()
    diff = "--- a/x.py\n+++ b/x.py\n@@ +1\n+pass\n"
    auditor.audit(diff, Path("/tmp"), prior_attempts="## Prior round attempts\n### Round 1\n")
    _system, user = llm.calls[0]
    assert diff in user
