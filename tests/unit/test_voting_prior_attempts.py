"""Unit tests for VotingAuditor forwarding prior_attempts to every sample.

Covers:
  - Single-sample fast path: prior_attempts forwarded once
  - Multi-sample: every sample receives the same prior_attempts kwarg
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from anneal.audit.base import AuditReport
from anneal.audit.voting import VotingAuditor


class RecordingAuditor:
    """Thread-safe auditor that captures every kwargs payload it receives."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.calls: list[dict[str, str]] = []

    def audit(
        self,
        diff: str,  # noqa: ARG002
        repo_root: Path,  # noqa: ARG002
        *,
        sast_findings: str = "",
        repograph_context: str = "",
        semantic_summary: str = "",
        prior_attempts: str = "",
    ) -> AuditReport:
        with self._lock:
            self.calls.append(
                {
                    "sast_findings": sast_findings,
                    "repograph_context": repograph_context,
                    "semantic_summary": semantic_summary,
                    "prior_attempts": prior_attempts,
                }
            )
        return AuditReport(
            verdict="PASS",
            findings=[],
            silent_drops=[],
            logic_disagreements=[],
            summary="",
            raw_markdown="**Verdict:** PASS",
            tokens_used=100,
        )


def test_single_sample_forwards_prior_attempts() -> None:
    """samples=1 fast path still forwards the kwarg."""
    base = RecordingAuditor()
    voting = VotingAuditor(base, samples=1, vote_threshold=1)
    prior = "## Prior round attempts\n### Round 1\n**Verdict:** FAIL\n"

    voting.audit("diff", Path("/tmp"), prior_attempts=prior)
    assert len(base.calls) == 1
    assert base.calls[0]["prior_attempts"] == prior


def test_multi_sample_forwards_prior_attempts_to_every_sample() -> None:
    """Each of N samples receives the same prior_attempts kwarg."""
    base = RecordingAuditor()
    voting = VotingAuditor(base, samples=3, vote_threshold=2)
    prior = "## Prior round attempts\n### Round 7\n**Verdict:** WARNINGS\n"

    voting.audit("diff", Path("/tmp"), prior_attempts=prior)

    assert len(base.calls) == 3
    for call in base.calls:
        assert call["prior_attempts"] == prior


def test_omitted_prior_attempts_defaults_to_empty() -> None:
    """Caller may omit prior_attempts; default empty propagates through."""
    base = RecordingAuditor()
    voting = VotingAuditor(base, samples=2, vote_threshold=1)
    voting.audit("diff", Path("/tmp"))
    for call in base.calls:
        assert call["prior_attempts"] == ""
