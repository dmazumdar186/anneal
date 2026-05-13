"""Deterministic mock LLM for unit tests — no API calls, no cost."""

from __future__ import annotations

from typing import Literal


class DeterministicMockLLM:
    """Mock LLM that returns pre-configured responses in sequence.

    Used in unit tests to drive the loop without real API calls.
    """

    def __init__(self, responses: list[str]) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")

    def complete(
        self,
        system: str,
        user: str,
        response_format: Literal["text", "json"] = "text",
    ) -> tuple[str, int]:
        """Return the next pre-configured response and an arbitrary token count."""
        raise NotImplementedError("anneal v0.0.1: not yet implemented")
