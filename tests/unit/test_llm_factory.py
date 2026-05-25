"""Unit tests for build_llm() in anneal.llm.factory.

No real API calls are made — tests only verify type and exception behavior.
"""

from __future__ import annotations

import pytest

from anneal.config import MissingCredentials, resolve_tier
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


def test_build_llm_gemini_returns_gemini_llm_or_import_error() -> None:
    """build_llm('gemini', ...) with a key present returns a GeminiLLM instance.

    If google-genai is not installed in the test environment, the ImportError
    message must point at 'pip install google-genai'.
    """
    try:
        llm = build_llm(
            "gemini",
            "gemini-2.5-flash",
            {"GEMINI_API_KEY": "fake-key"},
        )
        from anneal.llm.gemini import GeminiLLM
        assert isinstance(llm, GeminiLLM)
    except ImportError as exc:
        # google-genai not installed: verify error message is actionable.
        assert "pip install google-genai" in str(exc), (
            f"ImportError message should point at 'pip install google-genai', got: {exc}"
        )


def test_build_llm_gemini_missing_key_raises() -> None:
    """build_llm('gemini', ...) with empty dict raises MissingCredentials (when SDK installed)."""
    try:
        import google.genai  # noqa: F401
    except ImportError:
        pytest.skip("google-genai not installed — skipping key-missing test")

    with pytest.raises(MissingCredentials, match="GEMINI_API_KEY"):
        build_llm("gemini", "gemini-2.5-flash", {})


def test_resolve_tier_cheap_gemini() -> None:
    """cheap-gemini tier: all roles map to gemini-2.5-flash via direct gemini provider."""
    result = resolve_tier("cheap-gemini")
    assert set(result.keys()) == {"auditor", "fixer", "red", "blue", "judge"}
    for role, spec in result.items():
        assert spec["provider"] == "gemini", f"{role} provider should be 'gemini', got {spec['provider']!r}"
        assert spec["model"] == "gemini-2.5-flash", f"{role} model should be 'gemini-2.5-flash', got {spec['model']!r}"
