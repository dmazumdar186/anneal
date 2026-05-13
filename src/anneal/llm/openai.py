"""OpenAI adapter implementing the LLM Protocol."""

from __future__ import annotations

from typing import Literal


class OpenAILLM:
    """LLM adapter that calls the OpenAI API."""

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send prompt to OpenAI and return (response_text, tokens_used)."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
