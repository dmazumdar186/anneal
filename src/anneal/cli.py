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
    p.add_argument(
        "--tier",
        choices=["cheap", "balanced", "premium"],
        default="balanced",
        help="Model preset bundle: cheap (Gemini Flash/all), balanced (Haiku/substantive + Gemini/judge), premium (Sonnet/substantive + Haiku/judge). Default: balanced.",
    )
    p.add_argument(
        "--provider",
        choices=["anthropic", "openrouter"],
        default=None,
        help="Force a specific provider for all roles. Default: use tier's per-role provider.",
    )
    p.add_argument("--model", default=None, help="Override the tier's default model for ALL roles.")
    p.add_argument("--auditor-model", default=None, help="Override model for auditor.")
    p.add_argument("--fixer-model", default=None, help="Override model for fixer.")
    p.add_argument("--max-rounds", type=int, default=10, metavar="N")
    p.add_argument("--until-clean", type=int, default=2, metavar="N")
    p.add_argument("--max-cost-usd", type=float, default=1.00, metavar="FLOAT")
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
    canary.add_argument("--model", default="claude-haiku-4-5-20251001")

    # --- replay-am (stub) ---
    replay = subparsers.add_parser(
        "replay-am", help="AM-replay demo — classic mode on AM history (Phase 5)."
    )
    replay.add_argument("--commit", required=True, help="AntiGravity commit SHA to replay.")
    # --repo comes from _add_common_args below (required is enforced at runtime)
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
    from anneal.config import AnnealConfig, MissingCredentials, load_env, resolve_tier
    from anneal.audit.pipeline_auditor import PipelineAuditor
    from anneal.fix.default_fixer import DefaultFixer
    from anneal.llm.factory import build_llm
    from anneal.loop_classic import anneal_classic

    # --- Load .env from anneal root and merge with shell env ---
    anneal_root = _find_anneal_root()
    file_env: dict[str, str] = {}
    if anneal_root:
        file_env = load_env(anneal_root)
    # Shell env takes precedence over .env file
    api_keys: dict[str, str] = {**file_env, **{k: v for k, v in os.environ.items() if v}}

    # --- Resolve tier → per-role (provider, model) defaults ---
    tier = getattr(args, "tier", "balanced") or "balanced"
    tier_map = resolve_tier(tier)

    # --- Apply override priority for auditor role ---
    # --{role}-model > --model > tier default model
    # --provider > tier default provider for this role
    global_model_override = getattr(args, "model", None)
    global_provider_override = getattr(args, "provider", None)

    def _resolve_role(role: str, role_model_attr: str) -> tuple[str, str]:
        """Return (provider, model) for a role, applying CLI overrides."""
        role_defaults = tier_map[role]
        provider = global_provider_override or role_defaults["provider"]
        model = (
            getattr(args, role_model_attr, None)
            or global_model_override
            or role_defaults["model"]
        )
        return provider, model

    auditor_provider, auditor_model = _resolve_role("auditor", "auditor_model")
    fixer_provider, fixer_model = _resolve_role("fixer", "fixer_model")

    # --- Print resolved per-role config ---
    print(f"anneal classic  tier={tier}")
    print(f"  auditor  provider={auditor_provider}  model={auditor_model}")
    print(f"  fixer    provider={fixer_provider}  model={fixer_model}")

    # --- Build LLM adapters ---
    try:
        auditor_llm = build_llm(auditor_provider, auditor_model, api_keys)
        fixer_llm = build_llm(fixer_provider, fixer_model, api_keys)
    except MissingCredentials as exc:
        print(f"anneal: {exc}", file=sys.stderr)
        raise SystemExit(1)

    auditor = PipelineAuditor(auditor_llm)
    fixer = DefaultFixer(fixer_llm)

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
        model=auditor_model,
        auditor_model=auditor_model,
        fixer_model=fixer_model,
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


# ── Adversarial-mode flow ──────────────────────────────────────────────────────


