"""Unit tests for the prior-attempts loop-memory formatter and dataclass.

Covers:
  - empty history → ""
  - single round formatting (verdict, findings, rationale)
  - max-rounds cap (older rounds dropped, omission notice rendered)
  - rationale character cap (long rationale truncated with ellipsis)
  - PASS round with no rationale → "no patch applied" placeholder
"""

from __future__ import annotations

from anneal.audit.base import (
    PRIOR_ATTEMPTS_MAX_ROUNDS,
    PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP,
    PriorAttempt,
    format_prior_attempts,
)


def test_empty_history_returns_empty_string() -> None:
    """Empty history → empty string so callers can branch cheaply."""
    assert format_prior_attempts([]) == ""


def test_single_round_renders_verdict_findings_rationale() -> None:
    """Single round: all three components visible in the rendered block."""
    history = [
        PriorAttempt(
            round_num=1,
            verdict="FAIL",
            finding_summaries=["[HIGH] sql injection in query builder"],
            fixer_rationale="Switched to parameterised queries via psycopg2.sql.SQL.",
        ),
    ]
    md = format_prior_attempts(history)

    assert "## Prior round attempts (loop memory)" in md
    assert "### Round 1" in md
    assert "**Verdict:** FAIL" in md
    assert "[HIGH] sql injection in query builder" in md
    assert "Switched to parameterised queries" in md
    # The instructional preamble must be present so the auditor knows what to do
    # with this block.
    assert "AVOID re-raising" in md
    assert "AVOID proposing approaches the fixer already tried" in md


def test_no_findings_renders_none_marker() -> None:
    """A round with verdict WARNINGS but no parsed findings shows 'none'."""
    history = [
        PriorAttempt(round_num=2, verdict="WARNINGS", finding_summaries=[], fixer_rationale="noop"),
    ]
    md = format_prior_attempts(history)
    assert "**Findings raised:** none" in md


def test_empty_rationale_renders_placeholder() -> None:
    """An empty fixer_rationale renders the 'no patch applied' marker."""
    history = [
        PriorAttempt(round_num=3, verdict="FAIL", finding_summaries=["[LOW] x"], fixer_rationale=""),
    ]
    md = format_prior_attempts(history)
    assert "_(no patch applied this round)_" in md


def test_max_rounds_cap_drops_oldest() -> None:
    """When history exceeds PRIOR_ATTEMPTS_MAX_ROUNDS, only the most recent are kept."""
    history = [
        PriorAttempt(round_num=i, verdict="FAIL", finding_summaries=[f"[LOW] round {i}"], fixer_rationale=f"fix-{i}")
        for i in range(1, PRIOR_ATTEMPTS_MAX_ROUNDS + 4)  # 3 extras over the cap
    ]
    md = format_prior_attempts(history)

    # The omission notice must mention how many were dropped.
    assert "omitted 3 earlier round(s)" in md

    # Earliest rounds are gone.
    assert "round 1" not in md
    assert "round 2" not in md
    assert "round 3" not in md

    # The most recent PRIOR_ATTEMPTS_MAX_ROUNDS rounds survive.
    surviving_first = PRIOR_ATTEMPTS_MAX_ROUNDS + 3 - PRIOR_ATTEMPTS_MAX_ROUNDS + 1
    assert f"round {surviving_first}" in md  # boundary
    assert f"round {PRIOR_ATTEMPTS_MAX_ROUNDS + 3}" in md  # latest


def test_rationale_char_cap_truncates_with_ellipsis() -> None:
    """A rationale longer than the cap is truncated with a trailing ellipsis."""
    long_rationale = "x" * (PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP + 500)
    history = [
        PriorAttempt(
            round_num=1,
            verdict="FAIL",
            finding_summaries=["[HIGH] foo"],
            fixer_rationale=long_rationale,
        ),
    ]
    md = format_prior_attempts(history)

    # The full rationale is not present.
    assert long_rationale not in md
    # An ellipsis-truncated form is present.
    assert "…" in md
    # And the truncated chunk does not exceed the cap (plus the ellipsis char).
    # Find the rationale line.
    rationale_line = next(
        line for line in md.splitlines() if line.startswith("**Fixer rationale:** ")
    )
    rendered = rationale_line.removeprefix("**Fixer rationale:** ")
    # Length is bounded near the cap (allowing a few chars for the rstrip + ellipsis).
    assert len(rendered) <= PRIOR_ATTEMPTS_RATIONALE_CHAR_CAP


def test_short_rationale_unchanged() -> None:
    """A rationale under the cap is rendered verbatim."""
    history = [
        PriorAttempt(round_num=1, verdict="FAIL", finding_summaries=["[HIGH] x"], fixer_rationale="short"),
    ]
    md = format_prior_attempts(history)
    assert "**Fixer rationale:** short" in md
    assert "…" not in md
