"""AnnealConfig dataclass and environment loader with AM-key guard."""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from dotenv import dotenv_values

if TYPE_CHECKING:
    from anneal.audit.base import Auditor
    from anneal.fix.base import Fixer
    from anneal.adversarial.red import RedAgent
    from anneal.adversarial.blue import BlueAgent
    from anneal.adversarial.judge import Judge
    from anneal.sast.base import SastRunner
    from anneal.repograph.base import RepoGraph

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
    max_cost_usd: float = 1.00
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

    # SAST pre-pass (T2.6c)
    # None  = auto-detect (use ruff+semgrep if on PATH, skip silently if not)
    # []    = explicitly disabled (no SAST pre-pass)
    # [...]  = explicit list of runners to use
    sast_runners: "list[SastRunner] | None" = None

    # Repo-graph context injection (T2.8b)
    # None  = auto-detect (use PythonRepoGraph if any .py files exist in the worktree)
    # A RepoGraph instance = use it directly
    repo_graph: "RepoGraph | None" = None

    # Multi-sample voting (T2.7)
    # audit_samples=1 → single call, current behavior, zero overhead (default)
    # audit_samples=N, audit_vote_threshold=K → run N samples, keep findings in ≥K
    audit_samples: int = 1
    audit_vote_threshold: int = 1

    def __post_init__(self) -> None:
        if self.audit_samples < 1:
            raise ValueError(f"audit_samples must be >= 1, got {self.audit_samples}")
        if self.audit_vote_threshold < 1:
            raise ValueError(
                f"audit_vote_threshold must be >= 1, got {self.audit_vote_threshold}"
            )
        if self.audit_vote_threshold > self.audit_samples:
            raise ValueError(
                f"audit_vote_threshold ({self.audit_vote_threshold}) cannot exceed "
                f"audit_samples ({self.audit_samples})"
            )

    # Model overrides (None = use default)
    model: str = "claude-haiku-4-5-20251001"
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
        OPENROUTER_API_KEY if they appear. Empty dict if no .env exists.
    """
    env_file = repo_root / ".env"
    if not env_file.exists():
        return {}

    raw: dict[str, str | None] = dotenv_values(env_file)
    # Strip None values (unset vars in dotenv) and return only string values
    result: dict[str, str] = {k: v for k, v in raw.items() if v is not None}
    return result


def build_default_sast_runner():
    """Build a CompositeSastRunner from whichever tools are on PATH.

    Called automatically when ``AnnealConfig.sast_runners is None`` (auto-detect).
    Returns None if neither ruff nor semgrep is on PATH.

    Returns:
        A :class:`~anneal.sast.composite.CompositeSastRunner` containing all
        available runners, or ``None`` if no SAST tools are found.
    """
    import shutil

    from anneal.sast.composite import CompositeSastRunner
    from anneal.sast.ruff_runner import RuffRunner
    from anneal.sast.semgrep_runner import SemgrepRunner

    runners: list = []
    if shutil.which("ruff"):
        runners.append(RuffRunner())
        logger.debug("build_default_sast_runner: ruff found on PATH")
    else:
        logger.debug("build_default_sast_runner: ruff not on PATH, skipping")

    if shutil.which("semgrep"):
        runners.append(SemgrepRunner())
        logger.debug("build_default_sast_runner: semgrep found on PATH")
    else:
        logger.debug("build_default_sast_runner: semgrep not on PATH, skipping")

    if not runners:
        logger.debug("build_default_sast_runner: no SAST tools found, SAST pre-pass disabled")
        return None

    return CompositeSastRunner(runners)


def build_default_repo_graph(worktree: Path):
    """Return a PythonRepoGraph if the worktree contains any .py files, else None.

    Excludes ``.venv/`` and ``.git/`` directories from the search so the
    auto-detect does not trigger on vendored or VCS-internal Python files.

    Called automatically when ``AnnealConfig.repo_graph is None`` (auto-detect).

    Args:
        worktree: Absolute path to the worktree root.

    Returns:
        A :class:`~anneal.repograph.python_graph.PythonRepoGraph` instance, or
        ``None`` if no ``.py`` files are found outside excluded directories.
    """
    from anneal.repograph.python_graph import PythonRepoGraph  # noqa: PLC0415

    excluded = {".venv", ".git"}
    for py_file in worktree.rglob("*.py"):
        # Check that none of the path parts (relative to worktree) are excluded
        try:
            rel_parts = py_file.relative_to(worktree).parts
        except ValueError:
            continue
        if not any(part in excluded for part in rel_parts):
            logger.debug("build_default_repo_graph: .py files found, enabling PythonRepoGraph")
            return PythonRepoGraph()

    logger.debug("build_default_repo_graph: no .py files found outside excluded dirs, skipping")
    return None


def resolve_tier(
    tier: Literal["cheap", "balanced", "premium", "ultra"],
) -> dict[str, dict[str, str]]:
    """Resolve a tier preset to per-role (provider, model) tuples.

    Returns a dict keyed by role name. Each value is a dict with keys
    ``"provider"`` and ``"model"``.

    Tiers (per plan):
      cheap     -> gemini-2.5-flash for all roles, openrouter
      balanced  -> haiku 4.5 for audit/fix/red/blue (anthropic), gemini flash for judge (openrouter)
      premium   -> sonnet 4.6 for audit/fix/red/blue (anthropic), haiku 4.5 for judge (anthropic)
      ultra     -> opus 4.7 for audit/fix/red/blue (anthropic), sonnet 4.6 for judge (anthropic)

    Example::

        >>> resolve_tier("cheap")
        {
            "auditor": {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
            "fixer":   {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
            "red":     {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
            "blue":    {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
            "judge":   {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
        }

        >>> resolve_tier("balanced")
        {
            "auditor": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "fixer":   {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "red":     {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "blue":    {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "judge":   {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
        }

        >>> resolve_tier("premium")
        {
            "auditor": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "fixer":   {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "red":     {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "blue":    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "judge":   {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        }

        >>> resolve_tier("ultra")
        {
            "auditor": {"provider": "anthropic", "model": "claude-opus-4-7"},
            "fixer":   {"provider": "anthropic", "model": "claude-opus-4-7"},
            "red":     {"provider": "anthropic", "model": "claude-opus-4-7"},
            "blue":    {"provider": "anthropic", "model": "claude-opus-4-7"},
            "judge":   {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        }

    Args:
        tier: One of "cheap", "balanced", "premium", "ultra".

    Returns:
        Dict mapping role → {"provider": ..., "model": ...}.

    Raises:
        ValueError: If tier is not one of the three valid values.
    """
    _GEMINI_FLASH = {"provider": "openrouter", "model": "google/gemini-2.5-flash"}
    _HAIKU = {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}
    _SONNET = {"provider": "anthropic", "model": "claude-sonnet-4-6"}
    _OPUS_4_7 = {"provider": "anthropic", "model": "claude-opus-4-7"}

    if tier == "cheap":
        return {
            "auditor": _GEMINI_FLASH,
            "fixer":   _GEMINI_FLASH,
            "red":     _GEMINI_FLASH,
            "blue":    _GEMINI_FLASH,
            "judge":   _GEMINI_FLASH,
        }
    elif tier == "balanced":
        return {
            "auditor": _HAIKU,
            "fixer":   _HAIKU,
            "red":     _HAIKU,
            "blue":    _HAIKU,
            "judge":   _GEMINI_FLASH,
        }
    elif tier == "premium":
        return {
            "auditor": _SONNET,
            "fixer":   _SONNET,
            "red":     _SONNET,
            "blue":    _SONNET,
            "judge":   _HAIKU,
        }
    elif tier == "ultra":
        return {
            "auditor": _OPUS_4_7,
            "fixer":   _OPUS_4_7,
            "red":     _OPUS_4_7,
            "blue":    _OPUS_4_7,
            "judge":   _SONNET,
        }
    else:
        raise ValueError(
            f"Unknown tier {tier!r}. Valid values are: 'cheap', 'balanced', 'premium', 'ultra'."
        )
