"""CLI entry point: argparse with classic mode wired end-to-end.

Subcommands adversarial, canary, replay-am, and show are stubbed for Phase 3+.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn


# ── Anneal-root discovery ──────────────────────────────────────────────────────


def _find_anneal_root(start: Path | None = None) -> Path | None:
    """Walk up from start until we find a directory containing pyproject.toml.

    Only used to locate the anneal package root so we can read its .env.
    We NEVER read .env files from arbitrary parent directories — we only
    read the .env that lives next to the pyproject.toml we find here.

    Args:
        start: Starting directory. Defaults to Path.cwd().

    Returns:
        The directory containing pyproject.toml, or None if not found.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / "pyproject.toml").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


# ── Argument parser ────────────────────────────────────────────────────────────


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Add options shared across classic, adversarial, and replay-am subcommands."""
    p.add_argument("--auditor", default="pipeline-auditor", help="Auditor name or path.")
    p.add_argument("--fixer", default="default", help="Fixer name or path.")
    p.add_argument("--model", default="claude-sonnet-4-6", help="Default LLM model.")
    p.add_argument("--auditor-model", default=None, help="Override model for auditor.")
    p.add_argument("--fixer-model", default=None, help="Override model for fixer.")
    p.add_argument("--max-rounds", type=int, default=10, metavar="N")
    p.add_argument("--until-clean", type=int, default=2, metavar="N")
    p.add_argument("--max-cost-usd", type=float, default=5.00, metavar="FLOAT")
    p.add_argument(
        "--base-ref",
        default="HEAD~1",
        help="Base git ref to diff against (default: HEAD~1).",
    )
    p.add_argument("--repo", default=None, help="Path to git repo (default: cwd).")
    p.add_argument(
        "--log-dir",
        default=None,
        help="Directory for transcript output (default: .anneal/<timestamp>/).",
    )
    p.add_argument("--dry-run", action="store_true", help="Audit only; skip patching.")
    p.add_argument(
        "--no-worktree",
        action="store_true",
        help="Operate on repo in-place rather than in a git worktree (use with caution).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anneal",
        description="Harden code diffs via audit+fix or Red-vs-Blue adversarial loops.",
    )
    parser.add_argument("--version", action="version", version="anneal 0.0.1")

    subparsers = parser.add_subparsers(dest="command")

    # --- classic (default subcommand) ---
    classic = subparsers.add_parser("classic", help="Classic auditor+fixer loop (default).")
    classic.add_argument(
        "ref",
        nargs="?",
        default=None,
        help="Base git ref (e.g. HEAD~1, a SHA). Overrides --base-ref.",
    )
    classic.add_argument(
        "--diff-file",
        default=None,
        metavar="PATH",
        help="Apply a diff file on top of base-ref before the audit loop starts.",
    )
    _add_common_args(classic)

    # --- adversarial (stub) ---
    adversarial = subparsers.add_parser(
        "adversarial", help="Red-vs-Blue adversarial loop (Phase 3)."
    )
    adversarial.add_argument("ref", nargs="?", default="HEAD~1")
    adversarial.add_argument("--red", default="default")
    adversarial.add_argument("--blue", default="default")
    adversarial.add_argument("--judge", default="default")
    adversarial.add_argument("--red-model")
    adversarial.add_argument("--blue-model")
    adversarial.add_argument("--judge-model")
    _add_common_args(adversarial)

    # --- canary (stub) ---
    canary = subparsers.add_parser("canary", help="Run the canary test suite (Phase 4).")
    canary.add_argument(
        "--subset",
        choices=["planted", "perturb", "clean", "all"],
        default="all",
    )
    canary.add_argument("--model", default="claude-sonnet-4-6")

    # --- replay-am (stub) ---
    replay = subparsers.add_parser(
        "replay-am", help="AM-replay demo — classic mode on AM history (Phase 5)."
    )
    replay.add_argument("--commit", required=True, help="AntiGravity commit SHA to replay.")
    replay.add_argument(
        "--repo",
        required=True,
        help="Path to the AntiGravity workspace (read-only).",
    )
    _add_common_args(replay)

    # --- show (stub) ---
    show = subparsers.add_parser(
        "show", help="Display a transcript from a previous run (Phase 5)."
    )
    show.add_argument("log_dir", help="Path to the .anneal/<timestamp>/ log directory.")

    return parser


# ── Classic-mode flow ──────────────────────────────────────────────────────────


def _run_classic(args: argparse.Namespace) -> NoReturn:
    """Execute the classic audit+fix loop and exit with appropriate code."""
    from anneal.config import AnnealConfig, MissingCredentials, load_env
    from anneal.cost import CostTracker
    from anneal.audit.pipeline_auditor import PipelineAuditor
    from anneal.fix.default_fixer import DefaultFixer
    from anneal.llm.claude import ClaudeLLM
    from anneal.loop_classic import anneal_classic

    # --- Load .env from anneal root ---
    anneal_root = _find_anneal_root()
    env: dict[str, str] = {}
    if anneal_root:
        env = load_env(anneal_root)

    # --- Resolve ANTHROPIC_API_KEY ---
    api_key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "anneal: ANTHROPIC_API_KEY not set. "
            "Add it to the anneal .env or export it in your shell.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # --- Build components ---
    os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
    model = getattr(args, "model", "claude-sonnet-4-6") or "claude-sonnet-4-6"
    llm = ClaudeLLM(model=model, api_key=api_key)
    auditor = PipelineAuditor(llm)
    fixer = DefaultFixer(llm)

    # --- Resolve repo and base_ref ---
    repo = Path(args.repo) if args.repo else Path.cwd()
    # Positional `ref` overrides --base-ref if provided
    ref = args.ref if args.ref else getattr(args, "base_ref", "HEAD~1")

    # --- Resolve log_dir ---
    if args.log_dir:
        log_dir = Path(args.log_dir)
    else:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        log_dir = repo / ".anneal" / ts

    # --- Resolve diff_path ---
    diff_path: Path | None = None
    if getattr(args, "diff_file", None):
        diff_path = Path(args.diff_file)

    cfg = AnnealConfig(
        repo=repo,
        base_ref=ref,
        max_rounds=args.max_rounds,
        until_clean=args.until_clean,
        max_cost_usd=args.max_cost_usd,
        dry_run=args.dry_run,
        no_worktree=args.no_worktree,
        diff_path=diff_path,
        log_dir=log_dir,
        auditor=auditor,
        fixer=fixer,
        model=model,
        auditor_model=getattr(args, "auditor_model", None),
        fixer_model=getattr(args, "fixer_model", None),
    )

    result = anneal_classic(cfg)

    # --- Pretty-print summary ---
    status = "CONVERGED" if result.converged else "DID NOT CONVERGE"
    print(f"\nanneal classic — {status}")
    print(f"  rounds:    {result.rounds}")
    print(f"  reason:    {result.reason}")
    print(f"  cost:      ${result.total_cost_usd:.4f}")
    if result.log_dir:
        print(f"  transcript: {result.log_dir}")

    raise SystemExit(0 if result.converged else 1)


# ── Main entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point (installed as `anneal` by pyproject.toml)."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        # No subcommand — behave as `anneal classic` with positional ref if given.
        # Re-parse using the classic subparser defaults.
        parser.print_help()
        sys.exit(1)

    if args.command == "classic":
        _run_classic(args)

    elif args.command in ("adversarial", "canary", "replay-am", "show"):
        print(f"{args.command}: not yet implemented in Phase 2b", file=sys.stderr)
        sys.exit(2)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
