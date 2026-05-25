"""LLM Protocol: single abstract interface that all adapters must implement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable


class LLMError(Exception):
    """Raised by LLM adapters on transport or auth failures (timeouts, API errors, etc.)."""


@dataclass
class CacheUsage:
    """Token counts broken out by cache category (Anthropic prompt caching).

    Fields default to 0 so callers that don't use caching (OpenRouter non-Anthropic
    models, mock LLM) can omit them without changes.

    Attributes:
        cache_read_tokens:     Tokens read from the prompt cache (billed at 0.1× input).
        cache_creation_tokens: Tokens written into the prompt cache (billed at 1.25× input).
    """

    cache_read_tokens: int = field(default=0)
    cache_creation_tokens: int = field(default=0)


# Sentinel singleton meaning "no cache data available from this adapter".
NO_CACHE = CacheUsage()


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

            Adapters that support prompt caching (ClaudeLLM) also set
            ``cache_usage`` on the returned value so callers can pass it
            to ``CostTracker.add()`` for accurate weighted billing.  The
            return type is kept as ``tuple[str, int]`` for protocol compat;
            ``cache_usage`` is a separate attribute on ``ClaudeLLM`` that
            callers may read after ``complete()`` if they need it.

        Raises:
            LLMError: On any transport, auth, or provider-level failure.
        """
        ...
