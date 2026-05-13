"""Integration test: full canary suite runs end-to-end with real Claude.

Asserts pass rates: planted_bugs 100%, perturbations >=90%, clean_diffs 0% FP.
Requires ANTHROPIC_API_KEY. Skipped without it.
Phase 4 — canary suite end-to-end.
"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.live_api]

from anneal.canary.runner import run_canary


def test_placeholder():
    pytest.skip("Phase 4 — not yet implemented")
