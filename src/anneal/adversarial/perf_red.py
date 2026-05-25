"""Performance-specialist Red agent: finds N+1s, hot-path allocations, O(n²) patterns."""

from __future__ import annotations

from pathlib import Path

from anneal.adversarial.red import Red

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_PERF_PROMPT_PATH = _PROMPTS_DIR / "perf_red.md"


class PerfRed(Red):
    """Red attacker specializing in performance regressions.

    Targets N+1 query patterns, hot-path allocations in loops, missing
    memoization, O(n²) complexity, unbounded recursion, sync I/O in
    async paths, and missing pagination on user-controlled queries.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Override the perf prompt path. Defaults to
            ``adversarial/prompts/perf_red.md``.
    """

    def __init__(self, llm, prompt_path: Path | None = None) -> None:  # type: ignore[override]
        super().__init__(llm, prompt_path=prompt_path or _PERF_PROMPT_PATH)
