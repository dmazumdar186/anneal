"""VotingJudge: multi-sample consensus wrapper for any Judge.

Runs the base Judge N times per finding and returns "verified" (verdict=="valid")
only if at least `vote_threshold` samples agree.  Hardens adversarial mode
against jailbreak-style Red attacks that fool a single Judge call.

Cost note
---------
Calls are sequential (not parallel) because the existing ThreadPoolExecutor in
``loop_adversarial.py`` already parallelises across attacks.  Per-finding
latency is dominated by single-call latency, not sequential-sampling overhead.

When the base Judge's LLM uses Anthropic prompt caching (system-prompt TTL 5 min),
samples 2-N read the cached prompt at ~0.1x input-token cost, so 3 samples costs
roughly 1.2x a single call, not 3x.
"""

from __future__ import annotations

import logging
from pathlib import Path

from anneal.adversarial.base import Attack, JudgeOutput
from anneal.adversarial.judge import Judge

_log = logging.getLogger(__name__)


class VotingJudge:
    """Judge wrapper that runs N samples and decides by majority vote.

    The verdict field of ``JudgeOutput`` is coerced to a binary "verified"
    signal: ``"valid"`` counts as verified=True; ``"invalid"`` and
    ``"uncertain"`` count as verified=False (matching the base Judge's strict
    defaults).

    If >=``vote_threshold`` samples return ``"valid"`` → final verdict is
    ``"valid"`` (use the first verified sample's rationale).
    Otherwise → final verdict is ``"invalid"`` (use the first not-verified
    sample's rationale, or aggregate rejections if all were non-verified).

    Args:
        base_judge:      Any ``Judge`` instance.
        samples:         Number of independent judge calls per finding (default 3).
        vote_threshold:  Minimum "valid" votes required to confirm the attack
                         (default 2).  Must satisfy ``1 <= vote_threshold <= samples``.

    Raises:
        ValueError: If ``vote_threshold < 1``, ``samples < 1``, or
                    ``vote_threshold > samples``.
    """

    def __init__(
        self,
        base_judge: Judge,
        samples: int = 3,
        vote_threshold: int = 2,
    ) -> None:
        if samples < 1:
            raise ValueError(f"samples must be >= 1, got {samples}")
        if vote_threshold < 1:
            raise ValueError(f"vote_threshold must be >= 1, got {vote_threshold}")
        if vote_threshold > samples:
            raise ValueError(
                f"vote_threshold ({vote_threshold}) cannot exceed samples ({samples})"
            )
        self._base = base_judge
        self.samples = samples
        self.vote_threshold = vote_threshold

    def judge(
        self,
        attack: Attack,
        diff: str,
        repo_root: Path,
    ) -> JudgeOutput:
        """Run base Judge N times and return a consensus JudgeOutput.

        Algorithm:
          1. Collect N ``JudgeOutput`` objects from the base Judge.
          2. Count how many returned verdict=``"valid"`` (verified=True).
          3. If count >= ``vote_threshold`` → return ``"valid"`` with the
             first verified sample's rationale.
          4. Else → return ``"invalid"`` with the first non-verified sample's
             rationale (or the last sample's rationale if all were verified
             but below threshold — degenerate case with samples < threshold
             is prevented by __init__).
          5. tokens_used = sum across all samples.

        Args:
            attack:    An ``Attack`` with ``kind="finding"`` (forwarded to base).
            diff:      Current diff context (forwarded to base).
            repo_root: Worktree path (forwarded to base).

        Returns:
            A single merged ``JudgeOutput``.
        """
        # ── Fast path: single sample behaves identically to base Judge ──────
        if self.samples == 1:
            return self._base.judge(attack, diff, repo_root)

        outputs: list[JudgeOutput] = []
        for i in range(self.samples):
            out = self._base.judge(attack, diff, repo_root)
            outputs.append(out)
            _log.debug(
                "VotingJudge sample %d/%d: verdict=%s",
                i + 1,
                self.samples,
                out.verdict,
            )

        # ── Tally verified ("valid") vs not-verified ─────────────────────────
        verified_outputs = [o for o in outputs if o.verdict == "valid"]
        not_verified_outputs = [o for o in outputs if o.verdict != "valid"]
        verified_count = len(verified_outputs)
        total_tokens = sum(o.tokens_used for o in outputs)

        _log.info(
            "VotingJudge: %d samples → %d verified / %d not-verified (threshold=%d)",
            self.samples,
            verified_count,
            len(not_verified_outputs),
            self.vote_threshold,
        )

        if verified_count >= self.vote_threshold:
            # Consensus: attack is verified — use first verified sample's rationale
            return JudgeOutput(
                verdict="valid",
                rationale=verified_outputs[0].rationale,
                tokens_used=total_tokens,
            )
        else:
            # Consensus: attack is not verified — use first not-verified rationale
            rationale = (
                not_verified_outputs[0].rationale
                if not_verified_outputs
                else outputs[-1].rationale
            )
            return JudgeOutput(
                verdict="invalid",
                rationale=rationale,
                tokens_used=total_tokens,
            )
