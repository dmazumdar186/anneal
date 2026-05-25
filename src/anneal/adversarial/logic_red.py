"""Logic-specialist Red agent: finds off-by-one, wrong comparisons, contract violations."""

from __future__ import annotations

from pathlib import Path

from anneal.adversarial.red import Red

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_LOGIC_PROMPT_PATH = _PROMPTS_DIR / "logic_red.md"


class LogicRed(Red):
    """Red attacker specializing in logic and correctness bugs.

    Targets off-by-one errors, wrong comparison operators, swapped
    arguments, integer overflow, timezone bugs, NaN/None propagation,
    race conditions in single-threaded code, and caller/callee contract
    violations.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Override the logic prompt path. Defaults to
            ``adversarial/prompts/logic_red.md``.
    """

    def __init__(self, llm, prompt_path: Path | None = None) -> None:  # type: ignore[override]
        super().__init__(llm, prompt_path=prompt_path or _LOGIC_PROMPT_PATH)
