"""CompositeSastRunner: fan-out to multiple SAST runners, deduplicates findings."""

from __future__ import annotations

import logging
from pathlib import Path

from anneal.sast.base import SastFinding, SastRunner

logger = logging.getLogger(__name__)


class CompositeSastRunner:
    """Run multiple SAST runners in sequence and deduplicate findings.

    Deduplication key: ``(file, line, rule_id)`` — first occurrence wins.
    This prevents the same issue from being reported twice when two runners
    share rule coverage (e.g. ruff and semgrep both flag a security issue).

    Args:
        runners: Ordered list of :class:`~anneal.sast.base.SastRunner` objects.
                 Each runner is called with the same ``worktree`` and
                 ``changed_files`` arguments.  Runners that are not installed
                 silently return empty lists per the SastRunner protocol.
    """

    def __init__(self, runners: list[SastRunner]) -> None:
        self._runners = runners

    def run(self, worktree: Path, changed_files: list[str]) -> list[SastFinding]:
        """Invoke each runner in order, concatenate and deduplicate findings.

        Args:
            worktree:      Absolute path to the git worktree root.
            changed_files: Relative file paths to analyse.

        Returns:
            Deduplicated list of :class:`~anneal.sast.base.SastFinding` objects,
            preserving first-occurrence order.
        """
        all_findings: list[SastFinding] = []
        seen: set[tuple[str, int, str]] = set()

        for runner in self._runners:
            runner_name = type(runner).__name__
            findings = runner.run(worktree, changed_files)
            logger.debug(
                "CompositeSastRunner: %s returned %d finding(s)",
                runner_name,
                len(findings),
            )

            for finding in findings:
                dedup_key = (finding.file, finding.line, finding.rule_id)
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    all_findings.append(finding)
                else:
                    logger.debug(
                        "CompositeSastRunner: deduping %s:%d [%s] from %s",
                        finding.file,
                        finding.line,
                        finding.rule_id,
                        runner_name,
                    )

        logger.info(
            "CompositeSastRunner: %d unique finding(s) across %d runner(s)",
            len(all_findings),
            len(self._runners),
        )
        return all_findings
