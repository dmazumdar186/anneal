"""Deterministic mock LLM for unit tests — no API calls, no cost."""

from __future__ import annotations

from typing import Literal


class DeterministicMockLLM:
    """Mock LLM that returns pre-configured responses in sequence.

    Used in unit tests to drive the loop without real API calls.

    Each element of `responses` can be:
    - str: response text, tokens_used defaults to 1000
    - tuple[str, int]: (response_text, tokens_used)

    Raises IndexError (not a silent empty string) when the response queue is
    exhausted — this surfaces test bugs where more LLM calls are made than
    anticipated.

    Example::

        mock = DeterministicMockLLM([
            ("**Verdict:** FAIL\\n### Issues Found\\n...", 2500),
            ("**Verdict:** PASS", 800),
        ])
        text, tokens = mock.complete(system="...", user="...")
        assert tokens == 2500
    """

    def __init__(self, responses: list[str | tuple[str, int]]) -> None:
        self._original = list(responses)
        self._queue: list[str | tuple[str, int]] = list(responses)

    def complete(
        self,
        system: str,  # noqa: ARG002
        user: str,  # noqa: ARG002
        response_format: Literal["text", "json"] = "text",  # noqa: ARG002
    ) -> tuple[str, int]:
        """Return the next pre-configured response and token count.

        The system, user, and response_format arguments are intentionally
        ignored — the mock returns pre-configured responses regardless of input.

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
            text, tokens = item
            return text, tokens
        return item, 1000

    def reset(self) -> None:
        """Restore the response queue to its original state."""
        self._queue = list(self._original)

    def remaining(self) -> int:
        """Return the number of responses remaining in the queue."""
        return len(self._queue)
