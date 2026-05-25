"""Classic auditor+fixer loop: find, patch, re-audit until N consecutive clean rounds."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from anneal.audit.base import finding_fingerprint
from anneal.config import AnnealConfig, build_default_sast_runner
from anneal.cost import BudgetExceeded, CostTracker
from anneal.sast.base import format_findings_as_markdown
from anneal.diff.patch import ApplyResult, apply_patch
from anneal.diff.worktree import (
    GitOperationError,
    cleanup_worktree,
    git_commit_in_worktree,
    git_diff,
    make_worktree,
)
from anneal.fix.base import Patch
from anneal.result import AnnealResult
from anneal.transcript.writer import TranscriptWriter

logger = logging.getLogger(__name__)


# ── Private helpers ────────────────────────────────────────────────────────────


def _apply_initial_diff(worktree: Path, diff_path: Path | None) -> None:
    """Apply an initial diff file to the worktree before the loop starts.

    If diff_path is None, nothing is done — the worktree already represents
    the state to audit (checked out at the relevant commit).

    Args:
        worktree:  Absolute path to the worktree.
        diff_path: Optional path to a unified diff file on disk.

    Raises:
        FileNotFoundError: If diff_path is set but does not exist.
        GitOperationError: If the diff cannot be applied cleanly.
    """
    if diff_path is None:
        return

    # Import here to avoid a circular reference at module level
    from anneal.diff.patch import apply_initial_diff as _apply_file  # noqa: PLC0415

    result: ApplyResult = _apply_file(worktree, diff_path)
    if not result.ok:
        raise GitOperationError(
            f"Initial diff failed to apply cleanly: {result.stderr}",
            stderr=result.stderr,
        )


def _fingerprint_set(findings: list) -> frozenset[str]:
    """Return a frozenset of fingerprints for a list of Finding objects."""
    return frozenset(finding_fingerprint(f) for f in findings)


def oscillation_detected(current_findings: list, history: list[frozenset[str]]) -> bool:
    """Return True if the same set of finding fingerprints has appeared in the
    last 3 rounds (including the current one).

    The plan says "same fingerprint appears in 3 consecutive rounds" — we check
    whether any individual fingerprint from the current round appeared in each of
    the two most recent history entries AND in the current round.

    More precisely: if any fingerprint from current_findings also appears in
    both history[-1] and history[-2], that fingerprint has been seen for 3
    consecutive rounds → oscillation.

    Args:
        current_findings: Findings from the current round.
        history:          List of frozensets of fingerprints, one per prior
                          round that had findings (appended AFTER this check).

    Returns:
        True if oscillation is detected, False otherwise.
    """
    if len(history) < 2:
        return False

    current_fps = _fingerprint_set(current_findings)
    prev1 = history[-1]
    prev2 = history[-2]

    # Any fingerprint common to all three rounds → oscillation
    shared = current_fps & prev1 & prev2
    return len(shared) > 0


# ── Public loop ────────────────────────────────────────────────────────────────


def anneal_classic(cfg: AnnealConfig) -> AnnealResult:
    """Run the classic auditor+fixer loop on the diff described by cfg.

    Follows the pseudocode in the plan exactly:

        worktree = make_worktree(cfg.repo, cfg.base_ref)
        apply_initial_diff(worktree, cfg.diff_path)
        transcript = TranscriptWriter(cfg.log_dir, mode="classic")
        budget = CostTracker(cfg.max_cost_usd)
        clean_streak = 0
        finding_history = []

        for r in range(1, cfg.max_rounds + 1):
            budget.check()
            current_diff = git_diff(worktree, cfg.base_ref)
            report = cfg.auditor.audit(current_diff, worktree)
            transcript.write_audit(r, report)
            budget.add(report.tokens_used)

            if report.verdict == "PASS" and not report.findings:
                clean_streak += 1
                if clean_streak >= cfg.until_clean:
                    return AnnealResult(converged=True, ...)
                continue

            clean_streak = 0
            if oscillation_detected(report.findings, finding_history):
                return AnnealResult(converged=False, reason="oscillation", ...)
            finding_history.append(fingerprints)

            patch = cfg.fixer.fix(report, current_diff, worktree)
            budget.add(patch.tokens_used)
            ar = apply_patch(worktree, patch)
            transcript.write_fix(r, patch, ar)
            if not ar.ok:
                return AnnealResult(converged=False, reason="patch_conflict", ...)
            git_commit_in_worktree(worktree, f"fix: anneal-classic round {r}")

        return AnnealResult(converged=False, reason="max_rounds", ...)

    Termination:
        - cfg.until_clean consecutive PASS rounds → converged=True, reason="clean"
        - oscillation (same finding-fingerprint × 3) → reason="oscillation"
        - patch apply failure → reason="patch_conflict"
        - max_rounds reached → reason="max_rounds"
        - budget exceeded → reason="budget"
    """
    # ── Resolve log_dir ────────────────────────────────────────────────────────
    if cfg.log_dir is None:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        log_dir = Path.cwd() / ".anneal" / ts
    else:
        log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # ── Set up worktree ────────────────────────────────────────────────────────
    if cfg.no_worktree:
        logger.warning(
            "anneal_classic: --no-worktree is set. "
            "Operating directly on cfg.repo — changes will be made in place."
        )
        worktree = Path(cfg.repo)
        owned_worktree = False
    else:
        worktree_dest = log_dir / "worktree"
        worktree = make_worktree(cfg.repo, cfg.base_ref, dest=worktree_dest)
        owned_worktree = True

    # ── Apply initial diff (if any) ────────────────────────────────────────────
    try:
        _apply_initial_diff(worktree, cfg.diff_path)
    except (FileNotFoundError, GitOperationError) as exc:
        if owned_worktree:
            try:
                cleanup_worktree(cfg.repo, worktree, force=True)
            except GitOperationError:
                pass
        raise exc

    # ── Core loop ──────────────────────────────────────────────────────────────
    transcript = TranscriptWriter(log_dir, mode="classic")
    budget = CostTracker(cfg.max_cost_usd)
    clean_streak = 0
    finding_history: list[frozenset[str]] = []  # one entry per round with findings

    def _build_result(
        converged: bool,
        rounds: int,
        reason: str | None,
        final_diff: str | None = None,
    ) -> AnnealResult:
        return AnnealResult(
            converged=converged,
            rounds=rounds,
            reason=reason,  # type: ignore[arg-type]
            final_diff=final_diff,
            log_dir=log_dir,
            total_cost_usd=budget.total_usd,
            mode="classic",
        )

    result: AnnealResult | None = None

    # ── Resolve SAST runner (auto-detect once, before the loop) ───────────────
    if cfg.sast_runners is None:
        # Auto-detect: use ruff/semgrep if available, None if neither on PATH
        _sast_runner = build_default_sast_runner()
    elif len(cfg.sast_runners) == 0:
        # Explicitly disabled
        _sast_runner = None
    else:
        from anneal.sast.composite import CompositeSastRunner  # noqa: PLC0415
        _sast_runner = CompositeSastRunner(cfg.sast_runners)

    try:
        for r in range(1, cfg.max_rounds + 1):
            # Budget gate at the TOP of every round (plan says "wrap each LLM
            # call's tokens" and "check() at the top of every round")
            try:
                budget.check()
            except BudgetExceeded:
                result = _build_result(False, r - 1 if r > 1 else 1, "budget")
                break

            current_diff = git_diff(worktree, cfg.base_ref)

            # ── SAST pre-pass ──────────────────────────────────────────────────
            sast_md = ""
            if _sast_runner is not None:
                # Parse changed files from the diff ("+++ b/<path>" lines)
                changed_files = [
                    line[6:]  # strip "+++ b/"
                    for line in current_diff.splitlines()
                    if line.startswith("+++ b/")
                ]
                sast_findings_list = _sast_runner.run(worktree, changed_files)
                sast_md = format_findings_as_markdown(sast_findings_list)
            else:
                sast_findings_list = []

            logger.info("Round %d: sast: %d finding(s)", r, len(sast_findings_list))

            try:
                if sast_md:
                    report = cfg.auditor.audit(current_diff, worktree, sast_findings=sast_md)
                else:
                    report = cfg.auditor.audit(current_diff, worktree)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            transcript.write_audit(r, report)

            try:
                budget.add(report.tokens_used, cfg.auditor_model or cfg.model)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            # --- PASS path ---
            if report.verdict == "PASS" and not report.findings:
                clean_streak += 1
                logger.debug("Round %d: PASS (streak %d/%d)", r, clean_streak, cfg.until_clean)
                if clean_streak >= cfg.until_clean:
                    result = _build_result(True, r, "clean", final_diff=current_diff)
                    break
                continue

            # --- FAIL / WARNINGS path ---
            clean_streak = 0

            if oscillation_detected(report.findings, finding_history):
                logger.debug("Round %d: oscillation detected", r)
                result = _build_result(False, r, "oscillation")
                break

            finding_history.append(_fingerprint_set(report.findings))

            if cfg.dry_run:
                # dry-run: audit only, no patching
                logger.info("Round %d: --dry-run, skipping fix step", r)
                continue

            try:
                patch: Patch = cfg.fixer.fix(report, current_diff, worktree)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            try:
                budget.add(patch.tokens_used, cfg.fixer_model or cfg.model)
            except BudgetExceeded:
                ar = apply_patch(worktree, patch)
                transcript.write_fix(r, patch, ar)
                result = _build_result(False, r, "budget")
                break

            ar: ApplyResult = apply_patch(worktree, patch)
            transcript.write_fix(r, patch, ar)

            if not ar.ok:
                logger.debug("Round %d: patch conflict: %s", r, ar.stderr)
                result = _build_result(False, r, "patch_conflict")
                break

            try:
                git_commit_in_worktree(worktree, f"fix: anneal-classic round {r}")
            except GitOperationError:
                # Nothing to commit = patch was effectively a no-op; not a hard failure.
                # Log and continue — the next audit will catch it if there's still an issue.
                logger.debug("Round %d: git commit skipped (nothing to commit)", r)

        else:
            # Loop exhausted without break → max_rounds
            result = _build_result(False, cfg.max_rounds, "max_rounds")

    except GitOperationError as exc:
        logger.error("GitOperationError during loop: %s", exc)
        result = _build_result(
            False,
            cfg.max_rounds,  # rounds is ambiguous here; use max as a safe value
            "patch_conflict",
        )

    # ── Finalize ──────────────────────────────────────────────────────────────
    if result is None:
        # Should never happen, but be safe
        result = _build_result(False, cfg.max_rounds, "max_rounds")

    transcript.finalize(
        {
            "converged": result.converged,
            "rounds": result.rounds,
            "reason": result.reason,
            "total_cost_usd": result.total_cost_usd,
            "mode": result.mode,
        }
    )

    if owned_worktree:
        try:
            cleanup_worktree(cfg.repo, worktree, force=True)
        except GitOperationError as exc:
            logger.warning("Failed to clean up worktree '%s': %s", worktree, exc)

    return result
