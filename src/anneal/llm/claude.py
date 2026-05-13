"""Anthropic Claude adapter implementing the LLM Protocol."""

from __future__ import annotations

from typing import Literal


class ClaudeLLM:
    """LLM adapter that calls the Anthropic Claude API."""

    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str | None = None) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send prompt to Claude and return (response_text, tokens_used)."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
