"""Security-specialist Red agent: finds OWASP Top 10 / CWE Top 25 vulnerabilities."""

from __future__ import annotations

from pathlib import Path

from anneal.adversarial.red import Red

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SECURITY_PROMPT_PATH = _PROMPTS_DIR / "security_red.md"


class SecurityRed(Red):
    """Red attacker specializing in security vulnerabilities.

    Draws from OWASP Top 10 and CWE Top 25 to find injection flaws,
    auth/authz bypasses, secret exposure, path traversal, SSRF, weak
    crypto, and related security bugs.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Override the security prompt path. Defaults to
            ``adversarial/prompts/security_red.md``.
    """

    def __init__(self, llm, prompt_path: Path | None = None) -> None:  # type: ignore[override]
        super().__init__(llm, prompt_path=prompt_path or _SECURITY_PROMPT_PATH)
