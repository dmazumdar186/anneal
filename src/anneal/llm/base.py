"""LLM Protocol: single abstract interface that all adapters must implement."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    """Minimal LLM interface consumed by loops, auditors, fixers, and adversarial agents."""

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send a prompt and return (response_text, tokens_used)."""
        ...