def _run_adversarial(args: argparse.Namespace) -> NoReturn:
    """Execute the Red-vs-Blue adversarial loop and exit with appropriate code."""
    from anneal.config import AnnealConfig, MissingCredentials, load_env, resolve_tier
    from anneal.adversarial.red import Red
    from anneal.adversarial.blue import Blue
    from anneal.adversarial.judge import Judge
    from anneal.llm.factory import build_llm
    from anneal.loop_adversarial import anneal_adversarial

    # --- Load .env from anneal root and merge with shell env ---
    anneal_root = _find_anneal_root()
    file_env: dict[str, str] = {}
    if anneal_root:
        file_env = load_env(anneal_root)
    api_keys: dict[str, str] = {**file_env, **{k: v for k, v in os.environ.items() if v}}

    # --- Resolve tier → per-role (provider, model) defaults ---
    tier = getattr(args, "tier", "balanced") or "balanced"
    tier_map = resolve_tier(tier)

    global_model_override = getattr(args, "model", None)
    global_provider_override = getattr(args, "provider", None)

    def _resolve_role(role: str, role_model_attr: str) -> tuple[str, str]:
        role_defaults = tier_map[role]
        provider = global_provider_override or role_defaults["provider"]
        model = (
            getattr(args, role_model_attr, None)
            or global_model_override
            or role_defaults["model"]
        )
        return provider, model

    red_provider, red_model = _resolve_role("red", "red_model")
    blue_provider, blue_model = _resolve_role("blue", "blue_model")
    judge_provider, judge_model = _resolve_role("judge", "judge_model")

    # --- Print resolved per-role config ---
    print(f"anneal adversarial  tier={tier}")
    print(f"  red    provider={red_provider}  model={red_model}")
    print(f"  blue   provider={blue_provider}  model={blue_model}")
    print(f"  judge  provider={judge_provider}  model={judge_model}")

    # --- Build LLM adapters ---
    try:
        red_llm = build_llm(red_provider, red_model, api_keys)
        blue_llm = build_llm(blue_provider, blue_model, api_keys)
        judge_llm = build_llm(judge_provider, judge_model, api_keys)
    except MissingCredentials as exc:
        print(f"anneal: {exc}", file=sys.stderr)
        raise SystemExit(1)

    red = Red(red_llm)
    blue = Blue(blue_llm)
    judge = Judge(judge_llm)

    # --- Resolve repo and base_ref ---
    repo = Path(args.repo) if args.repo else Path.cwd()
    ref = args.ref if args.ref else getattr(args, "base_ref", "HEAD~1")

    # --- Resolve log_dir ---
    if args.log_dir:
        log_dir = Path(args.log_dir)
    else:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        log_dir = repo / ".anneal" / ts

    cfg = AnnealConfig(
        repo=repo,
        base_ref=ref,
        max_rounds=args.max_rounds,
        until_clean=args.until_clean,
        max_cost_usd=args.max_cost_usd,
        dry_run=args.dry_run,
        no_worktree=args.no_worktree,
        diff_path=None,
        log_dir=log_dir,
        red=red,
        blue=blue,
        judge=judge,
        model=red_model,
        red_model=red_model,
        blue_model=blue_model,
        judge_model=judge_model,
    )

    result = anneal_adversarial(cfg)

    # --- Pretty-print summary ---
    status = "CONVERGED" if result.converged else "DID NOT CONVERGE"
    print(f"\nanneal adversarial — {status}")
    print(f"  rounds:    {result.rounds}")
    print(f"  reason:    {result.reason}")
    print(f"  cost:      ${result.total_cost_usd:.4f}")
    if result.log_dir:
        print(f"  transcript: {result.log_dir}")

    raise SystemExit(0 if result.converged else 1)


# ── show subcommand ────────────────────────────────────────────────────────────


def _run_show(args: argparse.Namespace) -> NoReturn:
    """Pretty-print the manifest.json from a past run."""
    import json

    log_dir = Path(args.log_dir)
    manifest_path = log_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"anneal show: manifest.json not found in '{log_dir}'", file=sys.stderr)
        raise SystemExit(1)

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"anneal show: failed to read manifest.json: {exc}", file=sys.stderr)
        raise SystemExit(1)

    mode = data.get("mode", "unknown")
    started = data.get("started_at", "unknown")
    finalized = data.get("finalized_at", "unknown")
    result = data.get("result") or {}

    print(f"anneal run — mode={mode}")
    print(f"  started:   {started}")
    print(f"  finalized: {finalized}")
    if result:
        converged = result.get("converged")
        rounds = result.get("rounds")
        reason = result.get("reason")
        cost = result.get("total_cost_usd")
        print(f"  converged: {converged}")
        print(f"  rounds:    {rounds}")
        print(f"  reason:    {reason}")
        if cost is not None:
            print(f"  cost:      ${float(cost):.4f}")
    print(f"  log_dir:   {log_dir}")

    raise SystemExit(0)


# ── Main entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point (installed as `anneal` by pyproject.toml)."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "classic":
        _run_classic(args)

    elif args.command == "adversarial":
        _run_adversarial(args)

    elif args.command == "show":
        _run_show(args)

    elif args.command in ("canary", "replay-am"):
        print(f"{args.command}: not yet implemented (Phase 4/5)", file=sys.stderr)
        sys.exit(2)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
