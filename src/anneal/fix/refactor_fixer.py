"""Refactor-specialist fixer: addresses maintainability and style findings.

Makes minimal, behavior-preserving refactors only. Returns an empty diff
if a behavior-preserving fix is not possible.
"""

from __future__ import annotations

from pathlib import Path

from anneal.fix.default_fixer import DefaultFixer

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_REFACTOR_PROMPT_PATH = _PROMPTS_DIR / "refactor_fixer.md"


class RefactorFixer(DefaultFixer):
    """Fixer specialized for maintainability and style findings.

    Inherits all LLM-completion and diff-parsing logic from DefaultFixer.
    The system prompt constrains the LLM to behavior-preserving changes only,
    with surgical renames and targeted extractions.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Override prompt path. Defaults to ``prompts/refactor_fixer.md``.
    """

    def __init__(self, llm, prompt_path: Path | None = None) -> None:
        super().__init__(llm, prompt_path=prompt_path or _REFACTOR_PROMPT_PATH)

    @property
    def prompt_path(self) -> Path:
        """Path to the active system prompt file."""
        return _REFACTOR_PROMPT_PATH
