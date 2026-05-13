"""AnnealConfig dataclass and environment loader with AM-key guard."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anneal.audit.base import Auditor
    from anneal.fix.base import Fixer
    from anneal.adversarial.red import RedAgent
    from anneal.adversarial.blue import BlueAgent
    from anneal.adversarial.judge import Judge


class MissingCredentials(Exception):
    """Raised when required API keys are absent from anneal's own .env."""


@dataclass
class AnnealConfig:
    """Full configuration for a single anneal run (classic or adversarial)."""

    # Required
    repo: Path
    base_ref: str

    # Loop control
    max_rounds: int = 10
    until_clean: int = 2
    max_cost_usd: float = 5.00
    dry_run: bool = False
    no_worktree: bool = False

    # Paths
    diff_path: Path | None = None
    log_dir: Path | None = None

    # Classic-mode components (set by CLI or caller)
    auditor: "Auditor | None" = None
    fixer: "Fixer | None" = None

    # Adversarial-mode components
    red: "RedAgent | None" = None
    blue: "BlueAgent | None" = None
    judge: "Judge | None" = None

    # Model overrides (None = use default)
    model: str = "claude-sonnet-4-6"
    auditor_model: str | None = None
    fixer_model: str | None = None
    red_model: str | None = None
    blue_model: str | None = None
    judge_model: str | None = None


def load_env(env_path: Path | None = None) -> dict[str, str]:
    """Load anneal's own .env and return a dict of required keys.

    Guards against loading credentials from the AntiGravity workspace.
    Raises MissingCredentials if ANTHROPIC_API_KEY is absent after loading.
    Does NOT walk parent directories.
    """
    raise NotImplementedError("anneal v0.0.1: not yet implemented")
