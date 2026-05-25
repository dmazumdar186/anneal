"""Anthropic Claude adapter implementing the LLM Protocol."""

from __future__ import annotations

import os
from typing import Literal

import anthropic

from anneal.config import MissingCredentials
from anneal.llm.base import CacheUsage, LLMError

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: Respond with ONLY valid JSON. "
    "No prose, no markdown fences, no explanation outside the JSON object."
)


class ClaudeLLM:
    """LLM adapter that calls the Anthropic Claude API.

    This adapter enables Anthropic prompt caching on the system prompt by
    attaching ``cache_control={"type": "ephemeral"}`` to the system block.
    On rounds 2+ the system prompt (the 4.5 KB audit prompt) is served from
    the cache at 0.1× the normal input price instead of 1×, cutting per-round
    cost by ~5–10×.

    After each ``complete()`` call the cache token counts are available via
    ``self.last_cache_usage`` (a ``CacheUsage`` dataclass). Pass them to
    ``CostTracker.add()`` to get accurate weighted billing.

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
        # Updated after every complete() call; callers read this for cache-aware billing.
        self.last_cache_usage: CacheUsage = CacheUsage()

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Send prompt to Claude and return (response_text, tokens_used).

        The system prompt is sent with ``cache_control={"type": "ephemeral"}``
        so Anthropic caches it across calls within the same TTL window (5 min).
        On cache hits, ``last_cache_usage.cache_read_tokens`` is non-zero and
        the caller should pass it to ``CostTracker.add()`` for accurate pricing.

        Args:
            system: System prompt.
            user: User message.
            response_format: "json" appends a strong instruction to return only
                valid JSON. Anthropic has no native JSON-mode flag in the
                messages API, so we prompt-engineer it.

        Returns:
            (response_text, total_tokens) where total_tokens = input_tokens +
            cache_read_input_tokens + cache_creation_input_tokens + output_tokens
            (i.e. the full token sum as reported by the API).

        Side-effect:
            Sets ``self.last_cache_usage`` with the cache breakdown for this call.

        Raises:
            LLMError: Wraps any anthropic.APIError with the original as __cause__.
        """
        if response_format == "json":
            user = user + _JSON_INSTRUCTION

        # Wrap system prompt in a content block with cache_control so Anthropic
        # caches it for subsequent calls within the 5-minute TTL window.
        system_block: list[dict] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_block,  # type: ignore[arg-type]
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.last_cache_usage = CacheUsage(
            cache_read_tokens=cache_read,
            cache_creation_tokens=cache_creation,
        )

        text = response.content[0].text
        # Total tokens = all categories summed (matches old behaviour when cache=0)
        tokens_used = (
            usage.input_tokens
            + cache_read
            + cache_creation
            + usage.output_tokens
        )
        return text, tokens_used
