"""AnnealConfig dataclass and environment loader with AM-key guard."""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import dotenv_values

if TYPE_CHECKING:
    from anneal.audit.base import Auditor
    from anneal.fix.base import Fixer
    from anneal.adversarial.red import RedAgent
    from anneal.adversarial.blue import BlueAgent
    from anneal.adversarial.judge import Judge

logger = logging.getLogger(__name__)

# Glob pattern that identifies the AntiGravity / Accessory Masters workspace
_AM_GLOB = "directives/gtm_client_workflows/accessory_masters_*"


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


def assert_not_am_workspace(repo_path: Path) -> None:
    """Defense-in-depth guard: warn if repo_path looks like the AM/AntiGravity workspace.

    Checks for the co-presence of:
      1. A file matching directives/gtm_client_workflows/accessory_masters_*
      2. A .env file at repo_path root

    If both are found, emits a warning so the user can see the protection trigger.
    This is a logging guard only — load_env's explicit repo_root parameter is the
    primary enforcement mechanism.
    """
    env_file = repo_path / ".env"
    if not env_file.exists():
        return

    # Check for AM-identifying files
    am_files = list(repo_path.glob(_AM_GLOB))
    if am_files:
        msg = (
            f"anneal AM-key guard triggered: repo_path '{repo_path}' looks like the "
            f"AntiGravity / Accessory Masters workspace "
            f"(found {len(am_files)} matching directives/gtm_client_workflows/accessory_masters_*). "
            "anneal will NOT read .env from this path. "
            "Provide your own anneal .env with user-owned API keys."
        )
        warnings.warn(msg, stacklevel=2)
        logger.warning(msg)


def load_env(repo_root: Path) -> dict[str, str]:
    """Load anneal's own .env from repo_root ONLY — never walks parent directories.

    Uses python-dotenv's dotenv_values() which reads the file directly without
    modifying os.environ. Returns a dict with whatever keys are present.

    The caller decides which keys are required. To check for ANTHROPIC_API_KEY:
        env = load_env(repo_root)
        key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise MissingCredentials("ANTHROPIC_API_KEY not set in anneal .env or shell")

    AM-key guard: we explicitly pass repo_root so no parent-dir walk can happen.
    The .env at repo_root/.env is the only file read.

    Args:
        repo_root: The anneal project root. Only repo_root/.env is read.

    Returns:
        Dict of key → value from the .env file, plus ANTHROPIC_API_KEY and
        OPENAI_API_KEY if they appear. Empty dict if no .env exists.
    """
    env_file = repo_root / ".env"
    if not env_file.exists():
        return {}

    raw: dict[str, str | None] = dotenv_values(env_file)
    # Strip None values (unset vars in dotenv) and return only string values
    result: dict[str, str] = {k: v for k, v in raw.items() if v is not None}
    return result
