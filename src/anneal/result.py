"""AnnealResult frozen dataclass — the final outcome of any anneal run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class AnnealResult:
    """The final outcome returned by anneal_classic and anneal_adversarial.

    Attributes:
        converged:       True when the loop terminated cleanly (N consecutive
                         clean rounds / Red empty for N rounds).
        rounds:          Number of rounds actually executed (1-based count of
                         the last round that ran).
        reason:          Why the loop terminated.  None means converged cleanly
                         (the loop's own "clean streak" exit path sets this to
                         "clean" as a convenience; None is also acceptable for
                         a converged result).
        final_diff:      The unified diff at the point of termination, if
                         available.
        log_dir:         Path to the transcript directory for this run.
        total_cost_usd:  Cumulative estimated USD cost from the CostTracker.
        mode:            "classic" or "adversarial".
    """

    converged: bool
    rounds: int
    reason: Literal[
        "clean",
        "oscillation",
        "patch_conflict",
        "max_rounds",
        "budget",
        "blue_cannot_defend",
    ] | None
    final_diff: str | None
    log_dir: Path | None
    total_cost_usd: float
    mode: Literal["classic", "adversarial"]
