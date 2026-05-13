"""Default fixer: generates minimal patches to address auditor findings.

parse_patch_response is exposed as a standalone function for unit tests.

Example (parser)::

    >>> text = '''```diff
    ... # rationale: fix off-by-one in loop bound
    ... --- a/src/foo.py
    ... +++ b/src/foo.py
    ... @@ -10,7 +10,7 @@
    ...  def items(n):
    ... -    for i in range(n):
    ... +    for i in range(n + 1):
    ...          yield i
    ... ```'''
    >>> patch = parse_patch_response(text, tokens_used=300)
    >>> patch.rationale
    'fix off-by-one in loop bound'
    >>> '--- a/src/foo.py' in patch.unified_diff
    True
"""

from __future__ import annotations

import re
from pathlib import Path

from anneal.audit.base import AuditReport
from anneal.fix.base import Patch
from anneal.llm.base import LLM, LLMError

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPTS_DIR / "default_fixer.md"

_FENCE_RE = re.compile(
    r"```diff\s*\n(.*?)```",
    re.DOTALL,
)
_RATIONALE_RE = re.compile(r"^#\s*rationale:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_patch_response(text: str, tokens_used: int) -> Patch:
    """Extract rationale and unified diff from a fixer LLM response.

    Expects a single ```diff fenced block whose first non-blank line is
    ``# rationale: <text>``. The diff body is everything after that line.

    Args:
        text: Raw LLM response text.
        tokens_used: Token count to embed in the returned Patch.

    Returns:
        Patch with rationale, unified_diff, tokens_used, and raw_response.

    Raises:
        LLMError: If no ```diff fence is found in the response.

    Example::

        patch = parse_patch_response(
            "```diff\\n# rationale: fix null check\\n--- a/x.py\\n+++ b/x.py\\n```",
            tokens_used=100,
        )
        assert patch.rationale == "fix null check"
    """
    fence_m = _FENCE_RE.search(text)
    if not fence_m:
        raise LLMError(
            "Fixer did not return a valid diff block. "
            "Response must contain a ```diff ... ``` fenced code block."
        )

    fence_body = fence_m.group(1)

    # Extract rationale from the first matching comment line
    rationale_m = _RATIONALE_RE.search(fence_body)
    rationale = rationale_m.group(1).strip() if rationale_m else ""

    # Diff body: everything in the fence except the rationale line
    diff_lines = []
    for line in fence_body.splitlines(keepends=True):
        if _RATIONALE_RE.match(line):
            continue
        diff_lines.append(line)

    unified_diff = "".join(diff_lines).strip()

    return Patch(
        unified_diff=unified_diff,
        rationale=rationale,
        tokens_used=tokens_used,
        raw_response=text,
    )


class DefaultFixer:
    """Built-in fixer that turns AuditReport findings into unified-diff patches.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Path to the system prompt markdown. Defaults to the bundled
            fix/prompts/default_fixer.md.
    """

    def __init__(self, llm: LLM, prompt_path: Path | None = None) -> None:
        self._llm = llm
        self._prompt = _load_prompt(prompt_path or _DEFAULT_PROMPT_PATH)

    def fix(self, report: AuditReport, current_diff: str, repo_root: Path) -> Patch:  # noqa: ARG002
        """Generate a Patch addressing the findings in report.

        Args:
            report: The AuditReport from the most recent audit pass.
            current_diff: The current unified diff under audit (for context).
            repo_root: Repository root (available for context; not used by the
                base fixer but part of the Fixer Protocol).

        Returns:
            Parsed Patch with unified_diff and rationale.

        Raises:
            LLMError: If the LLM response does not contain a valid diff block.
        """
        user_msg = (
            "## Audit Report\n\n"
            f"{report.raw_markdown}\n\n"
            "## Current Diff Under Audit\n\n"
            "```diff\n"
            f"{current_diff}\n"
            "```\n\n"
            "Now produce a unified diff that fixes the issues listed in the audit report. "
            "Follow the output format exactly: a single ```diff fenced block with a "
            "# rationale: comment on the first line."
        )
        response_text, tokens_used = self._llm.complete(
            system=self._prompt,
            user=user_msg,
            response_format="text",
        )
        return parse_patch_response(response_text, tokens_used)
