"""OpenRouter adapter implementing the LLM Protocol.

Routes requests to any OpenRouter-hosted model (Gemini, DeepSeek, Llama, OpenAI, etc.)
using the OpenAI-compatible API at https://openrouter.ai/api/v1.
"""

from __future__ import annotations

import os
from typing import Literal

import openai

from anneal.config import MissingCredentials
from anneal.llm.base import LLMError


class OpenRouterLLM:
    """LLM adapter that calls OpenRouter via the OpenAI-compatible API.

    Args:
        model: OpenRouter model slug. Defaults to google/gemini-2.5-flash.
        api_key: OpenRouter API key. If None, read from OPENROUTER_API_KEY env var.
        temperature: Sampling temperature. Defaults to 0.0 for determinism.
        max_tokens: Maximum tokens in the response. Defaults to 8192.

    Raises:
        MissingCredentials: On construction if api_key is None and
            OPENROUTER_API_KEY is not set in the environment.
    """

    def __init__(
        self,
        model: str = "google/gemini-2.5-flash",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise MissingCredentials(
                "OPENROUTER_API_KEY is not set. "
                "Add it to your anneal .env or export it in the shell. "
                "Get a key at openrouter.ai/keys."
            )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send prompt to OpenRouter and return (response_text, tokens_used).

        Args:
            system: System prompt.
            user: User message.
            response_format: "json" sets response_format={"type": "json_object"}
                on the API call (OpenAI-compatible JSON mode).

        Returns:
            (response_text, total_tokens) where total_tokens = response.usage.total_tokens.

        Raises:
            LLMError: Wraps any openai.OpenAIError with the original as __cause__.
        """
        kwargs: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "extra_headers": {
                "HTTP-Referer": "https://github.com/dmazumdar186/anneal",
                "X-Title": "anneal",
            },
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenRouter API error: {exc}") from exc

        text = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens
        return text, tokens_used
