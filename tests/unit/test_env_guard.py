"""Unit tests for the AM-key guard in config.load_env.

Verifies that anneal fails with MissingCredentials — not with a client key —
when ANTHROPIC_API_KEY is present only in a parent-directory .env.
Phase 1 — strict-isolation guardrails.
"""

import pytest

from anneal.config import load_env, MissingCredentials


def test_placeholder():
    pytest.skip("Phase 1 — not yet implemented")
