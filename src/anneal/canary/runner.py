"""Canary suite runner: executes all fixture subsets and produces canary_report.json."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

CanarySubset = Literal["planted", "perturb", "clean", "all"]


def run_canary(
    subset: CanarySubset = "all",
    model: str = "claude-sonnet-4-6",
    report_path: Path | None = None,
) -> dict[str, object]:
    """Run the specified canary subset and write canary_report.json.

    Pass rates:
    - planted_bugs: 100% caught on round 1
    - perturbations: >=90% across all variants
    - clean_diffs: 0% false positives
    """
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
