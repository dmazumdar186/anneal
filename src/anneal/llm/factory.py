"""LLM factory: construct the right adapter from (provider, model, api_keys).

Usage::

    from anneal.llm.factory import build_llm

    api_keys = {**load_env(anneal_root), **os.environ}
    llm = build_llm("anthropic", "claude-haiku-4-5-20251001", api_keys)
    llm = build_llm("openrouter", "google/gemini-2.5-flash", api_keys)
"""

from __future__ import annotations

from typing import Literal

from anneal.config import MissingCredentials
from anneal.llm.base import LLM
from anneal.llm.claude import ClaudeLLM
from anneal.llm.openrouter import OpenRouterLLM


def build_llm(
    provider: Literal["anthropic", "openrouter"],
    model: str,
    api_keys: dict[str, str],
) -> LLM:
    """Construct an LLM adapter from (provider, model, api_keys).

    ``api_keys`` should be the merged dict of load_env() + os.environ
    (the caller — cli.py — performs that merge). This function only reads from it.

    Args:
        provider: "anthropic" (uses ClaudeLLM + ANTHROPIC_API_KEY) or
                  "openrouter" (uses OpenRouterLLM + OPENROUTER_API_KEY).
        model: Model identifier appropriate for the chosen provider.
        api_keys: Dict containing the required API key(s).

    Returns:
        A concrete LLM adapter that satisfies the LLM protocol.

    Raises:
        MissingCredentials: If the required API key for the provider is absent.
        ValueError: If provider is not one of the two valid values.

    Example::

        >>> llm = build_llm("anthropic", "claude-haiku-4-5-20251001",
        ...                  {"ANTHROPIC_API_KEY": "sk-ant-..."})
        >>> isinstance(llm, ClaudeLLM)
        True

        >>> llm = build_llm("openrouter", "google/gemini-2.5-flash",
        ...                  {"OPENROUTER_API_KEY": "sk-or-..."})
        >>> isinstance(llm, OpenRouterLLM)
        True
    """
    if provider == "anthropic":
        key = api_keys.get("ANTHROPIC_API_KEY")
        if not key:
            raise MissingCredentials(
                "ANTHROPIC_API_KEY is required for provider='anthropic' but was not found "
                "in the supplied api_keys dict. Add it to your anneal .env or shell env."
            )
        return ClaudeLLM(model=model, api_key=key)

    elif provider == "openrouter":
        key = api_keys.get("OPENROUTER_API_KEY")
        if not key:
            raise MissingCredentials(
                "OPENROUTER_API_KEY is required for provider='openrouter' but was not found "
                "in the supplied api_keys dict. Add it to your anneal .env or shell env."
            )
        return OpenRouterLLM(model=model, api_key=key)

    else:
        raise ValueError(
            f"Unknown provider {provider!r}. Valid values are: 'anthropic', 'openrouter'."
        )
