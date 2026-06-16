"""VotingAuditor: multi-sample consensus wrapper for any Auditor.

Runs the base auditor N times and keeps only findings that appear in at least
`vote_threshold` samples (matched by finding_fingerprint). Verdict is decided
by majority; ties break toward the most severe verdict (FAIL > WARNINGS > PASS).

Cache note
----------
When the base auditor is backed by an Anthropic LLM with prompt caching enabled
(T1.2), samples 2-N read the cached system prompt at ~0.1x input-token cost.
So 3 samples costs roughly 1 + 0.1 + 0.1 = 1.2x a single sample, not 3x.
"""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from anneal.audit.base import AuditReport, Auditor, Finding, Verdict, finding_fingerprint

logger = logging.getLogger(__name__)

_VERDICT_SEVERITY: dict[Verdict, int] = {"FAIL": 2, "WARNINGS": 1, "PASS": 0}


def _most_severe(verdicts: list[Verdict]) -> Verdict:
    """Return the most severe verdict from a list (FAIL > WARNINGS > PASS)."""
    return max(verdicts, key=lambda v: _VERDICT_SEVERITY[v])


class VotingAuditor:
    """Auditor wrapper that runs N samples and merges by consensus.

    Args:
        base_auditor:    Any object satisfying the Auditor Protocol.
        samples:         Number of independent audit calls per round (default 3).
        vote_threshold:  Minimum number of samples a finding must appear in to
                         survive (default 2). Must satisfy 1 <= vote_threshold <= samples.

    Raises:
        ValueError: If vote_threshold < 1, samples < 1, or vote_threshold > samples.
    """

    def __init__(
        self,
        base_auditor: Auditor,
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
        self._base = base_auditor
        self.samples = samples
        self.vote_threshold = vote_threshold

    def audit(
        self,
        diff: str,
        repo_root: Path,
        *,
        sast_findings: str = "",
        repograph_context: str = "",
        semantic_summary: str = "",
        prior_attempts: str = "",
    ) -> AuditReport:
        """Run base_auditor N times and return a consensus-merged AuditReport.

        Algorithm:
          1. Collect N AuditReport objects from base_auditor.
          2. Fingerprint every finding across all reports; count occurrences.
          3. Keep findings whose fingerprint appears in >= vote_threshold samples.
             Use the FIRST occurrence's full Finding object for the merged report.
          4. Verdict = majority across samples; ties → most severe.
          5. raw_markdown = sample 1's raw_markdown (sufficient for transcript).
          6. tokens_used = sum across all samples.

        Args:
            diff:              Unified diff string to audit.
            repo_root:         Path to the repository root.
            sast_findings:     Optional pre-pass SAST output forwarded to each sample.
            repograph_context: Optional repo-graph caller context forwarded to each sample.
            semantic_summary:  Optional AST-derived semantic diff summary forwarded
                               to each sample.
            prior_attempts:    Optional formatted prior-round history forwarded to
                               each sample (loop-with-memory; see audit.base
                               format_prior_attempts).

        Returns:
            A single merged AuditReport.
        """
        # ── Fast path: single sample behaves identically to the base auditor ──
        if self.samples == 1:
            return self._base.audit(
                diff,
                repo_root,
                sast_findings=sast_findings,
                repograph_context=repograph_context,
                semantic_summary=semantic_summary,
                prior_attempts=prior_attempts,
            )

        # ── Parallel sampling: run all N calls concurrently ───────────────────
        # CostTracker is already thread-safe (guarded by threading.Lock), so
        # no extra locking is needed here. We submit all samples at once and
        # collect in index order to keep the audit trail deterministic.
        reports: list[AuditReport] = [None] * self.samples  # type: ignore[list-item]

        def _run_sample(index: int) -> tuple[int, AuditReport]:
            report = self._base.audit(
                diff,
                repo_root,
                sast_findings=sast_findings,
                repograph_context=repograph_context,
                semantic_summary=semantic_summary,
                prior_attempts=prior_attempts,
            )
            logger.debug(
                "VotingAuditor sample %d/%d: verdict=%s findings=%d",
                index + 1,
                self.samples,
                report.verdict,
                len(report.findings),
            )
            return index, report

        with ThreadPoolExecutor(max_workers=self.samples) as executor:
            futures = {executor.submit(_run_sample, i): i for i in range(self.samples)}
            for future in as_completed(futures):
                idx, report = future.result()  # re-raises if _run_sample raised
                reports[idx] = report

        # ── Consensus: count fingerprint occurrences across samples ───────────
        # fp → first Finding encountered (sample 1 wins on wording)
        first_occurrence: dict[str, Finding] = {}
        fp_counts: Counter[str] = Counter()

        for report in reports:
            # Use a set per-report so one sample can't vote twice for the same fp
            seen_in_this_sample: set[str] = set()
            for finding in report.findings:
                fp = finding_fingerprint(finding)
                if fp not in seen_in_this_sample:
                    fp_counts[fp] += 1
                    seen_in_this_sample.add(fp)
                if fp not in first_occurrence:
                    first_occurrence[fp] = finding

        consensus_findings: list[Finding] = [
            first_occurrence[fp]
            for fp, count in fp_counts.items()
            if count >= self.vote_threshold
        ]

        logger.info(
            "VotingAuditor: %d samples → %d total fingerprints, %d survive threshold=%d",
            self.samples,
            len(fp_counts),
            len(consensus_findings),
            self.vote_threshold,
        )

        # ── Verdict: majority vote, ties → most severe ────────────────────────
        # Avoid most_common(1) for the tie-break path: Counter.most_common ordering
        # is insertion-order-dependent (CPython detail, not a language guarantee).
        # Instead, find max count explicitly then pass all tied verdicts to
        # _most_severe so the result is deterministic regardless of insertion order.
        verdict_counts: Counter[Verdict] = Counter(r.verdict for r in reports)
        max_count = max(verdict_counts.values())
        tied = [v for v, c in verdict_counts.items() if c == max_count]
        majority_verdict = _most_severe(tied)

        # ── Merge auxiliary fields from sample 1 ─────────────────────────────
        primary = reports[0]

        return AuditReport(
            verdict=majority_verdict,
            findings=consensus_findings,
            silent_drops=primary.silent_drops,
            logic_disagreements=primary.logic_disagreements,
            summary=primary.summary,
            raw_markdown=primary.raw_markdown,
            tokens_used=sum(r.tokens_used for r in reports),
        )
