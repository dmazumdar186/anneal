"""Unit tests for the adversarial Red-vs-Blue loop using DeterministicMockLLM.

Covers all termination paths:
  - converged (Red empty x N)
  - blue_cannot_defend (same fingerprint lands 3 rounds)
  - patch_conflict
  - max_rounds
  - budget
  - test_path outside worktree (security skip)
  - Judge valid / invalid finding
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from anneal.adversarial.blue import Blue
from anneal.adversarial.judge import Judge
from anneal.adversarial.red import Red
from anneal.config import AnnealConfig
from anneal.llm.mock import DeterministicMockLLM
from anneal.loop_adversarial import anneal_adversarial, blue_stuck


# ── Git fixture helpers ────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


def make_test_git_repo(tmp_path: Path) -> Path:
    """Init a git repo with one file and one commit. Return the repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "test@anneal"], repo)
    _git(["config", "user.name", "Anneal Test"], repo)
    (repo / "app.py").write_text('def add(a, b):\n    return a + b\n', encoding="utf-8")
    _git(["add", "app.py"], repo)
    _git(["commit", "-m", "initial commit"], repo)
    return repo


# ── Response helpers ───────────────────────────────────────────────────────────


def _mock_red_response_test(
    test_path: str = "tests/red/test_attack_001.py",
    test_body: str = "def test_x():\n    assert False, 'Red attack'\n",
    target_file: str = "app.py",
) -> str:
    """JSON Red would emit for a single kind='test' attack."""
    payload = {
        "attacks": [
            {
                "kind": "test",
                "target_files": [target_file],
                "test_path": test_path,
                "rationale": "Testing that the function fails edge case.",
                "test_body": test_body,
            }
        ]
    }
    return json.dumps(payload)


def _mock_red_response_finding(
    severity: str = "HIGH",
    claim: str = "Missing input validation",
    evidence: str = "Function add() does not check types.",
    target_file: str = "app.py",
) -> str:
    """JSON Red would emit for a single kind='finding' attack."""
    payload = {
        "attacks": [
            {
                "kind": "finding",
                "target_files": [target_file],
                "severity": severity,
                "claim": claim,
                "evidence": evidence,
                "rationale": "This is a security risk.",
                "expected": "Input validation present.",
                "actual": "No validation.",
            }
        ]
    }
    return json.dumps(payload)


def _mock_red_response_empty() -> str:
    """JSON for an empty round (no attacks)."""
    return json.dumps({"attacks": []})


def _mock_blue_response(diff_body: str = "# no-op", rationale: str = "auto", filename: str = "blue_fix.py") -> str:
    """Fenced diff string Blue returns when it has something to say."""
    return (
        "```diff\n"
        f"# rationale: {rationale}\n"
        "--- /dev/null\n"
        f"+++ b/{filename}\n"
        "@@ -0,0 +1,1 @@\n"
        f"+{diff_body}\n"
        "\n"
        "```\n"
    )


def _mock_blue_response_empty() -> str:
    """Blue returns a diff with no hunks → treated as nothing-to-do."""
    return (
        "```diff\n"
        "# rationale: nothing to do\n"
        "```\n"
    )


def _mock_judge_response(verdict: str, rationale: str = "Verified.") -> str:
    """JSON Judge returns."""
    return json.dumps({"verdict": verdict, "rationale": rationale})


# ── AnnealConfig factory ───────────────────────────────────────────────────────


def _make_adv_config(
    tmp_path: Path,
    red_responses: list[str | tuple[str, int]],
    blue_responses: list[str | tuple[str, int]],
    judge_responses: list[str | tuple[str, int]] | None = None,
    *,
    max_rounds: int = 10,
    until_clean: int = 2,
    max_cost_usd: float = 99.0,
) -> AnnealConfig:
    repo = make_test_git_repo(tmp_path)
    log_dir = tmp_path / "log"

    red_llm = DeterministicMockLLM(red_responses)
    blue_llm = DeterministicMockLLM(blue_responses)
    judge_llm = DeterministicMockLLM(judge_responses or [])

    return AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=max_rounds,
        until_clean=until_clean,
        max_cost_usd=max_cost_usd,
        log_dir=log_dir,
        red=Red(red_llm),
        blue=Blue(blue_llm),
        judge=Judge(judge_llm),
        model="claude-haiku-4-5-20251001",
    )


# ── blue_stuck unit tests ──────────────────────────────────────────────────────


def test_blue_stuck_false_when_short_history() -> None:
    assert blue_stuck([]) is False
    assert blue_stuck([["fp1"]]) is False
    assert blue_stuck([["fp1"], ["fp1"]]) is False


def test_blue_stuck_true_when_same_fp_in_last_3() -> None:
    assert blue_stuck([["fp1"], ["fp1"], ["fp1"]]) is True


def test_blue_stuck_false_when_different_fps() -> None:
    assert blue_stuck([["fp1"], ["fp2"], ["fp3"]]) is False


