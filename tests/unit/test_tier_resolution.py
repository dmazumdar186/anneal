"""Unit tests for resolve_tier() in anneal.config."""

from __future__ import annotations

import pytest

from anneal.config import resolve_tier


def test_resolve_tier_cheap() -> None:
    """cheap tier: all roles map to google/gemini-2.5-flash via openrouter."""
    result = resolve_tier("cheap")
    assert set(result.keys()) == {"auditor", "fixer", "red", "blue", "judge"}
    for role, spec in result.items():
        assert spec["provider"] == "openrouter", f"{role} provider mismatch"
        assert spec["model"] == "google/gemini-2.5-flash", f"{role} model mismatch"


def test_resolve_tier_balanced() -> None:
    """balanced tier: audit/fix/red/blue → haiku 4.5 anthropic; judge → gemini flash openrouter."""
    result = resolve_tier("balanced")
    assert set(result.keys()) == {"auditor", "fixer", "red", "blue", "judge"}

    for role in ("auditor", "fixer", "red", "blue"):
        assert result[role]["provider"] == "anthropic", f"{role} provider should be anthropic"
        assert result[role]["model"] == "claude-haiku-4-5-20251001", f"{role} model mismatch"

    assert result["judge"]["provider"] == "openrouter"
    assert result["judge"]["model"] == "google/gemini-2.5-flash"


def test_resolve_tier_premium() -> None:
    """premium tier: audit/fix/red/blue → sonnet 4.6 anthropic; judge → haiku 4.5 anthropic."""
    result = resolve_tier("premium")
    assert set(result.keys()) == {"auditor", "fixer", "red", "blue", "judge"}

    for role in ("auditor", "fixer", "red", "blue"):
        assert result[role]["provider"] == "anthropic", f"{role} provider should be anthropic"
        assert result[role]["model"] == "claude-sonnet-4-6", f"{role} model mismatch"

    assert result["judge"]["provider"] == "anthropic"
    assert result["judge"]["model"] == "claude-haiku-4-5-20251001"


def test_resolve_tier_invalid_raises() -> None:
    """Passing an unknown tier string raises ValueError."""
    with pytest.raises(ValueError, match="Unknown tier"):
        resolve_tier("garbage")  # type: ignore[arg-type]
