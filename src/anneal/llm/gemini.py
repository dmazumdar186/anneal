"""Google Gemini direct adapter implementing the LLM Protocol.

Uses the ``google-genai`` SDK (unified SDK, 2025-Q1+).
Install with: pip install google-genai

If ``google-genai`` is not installed, this module will raise an ImportError at
import time with a clear message pointing at the install command.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from anneal.config import MissingCredentials
from anneal.llm.base import LLMError

logger = logging.getLogger(__name__)

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Respond with ONLY valid JSON. "
    "No prose, no markdown fences, no explanation outside the JSON object."
)

try:
    from google import genai
    from google.genai import types as _genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]


class GeminiLLM:
    """LLM adapter that calls the Google Gemini API directly via google-genai.

    Requires ``google-genai>=0.6.0``. Install with::

        pip install google-genai
        # or: pip install anneal[gemini]

    Args:
        model: Gemini model ID. Defaults to gemini-2.5-flash.
        api_key: Google Gemini API key. If None, read from GEMINI_API_KEY env var.
        temperature: Sampling temperature. Defaults to 0.0 for determinism.
        max_tokens: Maximum output tokens. Defaults to 8192.

    Raises:
        ImportError: At construction time if google-genai is not installed.
        MissingCredentials: At construction time if api_key is None and
            GEMINI_API_KEY is not set in the environment.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> None:
        if not _GENAI_AVAILABLE:
            raise ImportError(
                "The google-genai package is required for the Gemini provider but is not installed. "
                "Install it with: pip install google-genai\n"
                "Or install the anneal optional dependency group: pip install anneal[gemini]"
            )
        if api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise MissingCredentials(
                "GEMINI_API_KEY is not set. "
                "Add it to your anneal .env or export it in the shell."
            )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = genai.Client(api_key=api_key)

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
        *,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> tuple[str, int]:
        """Send prompt to Gemini and return (response_text, tokens_used).

        The system prompt is sent as a system_instruction in the GenerateContent
        config. The user message is sent as a user content part.

        Args:
            system: System prompt / role instructions.
            user: User message (the diff, findings, etc.).
            response_format: "json" appends a JSON-only instruction to the user
                message. Gemini does not have a universal JSON-mode flag via the
                google-genai SDK config, so we prompt-engineer it.
            temperature: Per-call temperature override. None falls back to
                ``self._temperature`` (the constructor default).
            seed: Optional integer seed. Forwarded to Gemini via the generation
                config when supported (google-genai SDK >= 0.6 accepts it).
                Silently ignored by SDK versions that don't support it.

        Returns:
            (response_text, tokens_used) where tokens_used = prompt_token_count
            + candidates_token_count (as reported by response.usage_metadata).

        Raises:
            LLMError: Wraps any exception from the Gemini API with the original
                as __cause__.
        """
        effective_temperature = self._temperature if temperature is None else temperature

        if response_format == "json":
            user = user + _JSON_INSTRUCTION

        # Build generation config dict; conditionally include seed if provided.
        gen_config_kwargs: dict = {
            "temperature": effective_temperature,
            "max_output_tokens": self._max_tokens,
            "system_instruction": system,
        }
        if seed is not None:
            gen_config_kwargs["seed"] = seed

        try:
            gen_config = _genai_types.GenerateContentConfig(**gen_config_kwargs)
        except TypeError:
            # Older SDK versions may not accept all kwargs — fall back without seed.
            gen_config_kwargs.pop("seed", None)
            gen_config = _genai_types.GenerateContentConfig(**gen_config_kwargs)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user,
                config=gen_config,
            )
        except Exception as exc:
            raise LLMError(f"Gemini API call failed: {exc}") from exc

        text = response.text or ""

        # Extract token counts from usage_metadata if available.
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            tokens_used = prompt_tokens + output_tokens
        else:
            # Fallback: rough approximation via character count.
            tokens_used = len(text) // 4

        return text, tokens_used
