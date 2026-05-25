"""Test-gap fixer: adds or extends tests to expose audit findings.

Never modifies production code — only touches test files.
"""

from __future__ import annotations

from pathlib import Path

from anneal.fix.default_fixer import DefaultFixer

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_TEST_PROMPT_PATH = _PROMPTS_DIR / "test_fixer.md"


class TestFixer(DefaultFixer):
    """Fixer that writes new tests to expose flagged issues.

    Inherits all LLM-completion and diff-parsing logic from DefaultFixer.
    Only the system prompt is swapped — constraining the LLM to only touch
    test files and to add ``# exposes:`` comments above each new test.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Override prompt path. Defaults to ``prompts/test_fixer.md``.
    """

    def __init__(self, llm, prompt_path: Path | None = None) -> None:
        super().__init__(llm, prompt_path=prompt_path or _TEST_PROMPT_PATH)

    @property
    def prompt_path(self) -> Path:
        """Path to the active system prompt file."""
        return _TEST_PROMPT_PATH
