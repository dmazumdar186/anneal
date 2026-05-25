"""Security-specialist fixer: patches security findings with extra care.

Enforces principle-of-least-privilege and bans unsafe patterns (eval, raw SQL, etc.).
"""

from __future__ import annotations

from pathlib import Path

from anneal.fix.default_fixer import DefaultFixer

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SECURITY_PROMPT_PATH = _PROMPTS_DIR / "security_fixer.md"


class SecurityFixer(DefaultFixer):
    """Fixer specialized for security findings.

    Inherits all LLM-completion and diff-parsing logic from DefaultFixer.
    The system prompt instructs the LLM to follow least-privilege, add input
    validation, and never disable security checks.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Override prompt path. Defaults to ``prompts/security_fixer.md``.
    """

    def __init__(self, llm, prompt_path: Path | None = None) -> None:
        super().__init__(llm, prompt_path=prompt_path or _SECURITY_PROMPT_PATH)

    @property
    def prompt_path(self) -> Path:
        """Path to the active system prompt file."""
        return _SECURITY_PROMPT_PATH
