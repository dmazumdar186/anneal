"""Human-in-the-loop pause prompts for anneal failure modes.

This module is only active when ``AnnealConfig.interactive=True``.  All I/O
is injected via ``input_fn`` / ``output_fn`` so tests can stub them without
touching stdin/stdout.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable


class Intervention(str, Enum):
    """Actions the user can choose at an intervention pause."""

    CONTINUE = "CONTINUE"
    ABORT = "ABORT"
    RAISE_BUDGET = "RAISE_BUDGET"
    DISMISS_FINDING = "DISMISS_FINDING"
    ADD_HINT = "ADD_HINT"


class InterventionPrompter:
    """Present interactive menus at oscillation, budget, and patch-conflict pauses.

    Args:
        input_fn:  Callable that reads one line of user input (default: built-in
                   ``input``).  Replaced with a stub in tests.
        output_fn: Callable that prints a line to the user (default: built-in
                   ``print``).  Replaced with a stub in tests.
    """

    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[..., None] = print,
    ) -> None:
        self._input = input_fn
        self._out = output_fn

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _prompt_choice(self, prompt: str, options: int) -> int:
        """Prompt until the user enters an integer in [1, options]."""
        while True:
            raw = self._input(prompt).strip()
            try:
                choice = int(raw)
                if 1 <= choice <= options:
                    return choice
            except ValueError:
                pass
            self._out(f"  Please enter a number between 1 and {options}.")

    # ── Public API ────────────────────────────────────────────────────────────

    def prompt_at_oscillation(
        self,
        report: object,
        current_round: int,
    ) -> tuple[Intervention, dict]:
        """Pause when the loop detects oscillation.

        Prints the oscillating finding(s) from *report* and offers three options.

        Args:
            report:        The ``AuditReport`` from the current round.
            current_round: The 1-based loop round number.

        Returns:
            ``(Intervention, payload)`` where payload may be:
            - ``{}`` for ABORT / CONTINUE
            - ``{"fingerprint": str}`` for DISMISS_FINDING
            - ``{"hint": str}`` for ADD_HINT
        """
        findings = getattr(report, "findings", [])

        self._out("")
        self._out(f"[anneal] Oscillation detected at round {current_round}.")
        self._out("  The following finding(s) have appeared for 3+ consecutive rounds:")
        for i, f in enumerate(findings, 1):
            fp = _fingerprint(f)
            self._out(f"    [{i}] ({fp}) {getattr(f, 'severity', '?')} — {getattr(f, 'summary', str(f))}")
        self._out("")
        self._out("  Options:")
        self._out("    1) Abort — stop the run now")
        self._out("    2) Dismiss finding — suppress it and continue")
        self._out("    3) Add hint — inject a user hint and resume (may oscillate again)")
        self._out("    4) Continue — resume without changes (will likely oscillate again)")
        self._out("")

        choice = self._prompt_choice("  Your choice [1-4]: ", 4)

        if choice == 1:
            return Intervention.ABORT, {}

        if choice == 2:
            # Ask which finding to dismiss if there are multiple
            if len(findings) == 1:
                fp = _fingerprint(findings[0])
            else:
                idx = self._prompt_choice(
                    f"  Which finding to dismiss [1-{len(findings)}]: ", len(findings)
                )
                fp = _fingerprint(findings[idx - 1])
            return Intervention.DISMISS_FINDING, {"fingerprint": fp}

        if choice == 3:
            hint = self._input("  Enter hint for next round: ").strip()
            return Intervention.ADD_HINT, {"hint": hint}

        # choice == 4
        return Intervention.CONTINUE, {}

    def prompt_at_budget(
        self,
        current_cost: float,
        max_cost: float,
    ) -> tuple[Intervention, dict]:
        """Pause when the budget ceiling is hit.

        Args:
            current_cost: Accumulated spend so far (USD).
            max_cost:     Current budget ceiling (USD).

        Returns:
            ``(Intervention, payload)`` where payload may be:
            - ``{}`` for ABORT / CONTINUE
            - ``{"new_max_usd": float}`` for RAISE_BUDGET
        """
        self._out("")
        self._out(
            f"[anneal] Budget limit reached: ${current_cost:.4f} spent"
            f" (limit: ${max_cost:.2f})."
        )
        self._out("")
        self._out("  Options:")
        self._out("    1) Abort — stop the run now")
        self._out("    2) Raise budget — add more USD and continue")
        self._out("    3) Continue at risk — resume without raising the limit")
        self._out("")

        choice = self._prompt_choice("  Your choice [1-3]: ", 3)

        if choice == 1:
            return Intervention.ABORT, {}

        if choice == 2:
            extra_str = self._input("  Extra USD to add (e.g. 5.00): ").strip()
            try:
                extra = float(extra_str)
            except ValueError:
                extra = 0.0
            new_max = max_cost + extra
            return Intervention.RAISE_BUDGET, {"new_max_usd": new_max}

        # choice == 3 — continue at risk
        return Intervention.CONTINUE, {}

    def prompt_at_patch_conflict(
        self,
        patch_excerpt: str,
        conflict_files: list[str],
    ) -> tuple[Intervention, dict]:
        """Pause when a generated patch fails to apply.

        Args:
            patch_excerpt:  A short excerpt of the failing patch (for display).
            conflict_files: File paths that reported conflicts.

        Returns:
            ``(Intervention, payload)`` where payload is always ``{}``.
            Supported interventions: ABORT, CONTINUE (skip this round).
        """
        self._out("")
        self._out("[anneal] Patch conflict: the fixer's patch did not apply cleanly.")
        if conflict_files:
            self._out(f"  Conflicting files: {', '.join(conflict_files)}")
        if patch_excerpt:
            self._out(f"  Patch excerpt:\n{patch_excerpt[:400]}")
        self._out("")
        self._out("  Options:")
        self._out("    1) Abort — stop the run now")
        self._out("    2) Skip this round — discard the patch and continue to the next round")
        self._out("")

        choice = self._prompt_choice("  Your choice [1-2]: ", 2)

        if choice == 1:
            return Intervention.ABORT, {}

        # choice == 2 — skip round, continue
        return Intervention.CONTINUE, {}


# ── Private helpers ────────────────────────────────────────────────────────────


def _fingerprint(finding: object) -> str:
    """Return the fingerprint for a finding, using anneal's canonical function when available."""
    try:
        from anneal.audit.base import finding_fingerprint  # noqa: PLC0415
        return finding_fingerprint(finding)  # type: ignore[arg-type]
    except Exception:
        # Fallback: hash the summary string
        import hashlib  # noqa: PLC0415
        summary = getattr(finding, "summary", str(finding))
        return hashlib.sha256(summary.encode()).hexdigest()[:16]
