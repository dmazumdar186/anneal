"""LLM Protocol: single abstract interface that all adapters must implement."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


class LLMError(Exception):
    """Raised by LLM adapters on transport or auth failures (timeouts, API errors, etc.)."""


@runtime_checkable
class LLM(Protocol):
    """Minimal LLM interface consumed by loops, auditors, fixers, and adversarial agents.

    All adapters must implement exactly one method: complete().
    The protocol is runtime-checkable so isinstance(obj, LLM) works in tests.
    """

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send a prompt and return (response_text, tokens_used).

        Args:
            system: System prompt / role instructions.
            user: User message (the diff, findings, etc.).
            response_format: "text" for freeform markdown; "json" to request
                             structured JSON output (adapter may add a prompt
                             instruction or set a native JSON mode flag).

        Returns:
            (response_text, tokens_used) where tokens_used is the total of
            input + output tokens consumed for billing/budget tracking.

        Raises:
            LLMError: On any transport, auth, or provider-level failure.
        """
        ...
