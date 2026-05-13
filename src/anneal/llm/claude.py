"""Anthropic Claude adapter implementing the LLM Protocol."""

from __future__ import annotations

import os
from typing import Literal

import anthropic

from anneal.config import MissingCredentials
from anneal.llm.base import LLMError

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Respond with ONLY valid JSON. "
    "No prose, no markdown fences, no explanation outside the JSON object."
)


class ClaudeLLM:
    """LLM adapter that calls the Anthropic Claude API.

    Args:
        model: Claude model ID. Defaults to claude-sonnet-4-6.
        api_key: Anthropic API key. If None, read from ANTHROPIC_API_KEY env var.
        temperature: Sampling temperature. Defaults to 0.0 for determinism.
        max_tokens: Maximum tokens in the response. Defaults to 8192.

    Raises:
        MissingCredentials: On construction if api_key is None and
            ANTHROPIC_API_KEY is not set in the environment.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingCredentials(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your anneal .env or export it in the shell."
            )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send prompt to Claude and return (response_text, tokens_used).

        Args:
            system: System prompt.
            user: User message.
            response_format: "json" appends a strong instruction to return only
                valid JSON. Anthropic has no native JSON-mode flag in the
                messages API, so we prompt-engineer it.

        Returns:
            (response_text, total_tokens) where total_tokens = input + output.

        Raises:
            LLMError: Wraps any anthropic.APIError with the original as __cause__.
        """
        if response_format == "json":
            user = user + _JSON_INSTRUCTION

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        text = response.content[0].text
        tokens_used = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens_used
