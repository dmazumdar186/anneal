"""Blue agent: audits + patches the diff, addressing any open Red attacks.

Composes the DefaultFixer's parse_patch_response internally so the output
format is identical to the classic fixer (unified diff with # rationale: header).
"""

from __future__ import annotations

import logging
from pathlib import Path

from anneal.adversarial.base import Attack, BlueTurnOutput
from anneal.fix.base import Patch
from anneal.fix.default_fixer import parse_patch_response
from anneal.llm.base import LLM, LLMError

_log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPTS_DIR / "blue.md"

# A unified diff with only whitespace / empty hunks is treated as "nothing to do".
_EMPTY_HUNK_MARKERS = ("--- ", "+++ ", "@@ ")


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _diff_has_hunks(unified_diff: str) -> bool:
    """Return True if the diff contains at least one real hunk line (+ or -)."""
    for line in unified_diff.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("---", "+++")):
            return True
    return False


def _format_open_attacks(open_attacks: list[Attack]) -> str:
    """Render open_attacks as a structured block for Blue's user message."""
    if not open_attacks:
        return "## Open Red Attacks\n\n(none)"

    lines = ["## Open Red Attacks (you must address these)\n"]
    for i, atk in enumerate(open_attacks, 1):
        lines.append(f"### Attack {i}")
        lines.append(f"- kind: {atk.kind}")
        lines.append(f"- target_files: {', '.join(atk.target_files)}")
        if atk.kind == "test":
            lines.append(f"- test_path: {atk.test_path}")
            lines.append(f"- rationale: {atk.rationale}")
        else:
            lines.append(f"- severity: {atk.severity}")
            lines.append(f"- claim: {atk.claim}")
            lines.append(f"- evidence: {atk.evidence}")
            if atk.expected:
                lines.append(f"- expected: {atk.expected}")
            if atk.actual:
                lines.append(f"- actual: {atk.actual}")
            lines.append(f"- rationale: {atk.rationale}")
        lines.append("")
    return "\n".join(lines)


class Blue:
    """Blue defender. Audits + patches the diff, addressing any open Red attacks.

    Composes PipelineAuditor and DefaultFixer internally. The output format is
    identical to the classic fixer (unified diff with ``# rationale:`` header).

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Path to the system prompt markdown. Defaults to the bundled
            adversarial/prompts/blue.md.
    """

    def __init__(self, llm: LLM, prompt_path: Path | None = None) -> None:
        self._llm = llm
        self._prompt = _load_prompt(prompt_path or _DEFAULT_PROMPT_PATH)

    def harden(
        self,
        diff: str,
        repo_root: Path,  # noqa: ARG002  # reserved for future file-read enrichment
        open_attacks: list[Attack],
    ) -> BlueTurnOutput:
        """Audit the diff AND address open Red attacks. Returns a single combined patch.

        Args:
            diff: Current unified diff under audit.
            repo_root: Worktree path. Reserved for future file-read enrichment;
                Blue only sees the diff in this implementation.
            open_attacks: Attacks that landed in previous rounds and Blue hasn't
                yet addressed.

        Returns:
            BlueTurnOutput with:
            - ``patch``: a Patch (unified diff + rationale) or None if Blue
              determines nothing needs changing.
            - ``rationale``: one-line summary.
            - ``tokens_used``: total tokens consumed.
        """
        attacks_block = _format_open_attacks(open_attacks)

        user_msg = (
            "## Current Diff Under Review\n\n"
            "```diff\n"
            f"{diff}\n"
            "```\n\n"
            f"{attacks_block}\n\n"
            "Address all open attacks AND any other audit findings you identify. "
            "Return a single unified diff. "
            "Follow the output format exactly: a single ```diff fenced block with a "
            "# rationale: comment on the first line."
        )

        response_text, tokens_used = self._llm.complete(
            system=self._prompt,
            user=user_msg,
            response_format="text",
        )

        patch: Patch | None
        rationale: str

        try:
            patch = parse_patch_response(response_text, tokens_used)
        except LLMError as exc:
            _log.warning("Blue returned no valid diff block (%s) — patch=None this round", exc)
            patch = None
            rationale = "blue produced no valid diff"
        else:
            if not _diff_has_hunks(patch.unified_diff):
                _log.debug("Blue diff has no real hunks — treating as nothing-to-do")
                rationale = patch.rationale or "no issues found"
                patch = None
            else:
                rationale = patch.rationale or "blue hardening applied"

        return BlueTurnOutput(
            patch=patch,
            rationale=rationale,
            tokens_used=tokens_used,
        )
