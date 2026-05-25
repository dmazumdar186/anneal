"""Unit tests for VotingJudge (T4.18)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from anneal.adversarial.base import Attack, JudgeOutput, attack_fingerprint
from anneal.adversarial.voting_judge import VotingJudge


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_attack() -> Attack:
    """Return a minimal finding-kind Attack for testing."""
    fp = attack_fingerprint("finding", ("src/foo.py",), "critical|null deref")
    return Attack(
        kind="finding",
        fingerprint=fp,
        target_files=("src/foo.py",),
        rationale="Red claims null deref on line 42.",
        severity="critical",
        claim="Null pointer dereference",
        evidence="foo = bar.baz",
        expected="bar is never None",
        actual="bar can be None on the error path",
    )


def _fake_judge(outputs: list[JudgeOutput]) -> MagicMock:
    """Build a mock Judge whose .judge() returns items from outputs in order."""
    mock = MagicMock()
    mock.judge.side_effect = outputs
    return mock


def _valid_output(rationale: str = "claim supported") -> JudgeOutput:
    return JudgeOutput(verdict="valid", rationale=rationale, tokens_used=10)


def _invalid_output(rationale: str = "claim not supported") -> JudgeOutput:
    return JudgeOutput(verdict="invalid", rationale=rationale, tokens_used=8)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestVotingJudge:
    """Tests for VotingJudge wrapper."""

    def test_samples_1_threshold_1_behaves_like_base(self) -> None:
        """VotingJudge(samples=1, vote_threshold=1) delegates to base exactly once."""
        attack = _make_attack()
        repo = Path("/tmp/repo")
        diff = "--- a/src/foo.py\n+++ b/src/foo.py\n"

        base = _fake_judge([_valid_output("base rationale")])
        vj = VotingJudge(base, samples=1, vote_threshold=1)

        result = vj.judge(attack, diff, repo)

        # Base called exactly once
        base.judge.assert_called_once_with(attack, diff, repo)
        # Output passes through unchanged
        assert result.verdict == "valid"
        assert result.rationale == "base rationale"
        assert result.tokens_used == 10

    def test_majority_verified_returns_verified(self) -> None:
        """2/3 'valid' votes (threshold=2) → final verdict is 'valid'."""
        attack = _make_attack()
        repo = Path("/tmp/repo")
        diff = "diff"

        outputs = [
            _valid_output("first valid"),
            _valid_output("second valid"),
            _invalid_output("third not valid"),
        ]
        base = _fake_judge(outputs)
        vj = VotingJudge(base, samples=3, vote_threshold=2)

        result = vj.judge(attack, diff, repo)

        assert base.judge.call_count == 3
        assert result.verdict == "valid"
        # Rationale comes from the FIRST verified sample
        assert result.rationale == "first valid"
        assert result.tokens_used == 10 + 10 + 8  # sum of all

    def test_minority_verified_returns_not_verified(self) -> None:
        """1/3 'valid' votes with threshold=2 → final verdict is 'invalid'."""
        attack = _make_attack()
        repo = Path("/tmp/repo")
        diff = "diff"

        outputs = [
            _valid_output("sole valid"),
            _invalid_output("first rejection"),
            _invalid_output("second rejection"),
        ]
        base = _fake_judge(outputs)
        vj = VotingJudge(base, samples=3, vote_threshold=2)

        result = vj.judge(attack, diff, repo)

        assert base.judge.call_count == 3
        assert result.verdict == "invalid"
        # Rationale from FIRST not-verified sample
        assert result.rationale == "first rejection"
        assert result.tokens_used == 10 + 8 + 8

    def test_validates_threshold_range(self) -> None:
        """VotingJudge(samples=2, vote_threshold=3) raises ValueError."""
        base = MagicMock()
        with pytest.raises(ValueError, match="vote_threshold.*cannot exceed samples"):
            VotingJudge(base, samples=2, vote_threshold=3)