def test_blue_stuck_true_shared_in_last_3_of_longer_history() -> None:
    # Only last 3 matter — first entries can differ
    assert blue_stuck([["fpX"], ["fpX"], ["fp1"], ["fp1"], ["fp1"]]) is True


# ── Termination path tests ─────────────────────────────────────────────────────


def test_red_empty_two_rounds_converges(tmp_path: Path) -> None:
    """Red returns empty x2, Blue returns empty x2. converged=True, rounds=2, reason='clean'."""
    cfg = _make_adv_config(
        tmp_path,
        red_responses=[_mock_red_response_empty(), _mock_red_response_empty()],
        blue_responses=[_mock_blue_response_empty(), _mock_blue_response_empty()],
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is True
    assert result.reason == "clean"
    assert result.rounds == 2
    assert result.mode == "adversarial"


def test_red_lands_test_then_blue_fixes_then_red_empty(tmp_path: Path) -> None:
    """Round 1: Red writes failing test (lands). Rounds 2-3: Red empty → converged."""
    # The test that Red writes must actually fail when run via pytest.
    test_body = "def test_always_fails():\n    assert False, 'Planted failure'\n"

    cfg = _make_adv_config(
        tmp_path,
        red_responses=[
            # Round 1: Red attacks with a failing test
            _mock_red_response_test(
                test_path="tests/red/test_attack_001.py",
                test_body=test_body,
            ),
            # Round 2: Red empty
            _mock_red_response_empty(),
            # Round 3: Red empty → converged
            _mock_red_response_empty(),
        ],
        blue_responses=[
            # Round 1: Blue tries something (creates a new file, distinct per round)
            _mock_blue_response("# blue fix round 1", "addressing red attack", filename="blue_fix_r1.py"),
            # Round 2: Blue has nothing
            _mock_blue_response_empty(),
            # Round 3: Blue has nothing
            _mock_blue_response_empty(),
        ],
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is True
    assert result.rounds == 3
    assert result.reason == "clean"

    # The test file must exist on disk inside the worktree (it was written by write_test_file,
    # but the worktree gets cleaned up after the loop — verify via transcript instead).
    # The transcript red.json for round 1 should show landed_count=1.
    red_json = cfg.log_dir / "round_001" / "red.json"
    assert red_json.exists(), "red.json should be written for round 1"
    data = json.loads(red_json.read_text(encoding="utf-8"))
    assert data["landed_count"] == 1


def test_red_lands_finding_judge_valid(tmp_path: Path) -> None:
    """Red produces kind='finding'; Judge returns verdict='valid' → lands. Rounds 2-3 empty → converged."""
    cfg = _make_adv_config(
        tmp_path,
        red_responses=[
            _mock_red_response_finding(claim="Missing input validation"),
            _mock_red_response_empty(),
            _mock_red_response_empty(),
        ],
        blue_responses=[
            _mock_blue_response("# blue fix for finding", filename="blue_fix_r1.py"),
            _mock_blue_response_empty(),
            _mock_blue_response_empty(),
        ],
        judge_responses=[
            _mock_judge_response("valid", "The claim is correct."),
        ],
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is True
    assert result.rounds == 3
    assert result.reason == "clean"

    # Round 1 should have landed_count=1
    red_json = cfg.log_dir / "round_001" / "red.json"
    data = json.loads(red_json.read_text(encoding="utf-8"))
    assert data["landed_count"] == 1


def test_red_lands_finding_judge_invalid(tmp_path: Path) -> None:
    """Red produces kind='finding'; Judge returns verdict='invalid' → does NOT land.
    red_empty_streak increments. After 2 rounds with no landings → converged."""
    cfg = _make_adv_config(
        tmp_path,
        red_responses=[
            # Round 1: finding (Judge rejects)
            _mock_red_response_finding(claim="Spurious claim"),
            # Round 2: finding (Judge rejects again)
            _mock_red_response_finding(claim="Another spurious claim"),
        ],
        blue_responses=[
            _mock_blue_response_empty(),
            _mock_blue_response_empty(),
        ],
        judge_responses=[
            _mock_judge_response("invalid", "Claim is not supported by the diff."),
            _mock_judge_response("invalid", "Claim is not supported by the diff."),
        ],
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is True
    assert result.rounds == 2
    assert result.reason == "clean"

    # Neither round should have any landed attacks
    for rnd in (1, 2):
        red_json = cfg.log_dir / f"round_{rnd:03d}" / "red.json"
        data = json.loads(red_json.read_text(encoding="utf-8"))
        assert data["landed_count"] == 0


def test_blue_cannot_defend(tmp_path: Path) -> None:
    """Same attack fingerprint lands rounds 1, 2, 3 → blue_cannot_defend."""
    # The same test body with the same test_path → same fingerprint every round
    test_body = "def test_persistent_fail():\n    assert False, 'Cannot defend'\n"
    test_path = "tests/red/test_persistent.py"

    cfg = _make_adv_config(
        tmp_path,
        red_responses=[
            _mock_red_response_test(test_path=test_path, test_body=test_body),
            _mock_red_response_test(test_path=test_path, test_body=test_body),
            _mock_red_response_test(test_path=test_path, test_body=test_body),
        ],
        blue_responses=[
            # Blue creates distinct fix files each round but can't fix the failing test
            _mock_blue_response("# blue fix r1", filename="blue_fix_r1.py"),
            _mock_blue_response("# blue fix r2", filename="blue_fix_r2.py"),
            _mock_blue_response("# blue fix r3", filename="blue_fix_r3.py"),
        ],
        until_clean=2,
        max_rounds=10,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is False
    assert result.reason == "blue_cannot_defend"
    assert result.rounds == 3


def test_max_rounds_adversarial(tmp_path: Path) -> None:
    """Red always lands new attacks; never converges → max_rounds."""
    max_r = 3
    # Each round uses a distinct test_path so fingerprints differ (not blue_stuck)
    red_responses = [
        _mock_red_response_test(
            test_path=f"tests/red/test_attack_{i:03d}.py",
            test_body=f"def test_r{i}():\n    assert False\n",
        )
        for i in range(1, max_r + 1)
    ]
    # Each Blue response must create a distinct file to avoid patch conflicts
    blue_responses = [
        (
            "```diff\n"
            f"# rationale: blue fix r{i}\n"
            "--- /dev/null\n"
            f"+++ b/blue_fix_r{i}.py\n"
            "@@ -0,0 +1,1 @@\n"
            f"+# fix round {i}\n"
            "\n"
            "```\n"
        )
        for i in range(1, max_r + 1)
    ]

    cfg = _make_adv_config(
        tmp_path,
        red_responses=red_responses,
        blue_responses=blue_responses,
        max_rounds=max_r,
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is False
    assert result.reason == "max_rounds"
    assert result.rounds == max_r


def test_patch_conflict_adversarial(tmp_path: Path) -> None:
    """Blue returns a deliberately broken diff → patch_conflict."""
    broken_diff = (
        "```diff\n"
        "# rationale: broken patch\n"
        "--- a/does_not_exist.py\n"
        "+++ b/does_not_exist.py\n"
        "@@ -1,3 +1,3 @@\n"
        " line that does not exist\n"
        " neither does this\n"
        "-nor this\n"
        "+replacement\n"
        "```\n"
    )
    cfg = _make_adv_config(
        tmp_path,
        red_responses=[_mock_red_response_empty()],
        blue_responses=[broken_diff],
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is False
    assert result.reason == "patch_conflict"


def test_budget_exceeded_adversarial(tmp_path: Path) -> None:
    """max_cost_usd=0.0001. Budget check at round start trips before any LLM call → reason='budget'."""
    # We need the first budget.check() (before any LLM call) to fail.
    # But at round start the budget is 0 so check() won't fire until after add().
    # Strategy: use a tiny budget and a heavy response (5000 tokens × $2/M = $0.01).
    # The first Blue call adds tokens, which calls check() inside add(), raising BudgetExceeded.
    heavy_blue = (_mock_blue_response_empty(), 5000)
    cfg = _make_adv_config(
        tmp_path,
        red_responses=[_mock_red_response_empty()],
        blue_responses=[heavy_blue],
        max_cost_usd=0.0001,
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    assert result.converged is False
    assert result.reason == "budget"


def test_test_path_outside_worktree_skipped(tmp_path: Path) -> None:
    """Red emits test_path='../../escape/test_bad.py'. Attack is skipped, not landed."""
    # The test_path attempts to escape the worktree via ../
    # write_test_file will raise ValueError → loop skips, does not count as landed.
    escape_path = "../../escape/test_bad.py"

    cfg = _make_adv_config(
        tmp_path,
        red_responses=[
            _mock_red_response_test(
                test_path=escape_path,
                test_body="def test_evil():\n    assert False\n",
            ),
            # After skipping, Red returns empty x2 → converged
            _mock_red_response_empty(),
            _mock_red_response_empty(),
        ],
        blue_responses=[
            _mock_blue_response_empty(),
            _mock_blue_response_empty(),
            _mock_blue_response_empty(),
        ],
        until_clean=2,
    )
    result = anneal_adversarial(cfg)

    # Should converge because the escape attack was skipped (not landed)
    assert result.converged is True
    assert result.reason == "clean"

    # Round 1 red.json should show landed_count=0 (attack was skipped)
    red_json = cfg.log_dir / "round_001" / "red.json"
    data = json.loads(red_json.read_text(encoding="utf-8"))
    assert data["landed_count"] == 0

    # The escaped path must NOT exist on the filesystem
    escaped_resolved = (tmp_path / "escape" / "test_bad.py")
    assert not escaped_resolved.exists(), "Escaped test file must not exist on disk"
