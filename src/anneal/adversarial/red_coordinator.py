"""RedCoordinator: fans out to multiple Red agents in parallel and merges their attacks."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path

from anneal.adversarial.base import Attack, RedTurnOutput
from anneal.adversarial.red import Red

_log = logging.getLogger(__name__)

_MAX_COMBINED_ATTACKS = 15


class RedCoordinator:
    """Fan-out coordinator for multiple specialist Red agents.

    Runs each agent's ``attack()`` call in parallel via
    :class:`~concurrent.futures.ThreadPoolExecutor`, then merges and
    deduplicates the combined attack list by fingerprint (first occurrence
    wins).  The combined list is capped at ``_MAX_COMBINED_ATTACKS`` (15)
    attacks.

    Args:
        agents: List of :class:`~anneal.adversarial.red.Red` instances to fan
            out to (e.g. a mix of :class:`~anneal.adversarial.security_red.SecurityRed`,
            :class:`~anneal.adversarial.perf_red.PerfRed`, and
            :class:`~anneal.adversarial.logic_red.LogicRed`).
        max_workers: Maximum number of threads to use when running agents in
            parallel.  Defaults to 3 (one per specialist).
    """

    def __init__(self, agents: list[Red], max_workers: int = 3) -> None:
        self._agents = agents
        self._max_workers = max_workers

    def attack(
        self,
        diff: str,
        worktree: Path,
        history: list[Attack] | list[dict],
    ) -> RedTurnOutput:
        """Run all agents in parallel and return a deduplicated merged attack list.

        Each agent is called with the same ``diff``, ``worktree``, and
        ``history``.  Results are collected in agent-list order (deterministic
        ordering of first-occurrence wins for dedup).  Total tokens used is the
        sum across all agents.

        Args:
            diff: Current unified diff under attack.
            worktree: Path to the git worktree root.
            history: Previous attack records (passed through to each agent).

        Returns:
            :class:`~anneal.adversarial.base.RedTurnOutput` with deduplicated
            attacks (capped at 15) and total tokens consumed.
        """
        if not self._agents:
            _log.warning("RedCoordinator has no agents — returning empty round")
            return RedTurnOutput(attacks=[], tokens_used=0)

        n_workers = min(len(self._agents), self._max_workers)
        futures: dict[int, Future] = {}  # type: ignore[type-arg]

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            for idx, agent in enumerate(self._agents):
                futures[idx] = executor.submit(agent.attack, diff, worktree, history)

        _log.debug(
            "RedCoordinator: collected results from %d agent(s) in parallel",
            len(self._agents),
        )

        # Merge in agent order; dedup by fingerprint (first occurrence wins).
        seen_fps: set[str] = set()
        combined: list[Attack] = []
        total_tokens = 0

        for idx in range(len(self._agents)):
            fut = futures[idx]
            exc = fut.exception()
            if exc is not None:
                _log.warning(
                    "RedCoordinator: agent[%d] raised %s — skipping",
                    idx, exc,
                )
                continue

            turn_output: RedTurnOutput = fut.result()
            total_tokens += turn_output.tokens_used

            for attack in turn_output.attacks:
                if attack.fingerprint in seen_fps:
                    _log.debug(
                        "RedCoordinator: deduping fingerprint=%s from agent[%d]",
                        attack.fingerprint, idx,
                    )
                    continue
                seen_fps.add(attack.fingerprint)
                combined.append(attack)

        if len(combined) > _MAX_COMBINED_ATTACKS:
            _log.warning(
                "RedCoordinator: combined %d attacks exceeds cap %d — truncating",
                len(combined), _MAX_COMBINED_ATTACKS,
            )
            combined = combined[:_MAX_COMBINED_ATTACKS]

        _log.info(
            "RedCoordinator: %d unique attack(s) from %d agent(s) (%d tokens)",
            len(combined), len(self._agents), total_tokens,
        )
        return RedTurnOutput(attacks=combined, tokens_used=total_tokens)
