"""Classic auditor+fixer loop: find, patch, re-audit until N consecutive clean rounds."""

from __future__ import annotations

from anneal.config import AnnealConfig


class AnnealResult:
    """Result returned by both anneal_classic and anneal_adversarial."""

    def __init__(
        self,
        converged: bool,
        rounds: int,
        reason: str | None = None,
        transcript_dir: str | None = None,
    ) -> None:
        raise NotImplementedError("anneal v0.0.1: not yet implemented")


def anneal_classic(cfg: AnnealConfig) -> AnnealResult:
    """Run the classic auditor+fixer loop on the diff described by cfg.

    Terminates on:
    - cfg.until_clean consecutive PASS rounds
    - oscillation (same finding fingerprint × 3)
    - patch_conflict
    - max_rounds reached
    - budget exceeded
    """
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
