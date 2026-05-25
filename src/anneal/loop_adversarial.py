"""Red-vs-Blue adversarial loop: Red attacks, Blue hardens, loop until Red comes up empty."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone
from pathlib import Path

from anneal.adversarial.base import Attack, AttackResult
from anneal.config import AnnealConfig
from anneal.cost import BudgetExceeded, CostTracker
from anneal.diff.patch import apply_patch
from anneal.diff.worktree import (
    GitOperationError,
    cleanup_worktree,
    git_commit_in_worktree,
    git_diff,
    make_worktree,
)
from anneal.result import AnnealResult
from anneal.runner.python_test_runner import run_python_test, write_test_file
from anneal.transcript.writer import TranscriptWriter

logger = logging.getLogger(__name__)


# ── blue_stuck helper ──────────────────────────────────────────────────────────


def blue_stuck(landed_history: list[list[str]]) -> bool:
    """Return True if any fingerprint appears in each of the last 3 entries.

    Args:
        landed_history: List of lists of fingerprints, one list per round
            (newest last). Each entry is the fingerprints that landed that round.

    Returns:
        True if any single fingerprint appears in every one of the last 3 entries,
        indicating Blue is stuck and cannot defend against the attack.
    """
    if len(landed_history) < 3:
        return False

    last3 = landed_history[-3:]
    # Intersect all three sets — any fingerprint in all three means Blue is stuck
    shared = set(last3[0]) & set(last3[1]) & set(last3[2])
    return len(shared) > 0


# ── Public loop ────────────────────────────────────────────────────────────────


def anneal_adversarial(cfg: AnnealConfig) -> AnnealResult:
    """Run the Red-vs-Blue adversarial loop on the diff described by cfg.

    Follows the pseudocode in the plan exactly.

    Termination conditions:
    - Red empty for cfg.until_clean consecutive rounds → Blue wins (converged=True, reason="clean")
    - Same attack fingerprint landed in 3 consecutive rounds → reason="blue_cannot_defend"
    - patch_conflict → reason="patch_conflict"
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
            "anneal_adversarial: --no-worktree is set. "
            "Operating directly on cfg.repo — changes will be made in place."
        )
        worktree = Path(cfg.repo)
        owned_worktree = False
    else:
        worktree_dest = log_dir / "worktree"
        worktree = make_worktree(cfg.repo, cfg.base_ref, dest=worktree_dest)
        owned_worktree = True

    # ── Apply initial diff (if any) ────────────────────────────────────────────
    if cfg.diff_path is not None:
        from anneal.diff.patch import apply_initial_diff as _apply_file  # noqa: PLC0415
        ar0 = _apply_file(worktree, cfg.diff_path)
        if not ar0.ok:
            if owned_worktree:
                try:
                    cleanup_worktree(cfg.repo, worktree, force=True)
                except GitOperationError:
                    pass
            raise GitOperationError(
                f"Initial diff failed to apply cleanly: {ar0.stderr}",
                stderr=ar0.stderr,
            )

    # ── Core loop state ────────────────────────────────────────────────────────
    transcript = TranscriptWriter(log_dir, mode="adversarial")
    budget = CostTracker(cfg.max_cost_usd)
    red_empty_streak = 0
    open_attacks: list[Attack] = []          # landed attacks Blue must address next round
    landed_history: list[list[str]] = []     # per-round lists of fingerprints that landed

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
            mode="adversarial",
        )

    result: AnnealResult | None = None

    try:
        for r in range(1, cfg.max_rounds + 1):
            # Budget gate at the TOP of every round
            try:
                budget.check()
            except BudgetExceeded:
                result = _build_result(False, r - 1 if r > 1 else 1, "budget")
                break

            current_diff = git_diff(worktree, cfg.base_ref)

            # ── Blue's turn: audit + fix, ALSO address any open attacks ────────
            try:
                blue_report = cfg.blue.harden(current_diff, worktree, open_attacks)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            transcript.write_blue(r, blue_report)

            try:
                budget.add(blue_report.tokens_used, cfg.blue_model or cfg.model)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            if blue_report.patch:
                ar = apply_patch(worktree, blue_report.patch)
                if not ar.ok:
                    logger.debug("Round %d: Blue patch conflict: %s", r, ar.stderr)
                    result = _build_result(False, r, "patch_conflict")
                    break
                try:
                    git_commit_in_worktree(worktree, f"fix: anneal-blue round {r}")
                except GitOperationError:
                    # Nothing to commit = patch was a no-op
                    logger.debug("Round %d: Blue git commit skipped (nothing to commit)", r)

            # ── Red's turn: attack the (now-patched) diff ────────────────────
            current_diff = git_diff(worktree, cfg.base_ref)

            try:
                red_attacks = cfg.red.attack(current_diff, worktree, history=transcript.red_history())
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            try:
                budget.add(red_attacks.tokens_used, cfg.red_model or cfg.model)
            except BudgetExceeded:
                result = _build_result(False, r, "budget")
                break

            # ── Verify each attack ────────────────────────────────────────────
            landed_attacks: list[Attack] = []
            landed_results: list[AttackResult] = []

            # Partition attacks by kind — test attacks are run sequentially
            # (they mutate the worktree); finding attacks are judged in parallel.
            finding_attacks = [atk for atk in red_attacks.attacks if atk.kind == "finding"]
            test_attacks = [atk for atk in red_attacks.attacks if atk.kind == "test"]

            # ── Test attacks: sequential (worktree mutation) ──────────────────
            for atk in test_attacks:
                # Write test file — write_test_file performs the path-traversal
                # security check internally; raises ValueError if path escapes worktree.
                try:
                    write_test_file(worktree, atk)
                except (ValueError, OSError) as exc:
                    logger.warning("Round %d: write_test_file failed (%s) — skipping attack", r, exc)
                    continue

                test_run = run_python_test(worktree, atk.test_path, timeout=30)  # type: ignore[arg-type]
                if test_run.failed:
                    attack_result = atk.with_evidence(test_run)
                    landed_attacks.append(atk)
                    landed_results.append(attack_result)

            # ── Finding attacks: parallel Judge calls ─────────────────────────
            if finding_attacks:
                if cfg.parallel_judge and len(finding_attacks) > 1:
                    max_workers = min(len(finding_attacks), cfg.judge_max_workers)
                    futures: dict[Attack, Future] = {}  # type: ignore[type-arg]
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        for atk in finding_attacks:
                            futures[atk] = executor.submit(
                                cfg.judge.judge, atk, current_diff, worktree
                            )
                    logger.debug(
                        "adversarial round %d: judged %d attack(s) in parallel",
                        r, len(finding_attacks),
                    )
                    # Collect results in original attack order (deterministic audit trail)
                    first_exc: BaseException | None = None
                    for atk in finding_attacks:
                        fut = futures[atk]
                        exc = fut.exception()
                        if exc is not None:
                            if isinstance(exc, BudgetExceeded):
                                result = _build_result(False, r, "budget")
                                first_exc = exc
                                break
                            if first_exc is None:
                                first_exc = exc
                            continue
                        judgment = fut.result()
                        try:
                            budget.add(judgment.tokens_used, cfg.judge_model or cfg.model)
                        except BudgetExceeded:
                            result = _build_result(False, r, "budget")
                            first_exc = BudgetExceeded()
                            break
                        if judgment.verdict == "valid":
                            landed_attacks.append(atk)
                            landed_results.append(atk.with_evidence(judgment))
                    if first_exc is not None and not isinstance(first_exc, BudgetExceeded):
                        raise first_exc  # re-raise non-budget exceptions
                else:
                    # Sequential path: parallel_judge=False or only one finding attack
                    for atk in finding_attacks:
                        try:
                            judgment = cfg.judge.judge(atk, current_diff, worktree)
                        except BudgetExceeded:
                            result = _build_result(False, r, "budget")
                            break

                        try:
                            budget.add(judgment.tokens_used, cfg.judge_model or cfg.model)
                        except BudgetExceeded:
                            result = _build_result(False, r, "budget")
                            break

                        if judgment.verdict == "valid":
                            attack_result = atk.with_evidence(judgment)
                            landed_attacks.append(atk)
                            landed_results.append(attack_result)

            # Check if we broke out of a finding-attack loop due to BudgetExceeded
            if result is not None:
                break

            # Write transcript for Red's turn (all attacks + which landed)
            transcript.write_red(r, red_attacks.attacks, landed_results)

            # Commit test files that Red wrote (for kind=test attacks that landed)
            test_attacks_written = [a for a in landed_attacks if a.kind == "test"]
            if test_attacks_written:
                try:
                    git_commit_in_worktree(worktree, f"test: anneal-red round {r}")
                except GitOperationError:
                    logger.debug("Round %d: Red git commit skipped (nothing to commit)", r)

            # ── Update landed_history ─────────────────────────────────────────
            landed_fps = [atk.fingerprint for atk in landed_attacks]
            landed_history.append(landed_fps)

            # ── Check termination conditions ──────────────────────────────────
            if not landed_attacks:
                red_empty_streak += 1
                logger.debug(
                    "Round %d: Red empty (streak %d/%d)", r, red_empty_streak, cfg.until_clean
                )
                if red_empty_streak >= cfg.until_clean:
                    result = _build_result(True, r, "clean", final_diff=current_diff)
                    break
                open_attacks = []
                continue

            # Red landed something — check for blue_stuck
            red_empty_streak = 0

            if blue_stuck(landed_history):
                logger.debug("Round %d: blue_stuck detected", r)
                result = _build_result(False, r, "blue_cannot_defend")
                break

            # Pass landed attacks to Blue next round
            open_attacks = landed_attacks

        else:
            # Loop exhausted without break → max_rounds
            result = _build_result(False, cfg.max_rounds, "max_rounds")

    except GitOperationError as exc:
        logger.error("GitOperationError during adversarial loop: %s", exc)
        result = _build_result(False, cfg.max_rounds, "patch_conflict")

    # ── Finalize ───────────────────────────────────────────────────────────────
    if result is None:
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
