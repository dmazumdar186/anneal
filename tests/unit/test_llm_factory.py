"""Unit tests for build_llm() in anneal.llm.factory.

No real API calls are made — tests only verify type and exception behavior.
"""

from __future__ import annotations

import pytest

from anneal.config import MissingCredentials
from anneal.llm.claude import ClaudeLLM
from anneal.llm.factory import build_llm
from anneal.llm.openrouter import OpenRouterLLM


def test_build_llm_anthropic() -> None:
    """build_llm('anthropic', ...) with a key present returns a ClaudeLLM instance."""
    llm = build_llm(
        "anthropic",
        "claude-haiku-4-5-20251001",
        {"ANTHROPIC_API_KEY": "sk-ant-test"},
    )
    assert isinstance(llm, ClaudeLLM)


def test_build_llm_openrouter() -> None:
    """build_llm('openrouter', ...) with a key present returns an OpenRouterLLM instance."""
    llm = build_llm(
        "openrouter",
        "google/gemini-2.5-flash",
        {"OPENROUTER_API_KEY": "sk-or-test"},
    )
    assert isinstance(llm, OpenRouterLLM)


def test_build_llm_missing_anthropic_key_raises() -> None:
    """build_llm('anthropic', ...) with empty dict raises MissingCredentials."""
    with pytest.raises(MissingCredentials, match="ANTHROPIC_API_KEY"):
        build_llm("anthropic", "claude-haiku-4-5-20251001", {})


def test_build_llm_missing_openrouter_key_raises() -> None:
    """build_llm('openrouter', ...) with empty dict raises MissingCredentials."""
    with pytest.raises(MissingCredentials, match="OPENROUTER_API_KEY"):
        build_llm("openrouter", "google/gemini-2.5-flash", {})


def test_build_llm_unknown_provider_raises() -> None:
    """build_llm with an unknown provider string raises ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        build_llm("madeup", "some-model", {})  # type: ignore[arg-type]
