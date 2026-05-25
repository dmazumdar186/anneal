"""Pipeline auditor: mirrors the AM pipeline-auditor.md prompt and schema.

Parses the structured markdown output produced by the pipeline_auditor.md prompt
into a typed AuditReport.

Parser contract
---------------
The LLM is instructed to produce a report matching this exact structure::

    ## Audit Report: ...

    **Verdict: PASS / FAIL / WARNINGS**

    ### Issues Found
    - [Severity: HIGH] summary text
      Impact: ...
      Recommended fix: ...

    ### Silent Drops
    - item description
    (or "None detected")

    ### Logic Disagreements
    - item description
    (or "None detected")

    ### Summary
    ...free text...

Missing sections default to empty lists. Missing verdict defaults to FAIL.
The full LLM response is always stored in raw_markdown regardless of parse success.

Example (doctest-style)::

    >>> md = '''
    ... **Verdict:** PASS
    ...
    ... ### Issues Found
    ...
    ... ### Silent Drops
    ... None detected
    ...
    ... ### Logic Disagreements
    ... None detected
    ...
    ... ### Summary
    ... All checks passed.
    ... '''
    >>> report = parse_audit_markdown(md, tokens_used=100)
    >>> report.verdict
    'PASS'
    >>> report.findings
    []
    >>> report.summary
    'All checks passed.'
"""

from __future__ import annotations

import re
from pathlib import Path

from anneal.audit.base import AuditReport, Finding, Severity, Verdict
from anneal.llm.base import LLM

# ── Prompt loader ──────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPTS_DIR / "pipeline_auditor.md"


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Regex patterns ─────────────────────────────────────────────────────────────

_VERDICT_RE = re.compile(
    r"\*\*Verdict[:\s]+\**\s*(PASS|FAIL|WARNINGS)\b",
    re.IGNORECASE,
)

# Matches "- [Severity: HIGH] summary text" with optional file:line prefix
_FINDING_HEADER_RE = re.compile(
    r"^\s*-\s*\[Severity:\s*(CRITICAL|HIGH|MEDIUM|LOW|INFO)\]\s*(.+)$",
    re.IGNORECASE,
)
_IMPACT_RE = re.compile(r"^\s*Impact:\s*(.+)$", re.IGNORECASE)
_FIX_RE = re.compile(r"^\s*Recommended fix:\s*(.+)$", re.IGNORECASE)

# Section delimiters
_ISSUES_RE = re.compile(r"^###\s*Issues Found", re.IGNORECASE | re.MULTILINE)
_SILENT_RE = re.compile(r"^###\s*Silent Drops", re.IGNORECASE | re.MULTILINE)
_LOGIC_RE = re.compile(r"^###\s*Logic Disagreements", re.IGNORECASE | re.MULTILINE)
_SUMMARY_RE = re.compile(r"^###\s*Summary", re.IGNORECASE | re.MULTILINE)
_NEXT_SECTION_RE = re.compile(r"^###\s+\S", re.MULTILINE)

_NONE_DETECTED_RE = re.compile(r"^\s*none\s+detected\s*$", re.IGNORECASE)


def _extract_section(md: str, section_re: re.Pattern) -> str | None:
    """Return the text of a ### section, up to the next ### heading or end of string."""
    m = section_re.search(md)
    if not m:
        return None
    start = m.end()
    # Find next ### heading after this one
    rest = md[start:]
    next_m = _NEXT_SECTION_RE.search(rest)
    if next_m:
        return rest[: next_m.start()].strip()
    return rest.strip()


def _parse_bullet_list(text: str) -> list[str]:
    """Parse a simple bullet list; return [] if "None detected"."""
    if _NONE_DETECTED_RE.match(text):
        return []
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
        elif stripped.startswith("* "):
            items.append(stripped[2:].strip())
    return items


def _parse_findings(issues_text: str) -> list[Finding]:
    """Parse the Issues Found section into a list of Finding objects."""
    if not issues_text:
        return []
    if _NONE_DETECTED_RE.match(issues_text):
        return []

    findings: list[Finding] = []
    lines = issues_text.splitlines()
    i = 0
    while i < len(lines):
        header_m = _FINDING_HEADER_RE.match(lines[i])
        if header_m:
            raw_severity = header_m.group(1).upper()
            # Normalise CRITICAL → HIGH if not in Severity (protocol allows CRITICAL)
            severity: Severity = raw_severity  # type: ignore[assignment]
            summary = header_m.group(2).strip()
            impact = ""
            fix = ""
            # Consume following indented lines for Impact / Recommended fix
            j = i + 1
            while j < len(lines):
                impact_m = _IMPACT_RE.match(lines[j])
                fix_m = _FIX_RE.match(lines[j])
                if impact_m:
                    impact = impact_m.group(1).strip()
                elif fix_m:
                    fix = fix_m.group(1).strip()
                elif lines[j].strip() and not lines[j].strip().startswith("-"):
                    # continuation of previous field (multi-line)
                    pass
                else:
                    break
                j += 1

            # Parse optional file:line from summary (e.g. "src/foo.py:42: issue")
            file_str = ""
            line_start = None
            file_m = re.match(r"^([^\s:]+\.py):(\d+):\s*(.*)", summary)
            if file_m:
                file_str = file_m.group(1)
                line_start = int(file_m.group(2))
                summary = file_m.group(3)

            findings.append(
                Finding(
                    severity=severity,
                    summary=summary,
                    file=file_str,
                    impact=impact,
                    recommended_fix=fix,
                    line_start=line_start,
                )
            )
            i = j
        else:
            i += 1

    return findings


