"""CLI entry point: argparse skeleton with all subcommands registered."""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anneal",
        description="Harden code diffs via audit+fix or Red-vs-Blue adversarial loops.",
    )
    parser.add_argument("--version", action="version", version="anneal 0.0.1")

    subparsers = parser.add_subparsers(dest="command")

    # --- classic (default, also accessible as positional <ref>) ---
    classic = subparsers.add_parser("classic", help="Classic auditor+fixer loop.")
    _add_common_args(classic)
    classic.add_argument("ref", nargs="?", default="HEAD~1", help="Base git ref.")

    # --- adversarial ---
    adversarial = subparsers.add_parser("adversarial", help="Red-vs-Blue adversarial loop.")
    _add_common_args(adversarial)
    adversarial.add_argument("ref", nargs="?", default="HEAD~1")
    adversarial.add_argument("--red", default="default")
    adversarial.add_argument("--blue", default="default")
    adversarial.add_argument("--judge", default="default")
    adversarial.add_argument("--red-model")
    adversarial.add_argument("--blue-model")
    adversarial.add_argument("--judge-model")

    # --- canary ---
    canary = subparsers.add_parser("canary", help="Run the canary test suite.")
    canary.add_argument(
        "--subset",
        choices=["planted", "perturb", "clean", "all"],
        default="all",
    )
    canary.add_argument("--model", default="claude-sonnet-4-6")

    # --- replay-am ---
    replay = subparsers.add_parser("replay-am", help="AM-replay demo (classic mode).")
    _add_common_args(replay)
    replay.add_argument("--commit", required=True, help="AntiGravity commit SHA to replay.")
    replay.add_argument(
        "--repo",
        required=True,
        help="Path to the AntiGravity workspace (read-only).",
    )

    # --- show ---
    show = subparsers.add_parser("show", help="Display a transcript from a previous run.")
    show.add_argument("log_dir", help="Path to the .anneal/<timestamp>/ log directory.")

    return parser


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Add options shared across classic, adversarial, and replay-am subcommands."""
    p.add_argument("--auditor", default="pipeline-auditor")
    p.add_argument("--fixer", default="default")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--auditor-model")
    p.add_argument("--fixer-model")
    p.add_argument("--max-rounds", type=int, default=10)
    p.add_argument("--until-clean", type=int, default=2)
    p.add_argument("--max-cost-usd", type=float, default=5.00)
    p.add_argument("--base-ref", default="HEAD~1")
    p.add_argument("--repo", default=None)
    p.add_argument("--log-dir", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-worktree", action="store_true")


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    print(f"anneal v0.0.1: {args.command} not yet implemented")
    sys.exit(1)


if __name__ == "__main__":
    main()
