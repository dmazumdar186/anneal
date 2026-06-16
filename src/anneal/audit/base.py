"""Auditor Protocol, severity/verdict types, Finding/AuditReport/PriorAttempt dataclasses."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Verdict = Literal["PASS", "FAIL", "WARNINGS"]


# Hard cap on how many prior rounds the formatter will include in one prompt,
# regardless of how long the loop has run. Older rounds are dropped; the most
# recent N are kept. Caps the user_msg size so prior_attempts can't blow context.
PRIOR_ATTEMPTS_MAX_ROUNDS = 5

# Per-rationale character cap. Fixer rationales can be paragraphs; we keep them
# bounded so the prior-attempts block stays readable and cheap.
PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP = 600


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


@dataclass(frozen=True)
class PriorAttempt:
    """One historical round captured for the next round's auditor (loop-with-memory).

    The loop appends one of these per FAIL/WARNINGS round (PASS rounds carry no
    fixer rationale, so they're not interesting to the next round). The auditor
    in round N+1 reads these and is instructed to:
      - not re-raise findings the latest fix actually resolves,
      - re-raise findings the fix tried-and-failed to address,
      - not propose approaches the fixer already tried.

    Fields
    ------
    round_num         1-based round number this attempt was captured at.
    verdict           Verdict the auditor returned that round.
    finding_summaries One-line "[SEVERITY] summary" strings for every finding
                      raised in that round. Truncated by the formatter, not here.
    fixer_rationale   The Patch.rationale string the fixer produced that round.
                      "" if the round was dry-run or the fixer produced no patch
                      (patch_conflict, budget exhaustion mid-fix).
    """

    round_num: int
    verdict: Verdict
    finding_summaries: list[str]
    fixer_rationale: str = ""


def format_prior_attempts(history: list["PriorAttempt"]) -> str:
    """Format a prior-round history as a markdown block for the auditor's user message.

    Returns "" when history is empty (caller can branch cheaply on that).
    Keeps only the most recent ``PRIOR_ATTEMPTS_MAX_ROUNDS`` entries; older
    rounds are silently dropped to bound prompt size. Per-rationale length
    is capped at ``PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP`` characters with an
    ellipsis suffix when truncated.

    Example::

        attempts = [
            PriorAttempt(1, "FAIL", ["[HIGH] sql injection"], "switched to params"),
            PriorAttempt(2, "WARNINGS", ["[LOW] missing docstring"], "added docstring"),
        ]
        block = format_prior_attempts(attempts)
        # → markdown block with both rounds, suitable for prompt injection.
    """
    if not history:
        return ""

    kept = history[-PRIOR_ATTEMPTS_MAX_ROUNDS:]
    lines: list[str] = []
    lines.append("## Prior round attempts (loop memory)")
    lines.append("")
    lines.append(
        "Earlier rounds audited a previous version of this diff. Use the "
        "summaries below to:"
    )
    lines.append(
        "- AVOID re-raising findings that the latest fix actually resolves "
        "in the diff under review."
    )
    lines.append(
        "- DO re-raise findings the fix tried to address but did not fully "
        "fix (the issue must still be present in the current diff)."
    )
    lines.append(
        "- AVOID proposing approaches the fixer already tried in an earlier "
        "round, unless you can explain concretely why a previous attempt failed "
        "and how a new attempt would differ."
    )
    lines.append("")

    if len(history) > len(kept):
        skipped = len(history) - len(kept)
        lines.append(
            f"_(omitted {skipped} earlier round(s) — only the most recent "
            f"{len(kept)} are shown)_"
        )
        lines.append("")

    for attempt in kept:
        lines.append(f"### Round {attempt.round_num}")
        lines.append(f"**Verdict:** {attempt.verdict}")
        if attempt.finding_summaries:
            lines.append("**Findings raised:**")
            for summary in attempt.finding_summaries:
                lines.append(f"- {summary}")
        else:
            lines.append("**Findings raised:** none")
        rationale = attempt.fixer_rationale.strip()
        if rationale:
            if len(rationale) > PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP:
                rationale = rationale[: PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP - 1].rstrip() + "…"
            lines.append(f"**Fixer rationale:** {rationale}")
        else:
            lines.append("**Fixer rationale:** _(no patch applied this round)_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


@runtime_checkable
class Auditor(Protocol):
    """Protocol that all auditor implementations must satisfy."""

    def audit(
        self,
        diff: str,
        repo_root: Path,
        *,
        sast_findings: str = "",
        repograph_context: str = "",
        semantic_summary: str = "",
        prior_attempts: str = "",
    ) -> AuditReport:
        """Audit a diff and return a structured AuditReport.

        Args:
            diff:              Unified diff string to audit.
            repo_root:         Path to the repository root.
            sast_findings:     Optional pre-pass SAST output as a markdown string.
                               When non-empty, the auditor should treat these as
                               known issues and focus on what SAST cannot catch.
            repograph_context: Optional repo-graph caller context as a markdown
                               string.  When non-empty, contains the callers of
                               every modified symbol so the auditor can detect
                               cross-file breakage.
            semantic_summary:  Optional AST-derived semantic diff summary as a
                               markdown string.  When non-empty, the auditor can
                               use it to skip cosmetic hunks and focus on
                               structural changes (added/removed/renamed symbols).
            prior_attempts:    Optional formatted markdown block describing prior
                               rounds (findings + fixer rationales). When non-empty,
                               the auditor should avoid re-raising issues the
                               latest fix actually resolves and avoid proposing
                               approaches the fixer already tried. Produced by
                               ``format_prior_attempts(history)``.
        """
        ...
