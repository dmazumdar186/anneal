"""Red-vs-Blue adversarial loop: Red attacks, Blue hardens, loop until Red comes up empty."""

from __future__ import annotations

from anneal.config import AnnealConfig
from anneal.loop_classic import AnnealResult


def anneal_adversarial(cfg: AnnealConfig) -> AnnealResult:
    """Run the Red-vs-Blue adversarial loop on the diff described by cfg.

    Terminates on:
    - Red empty for cfg.until_clean consecutive rounds (Blue wins, converged=True)
    - Same attack fingerprint landed in 3 consecutive rounds (blue_cannot_defend)
    - patch_conflict
    - max_rounds reached
    - budget exceeded
    """
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