# ── Public parser ──────────────────────────────────────────────────────────────

def parse_audit_markdown(md: str, tokens_used: int) -> AuditReport:
    """Parse a pipeline-auditor markdown response into a typed AuditReport.

    Defensive: missing sections → empty lists, missing verdict → FAIL.
    Always populates raw_markdown with the full input string.

    Args:
        md: Raw markdown text returned by the LLM.
        tokens_used: Token count to embed in the report.

    Returns:
        AuditReport with all fields populated.

    Example::

        report = parse_audit_markdown(
            "**Verdict:** PASS\\n### Issues Found\\n### Silent Drops\\nNone detected\\n"
            "### Logic Disagreements\\nNone detected\\n### Summary\\nLooks good.",
            tokens_used=500,
        )
        assert report.verdict == "PASS"
        assert report.findings == []
    """
    # Verdict
    verdict_m = _VERDICT_RE.search(md)
    if verdict_m:
        raw_verdict = verdict_m.group(1).upper()
        verdict: Verdict = raw_verdict  # type: ignore[assignment]
    else:
        verdict = "FAIL"

    # Issues Found
    issues_text = _extract_section(md, _ISSUES_RE) or ""
    findings = _parse_findings(issues_text)

    # Silent Drops
    silent_text = _extract_section(md, _SILENT_RE) or ""
    silent_drops = _parse_bullet_list(silent_text)

    # Logic Disagreements
    logic_text = _extract_section(md, _LOGIC_RE) or ""
    logic_disagreements = _parse_bullet_list(logic_text)

    # Summary
    summary_text = _extract_section(md, _SUMMARY_RE) or ""

    return AuditReport(
        verdict=verdict,
        findings=findings,
        silent_drops=silent_drops,
        logic_disagreements=logic_disagreements,
        summary=summary_text,
        raw_markdown=md,
        tokens_used=tokens_used,
    )


# ── PipelineAuditor class ──────────────────────────────────────────────────────

class PipelineAuditor:
    """Built-in auditor ported from the AntiGravity pipeline-auditor.md directive.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Path to the system prompt markdown. Defaults to the bundled
            audit/prompts/pipeline_auditor.md.
    """

    def __init__(self, llm: LLM, prompt_path: Path | None = None) -> None:
        self._llm = llm
        self._prompt = _load_prompt(prompt_path or _DEFAULT_PROMPT_PATH)

    def audit(
        self,
        diff: str,
        repo_root: Path,  # noqa: ARG002  # Protocol requires it; unused by base impl
        *,
        sast_findings: str = "",
        repograph_context: str = "",
        semantic_summary: str = "",
    ) -> AuditReport:
        """Run the pipeline-auditor prompt against diff and parse findings.

        Args:
            diff:              Unified diff string to audit.
            repo_root:         Path to the repository root (available for context;
                               not used by the base auditor but part of the Protocol).
            sast_findings:     Optional pre-pass SAST output as a markdown string.
                               When non-empty, a "## Pre-pass findings" section is
                               prepended to the user message so the LLM can focus
                               on issues the deterministic pass did not already catch.
            repograph_context: Optional repo-graph caller context as a markdown
                               string.  When non-empty, a "## Repo-graph context"
                               section is injected between SAST findings and the
                               diff so the auditor can reason about cross-file impact.
            semantic_summary:  Optional AST-derived semantic diff summary as a
                               markdown string.  When non-empty, injected between
                               the repo-graph context and the diff so the auditor
                               can skip cosmetic hunks and prioritise structural
                               changes.

        Returns:
            Parsed AuditReport.
        """
        sast_block = ""
        if sast_findings:
            sast_block = (
                "## Pre-pass findings (deterministic SAST — DO NOT re-flag these)\n\n"
                f"{sast_findings}\n\n"
                "---\n\n"
            )

        repograph_block = ""
        if repograph_context:
            repograph_block = (
                "## Repo-graph context — callers of modified symbols\n\n"
                f"{repograph_context}\n\n"
                "---\n\n"
            )

        semantic_block = ""
        if semantic_summary:
            semantic_block = (
                f"{semantic_summary}\n\n"
                "---\n\n"
            )

        user_msg = (
            f"{sast_block}"
            f"{repograph_block}"
            f"{semantic_block}"
            "Below is the diff to audit. Review it carefully according to your instructions.\n\n"
            "```diff\n"
            f"{diff}\n"
            "```\n\n"
            "Now run your audit and return a report in the specified format."
        )
        response_text, tokens_used = self._llm.complete(
            system=self._prompt,
            user=user_msg,
            response_format="text",
        )
        return parse_audit_markdown(response_text, tokens_used)
