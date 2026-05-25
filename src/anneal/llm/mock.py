"""Deterministic mock LLM for unit tests — no API calls, no cost."""

from __future__ import annotations

from typing import Literal

from anneal.llm.base import CacheUsage


class DeterministicMockLLM:
    """Mock LLM that returns pre-configured responses in sequence.

    Used in unit tests to drive the loop without real API calls.

    Each element of `responses` can be:
    - str: response text; tokens_used defaults to 1000, no cache.
    - tuple[str, int]: (response_text, tokens_used); no cache simulation.
    - tuple[str, int, CacheUsage]: (response_text, tokens_used, cache_usage);
      simulates a cache hit/write so tests can exercise cache-aware billing.

    ``last_cache_usage`` is updated after each ``complete()`` call, mirroring
    the interface of ``ClaudeLLM`` so callers can be tested without mocking.

    Raises IndexError (not a silent empty string) when the response queue is
    exhausted — this surfaces test bugs where more LLM calls are made than
    anticipated.

    Example::

        from anneal.llm.base import CacheUsage
        mock = DeterministicMockLLM([
            ("**Verdict:** FAIL\\n### Issues Found\\n...", 5000,
             CacheUsage(cache_read_tokens=4500, cache_creation_tokens=0)),
            ("**Verdict:** PASS", 800),
        ])
        text, tokens = mock.complete(system="...", user="...")
        assert tokens == 5000
        assert mock.last_cache_usage.cache_read_tokens == 4500
    """

    def __init__(self, responses: list[str | tuple[str, int] | tuple[str, int, CacheUsage]]) -> None:
        self._original = list(responses)
        self._queue: list[str | tuple[str, int] | tuple[str, int, CacheUsage]] = list(responses)
        self.last_cache_usage: CacheUsage = CacheUsage()

    def complete(
        self,
        system: str,  # noqa: ARG002
        user: str,  # noqa: ARG002
        response_format: Literal["text", "json"] = "text",  # noqa: ARG002
    ) -> tuple[str, int]:
        """Return the next pre-configured response and token count.

        The system, user, and response_format arguments are intentionally
        ignored — the mock returns pre-configured responses regardless of input.

        Side-effect:
            Sets ``self.last_cache_usage`` from the response tuple if a
            ``CacheUsage`` was provided, otherwise resets it to no-cache.

        Raises:
            IndexError: If the response queue is exhausted (test bug, not silent).
        """
        if not self._queue:
            raise IndexError(
                "DeterministicMockLLM response queue exhausted — "
                "more complete() calls were made than responses were configured."
            )
        item = self._queue.pop(0)
        if isinstance(item, tuple):
            if len(item) == 3:  # type: ignore[misc]
                text, tokens, cache = item  # type: ignore[misc]
                self.last_cache_usage = cache
                return text, tokens
            text, tokens = item  # type: ignore[misc]
            self.last_cache_usage = CacheUsage()
            return text, tokens
        self.last_cache_usage = CacheUsage()
        return item, 1000

    def reset(self) -> None:
        """Restore the response queue to its original state."""
        self._queue = list(self._original)
        self.last_cache_usage = CacheUsage()

    def remaining(self) -> int:
        """Return the number of responses remaining in the queue."""
        return len(self._queue)
