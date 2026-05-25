"""SAST base types: SastFinding dataclass, SastRunner Protocol, and markdown formatter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

SastSeverity = Literal["critical", "high", "medium", "low", "info"]


@dataclass(frozen=True)
class SastFinding:
    """A single issue identified by a SAST tool.

    Attributes:
        severity: Issue severity level.
        file:     Path to the file containing the issue (relative to worktree).
        line:     1-based line number where the issue was found.
        rule_id:  Tool-specific rule identifier (e.g. "S101", "F401").
        message:  Human-readable description of the issue.
        tool:     Name of the tool that produced this finding (e.g. "ruff", "semgrep").
    """

    severity: SastSeverity
    file: str
    line: int
    rule_id: str
    message: str
    tool: str


@runtime_checkable
class SastRunner(Protocol):
    """Protocol that all SAST runner implementations must satisfy."""

    def run(self, worktree: Path, changed_files: list[str]) -> list[SastFinding]:
        """Run the SAST tool against the given files inside the worktree.

        Args:
            worktree:      Absolute path to the git worktree root.
            changed_files: List of file paths (relative to worktree) to analyse.
                           Runners are expected to filter to files they can handle
                           (e.g. only .py files for ruff).

        Returns:
            A list of :class:`SastFinding` objects.  Empty list if the tool is
            not installed, no files are applicable, or no issues were found.
        """
        ...


def format_findings_as_markdown(findings: list[SastFinding]) -> str:
    """Render a list of SAST findings as a bulleted markdown block.

    Suitable for injection into an LLM audit prompt so the model can focus on
    issues the deterministic pre-pass did not already catch.

    Args:
        findings: List of :class:`SastFinding` objects to render.

    Returns:
        A markdown string.  Empty string when ``findings`` is empty.

    Example output::

        ## SAST Pre-pass Findings (2 issues)

        - **[high]** `src/foo.py:12` — S101 — Use of `assert` detected (ruff)
        - **[low]** `src/foo.py:3` — F401 — `os` imported but unused (ruff)
    """
    if not findings:
        return ""

    lines: list[str] = [f"## SAST Pre-pass Findings ({len(findings)} issue{'s' if len(findings) != 1 else ''})\n"]
    for f in findings:
        lines.append(
            f"- **[{f.severity}]** `{f.file}:{f.line}` — {f.rule_id} — {f.message} ({f.tool})"
        )
    return "\n".join(lines)
