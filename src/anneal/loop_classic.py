"""Classic auditor+fixer loop: find, patch, re-audit until N consecutive clean rounds."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from anneal.audit.base import AuditReport, PriorAttempt, finding_fingerprint, format_prior_attempts
from anneal.config import AnnealConfig, build_default_sast_runner, build_default_repo_graph
from anneal.diff.semantic import summarize_diff
from anneal.suppressions.store import SuppressionStore
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


# ── Determinism helper ────────────────────────────────────────────────────────


def _apply_determinism(cfg: AnnealConfig) -> None:
    """Monkey-patch auditor/fixer LLMs to bind temperature=0.0 and cfg.seed.

    Called at loop start when cfg.deterministic is True.  Sets ``_temperature``
    and ``_seed`` instance attributes on each adapter so every subsequent
    complete() call uses them as defaults (adapters read ``self._temperature``
    when the caller passes temperature=None).
    """
    for agent in (cfg.auditor, cfg.fixer):
        if agent is None:
            continue
        llm = getattr(agent, "llm", None) or getattr(agent, "_llm", None)
        if llm is None:
            continue
        llm._temperature = 0.0
        llm._seed = cfg.seed


# ── Private helpers ────────────────────────────────────────────────────────────


def _apply_suppressions(report: AuditReport, store: "SuppressionStore") -> AuditReport:
    """Filter suppressed findings from report; fix up verdict if needed.

    Args:
        report: The raw AuditReport from the auditor.
        store:  A loaded SuppressionStore.  is_suppressed() is called for each
                finding — this also refreshes last_seen_at in the store.

    Returns:
        A new AuditReport with suppressed findings removed.  If all findings
        are suppressed and the original verdict was FAIL or WARNINGS, the
        verdict is bumped down to PASS so the loop doesn't try to fix
        non-existent issues.
    """
    if not report.findings:
        return report

    kept = [f for f in report.findings if not store.is_suppressed(finding_fingerprint(f))]
    dropped = len(report.findings) - len(kept)
    if dropped:
        logger.info("suppressions: dropped %d finding(s)", dropped)

    if kept == report.findings:
        return report  # nothing changed — return as-is

    # Fix up verdict: if no findings remain, a FAIL/WARNINGS verdict is stale.
    verdict = report.verdict
    if not kept and verdict in ("FAIL", "WARNINGS"):
        verdict = "PASS"

    return AuditReport(
        verdict=verdict,
        findings=kept,
        silent_drops=report.silent_drops,
        logic_disagreements=report.logic_disagreements,
        summary=report.summary,
        raw_markdown=report.raw_markdown,
        tokens_used=report.tokens_used,
    )


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

    # ── Deterministic replay (T4.14) ───────────────────────────────────────────
    if cfg.deterministic:
        _apply_determinism(cfg)

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
    transcript = TranscriptWriter(
        log_dir,
        mode="classic",
        deterministic=cfg.deterministic,
        seed=cfg.seed,
        models={
            "auditor": cfg.auditor_model or cfg.model,
            "fixer": cfg.fixer_model or cfg.model,
        },
        max_rounds=cfg.max_rounds,
        until_clean=cfg.until_clean,
        max_cost_usd=cfg.max_cost_usd,
    )
    budget = CostTracker(cfg.max_cost_usd)
    clean_streak = 0
    finding_history: list[frozenset[str]] = []  # one entry per round with findings
    # Loop memory: one PriorAttempt per FAIL/WARNINGS round, fed forward to the
    # next round's auditor so it doesn't keep raising issues the fix resolved
    # nor keep proposing approaches the fixer already tried.
    prior_attempts_history: list[PriorAttempt] = []

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

    # ── Resolve repo-graph (auto-detect once, before the loop) ────────────────
    if cfg.repo_graph is None:
        _repo_graph = build_default_repo_graph(worktree)
    else:
        _repo_graph = cfg.repo_graph

    # ── Lazy-load SuppressionStore (once, before the loop) ────────────────────
    _store: SuppressionStore | None = None
    if cfg.suppressions_path is not None:
        _store = SuppressionStore(cfg.suppressions_path)
        logger.info("anneal_classic: suppressions loaded from %s", cfg.suppressions_path)

    # ── Wrap auditor with VotingAuditor if multi-sample requested (T2.7) ──
    # Composes cleanly with SAST: sast_findings are forwarded to each sample.
    _auditor = cfg.auditor
    if cfg.audit_samples > 1:
        from anneal.audit.voting import VotingAuditor  # noqa: PLC0415
        _auditor = VotingAuditor(
            cfg.auditor,
            samples=cfg.audit_samples,
            vote_threshold=cfg.audit_vote_threshold,
        )
        logger.info(
            "anneal_classic: multi-sample voting enabled — samples=%d threshold=%d",
            cfg.audit_samples,
            cfg.audit_vote_threshold,
        )

    # ── Resolve InterventionPrompter (lazy, once before the loop) ─────────────
    _prompter = None
    if cfg.interactive:
        if cfg.intervention_prompter is not None:
            _prompter = cfg.intervention_prompter
        else:
            from anneal.intervention.pause import InterventionPrompter  # noqa: PLC0415
            _prompter = InterventionPrompter()

    try:
        for r in range(1, cfg.max_rounds + 1):
            # Budget gate at the TOP of every round (plan says "wrap each LLM
            # call's tokens" and "check() at the top of every round")
            try:
                budget.check()
            except BudgetExceeded:
                if _prompter is not None:
                    from anneal.intervention.pause import Intervention  # noqa: PLC0415
                    choice, payload = _prompter.prompt_at_budget(budget.total_usd, cfg.max_cost_usd)
                    if choice == Intervention.RAISE_BUDGET:
                        new_max = payload.get("new_max_usd", cfg.max_cost_usd)
                        cfg.max_cost_usd = new_max
                        budget._max_usd = new_max
                        logger.info("Budget raised to $%.4f by user", new_max)
                        continue  # retry this round with raised budget
                    elif choice == Intervention.CONTINUE:
                        logger.info("User chose to continue past budget limit at risk")
                        # Disable the budget ceiling for the rest of the run
                        budget._max_usd = float("inf")
                        continue
                    # ABORT (or any other) → fall through to exit
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

            # ── Inject user hint from a prior oscillation pause (if any) ──────
            # Appended to sast_md so the auditor sees it as part of pre-pass context.
            _user_hint: str = cfg.__dict__.pop("_user_hint", "")
            if _user_hint:
                sast_md = (sast_md + "\n\n" if sast_md else "") + f"## User hint\n{_user_hint}"
                logger.info("Round %d: injecting user hint into audit context", r)

            # ── Repo-graph context ─────────────────────────────────────────────
            repograph_md = ""
            if _repo_graph is not None:
                from anneal.repograph.diff_extractor import build_context_for_diff  # noqa: PLC0415
                repograph_md = build_context_for_diff(current_diff, worktree, _repo_graph)
                # Count symbols and callers for the transcript log line
                _rg_symbols = [
                    line for line in repograph_md.splitlines()
                    if line.startswith("### `")
                ]
                _rg_callers = [
                    line for line in repograph_md.splitlines()
                    if line.startswith("- `") and "calls `" in line
                ]
                logger.info(
                    "Round %d: repograph: %d symbol(s), %d caller(s)",
                    r, len(_rg_symbols), len(_rg_callers),
                )

            # ── Semantic diff summary (pure Python, always-on) ─────────────────
            semantic_md = summarize_diff(current_diff, worktree)
            if semantic_md:
                logger.info("Round %d: semantic: %d line(s)", r, len(semantic_md.splitlines()))

            # ── Prior-round attempts (loop memory) ─────────────────────────────
            prior_md = format_prior_attempts(prior_attempts_history)
            if prior_md:
                logger.info(
                    "Round %d: prior_attempts: %d round(s) of memory injected",
                    r, len(prior_attempts_history),
                )

            try:
                if sast_md or repograph_md or semantic_md or prior_md:
                    report = _auditor.audit(
                        current_diff,
                        worktree,
                        sast_findings=sast_md,
                        repograph_context=repograph_md,
                        semantic_summary=semantic_md,
                        prior_attempts=prior_md,
                    )
                else:
                    report = _auditor.audit(current_diff, worktree)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            # ── Suppression filter (drop known-suppressed findings) ────────────
            if _store is not None:
                report = _apply_suppressions(report, _store)

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
                if _prompter is not None:
                    from anneal.intervention.pause import Intervention  # noqa: PLC0415
                    choice, payload = _prompter.prompt_at_oscillation(report, r)
                    if choice == Intervention.DISMISS_FINDING:
                        fp = payload.get("fingerprint", "")
                        if fp and _store is not None:
                            _store.add(fp, "dismissed via interactive oscillation pause")
                            logger.info("Oscillation: dismissed finding %s", fp)
                        # Re-apply suppressions and continue — don't break
                        if _store is not None:
                            report = _apply_suppressions(report, _store)
                        finding_history.append(_fingerprint_set(report.findings))
                        continue
                    elif choice == Intervention.ADD_HINT:
                        hint = payload.get("hint", "")
                        logger.info("Oscillation: user hint injected for next round: %r", hint)
                        # Inject hint into next round by tagging it on cfg for the auditor
                        # to pick up.  We prepend it to sast_md in the next iteration
                        # by storing on a mutable container attached to cfg.
                        if not hasattr(cfg, "_user_hint"):
                            object.__setattr__(cfg, "_user_hint", hint) if False else None
                        cfg.__dict__["_user_hint"] = hint
                        finding_history.append(_fingerprint_set(report.findings))
                        continue
                    elif choice == Intervention.CONTINUE:
                        logger.info("Oscillation: user chose to continue without changes")
                        finding_history.append(_fingerprint_set(report.findings))
                        continue
                    # ABORT → fall through to exit
                result = _build_result(False, r, "oscillation")
                break

            finding_history.append(_fingerprint_set(report.findings))

            # ── Loop memory: build per-round finding summaries ────────────────
            # Built once per FAIL/WARNINGS round; rationale is filled in below if
            # the fixer actually produced a patch. Captured even when the patch
            # fails to apply — the next round still benefits from knowing what
            # the fixer tried.
            _round_finding_summaries = [
                f"[{f.severity}] {f.summary}" for f in report.findings
            ]

            if cfg.dry_run:
                # dry-run: audit only, no patching — record findings without rationale
                # so the next dry-run round still gets memory of what was raised.
                prior_attempts_history.append(
                    PriorAttempt(
                        round_num=r,
                        verdict=report.verdict,
                        finding_summaries=_round_finding_summaries,
                        fixer_rationale="",
                    )
                )
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

            # Append this round's attempt to the loop-memory history regardless of
            # whether the patch applies cleanly. A failed patch is still signal
            # for round N+1 ("this approach didn't even apply — try a different one").
            prior_attempts_history.append(
                PriorAttempt(
                    round_num=r,
                    verdict=report.verdict,
                    finding_summaries=_round_finding_summaries,
                    fixer_rationale=patch.rationale,
                )
            )

            if not ar.ok:
                logger.debug("Round %d: patch conflict: %s", r, ar.stderr)
                if _prompter is not None:
                    from anneal.intervention.pause import Intervention  # noqa: PLC0415
                    conflict_files = [
                        line[6:]
                        for line in (patch.content if hasattr(patch, "content") else "").splitlines()
                        if line.startswith("+++ b/")
                    ]
                    excerpt = getattr(ar, "stderr", "") or ""
                    choice, _ = _prompter.prompt_at_patch_conflict(excerpt, conflict_files)
                    if choice == Intervention.CONTINUE:
                        logger.info("Patch conflict: user chose to skip this round and continue")
                        continue
                    # ABORT → fall through to exit
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
