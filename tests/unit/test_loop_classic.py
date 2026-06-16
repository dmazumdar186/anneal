"""Unit tests for the classic auditor+fixer loop using DeterministicMockLLM.

All tests use a tiny in-process git repo (tmp_path) so no real API calls are made.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from anneal.audit.pipeline_auditor import PipelineAuditor
from anneal.config import AnnealConfig
from anneal.fix.default_fixer import DefaultFixer
from anneal.llm.mock import DeterministicMockLLM
from anneal.loop_classic import anneal_classic, oscillation_detected


# ── Git fixture helpers ────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command; raise on failure."""
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


def _init_repo(base: Path) -> Path:
    """Create a tiny git repo with one initial commit. Return the repo path."""
    repo = base / "repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "test@anneal"], repo)
    _git(["config", "user.name", "Anneal Test"], repo)
    # Write a starting file
    (repo / "hello.py").write_text('print("hello")\n', encoding="utf-8")
    _git(["add", "hello.py"], repo)
    _git(["commit", "-m", "initial commit"], repo)
    return repo


def _make_config(
    tmp_path: Path,
    auditor_responses: list[str | tuple[str, int]],
    fixer_responses: list[str | tuple[str, int]] | None = None,
    *,
    max_rounds: int = 10,
    until_clean: int = 2,
    max_cost_usd: float = 99.0,
    no_worktree: bool = False,
    dry_run: bool = False,
) -> tuple[AnnealConfig, DeterministicMockLLM, DeterministicMockLLM]:
    """
    Build an AnnealConfig wired to two DeterministicMockLLMs (one for audit,
    one for fix), using a real tiny git repo under tmp_path.

    Returns:
        (cfg, auditor_mock, fixer_mock)
    """
    repo = _init_repo(tmp_path)

    auditor_llm = DeterministicMockLLM(auditor_responses)
    fixer_llm = DeterministicMockLLM(fixer_responses or [])

    auditor = PipelineAuditor(auditor_llm)
    fixer = DefaultFixer(fixer_llm)

    log_dir = tmp_path / "log"

    cfg = AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=max_rounds,
        until_clean=until_clean,
        max_cost_usd=max_cost_usd,
        dry_run=dry_run,
        no_worktree=no_worktree,
        diff_path=None,
        log_dir=log_dir,
        auditor=auditor,
        fixer=fixer,
        model="claude-haiku-4-5-20251001",
    )
    return cfg, auditor_llm, fixer_llm


# ── Response helpers ───────────────────────────────────────────────────────────


def _pass_response() -> str:
    """Return minimal PASS audit markdown."""
    return (
        "**Verdict:** PASS\n\n"
        "### Issues Found\n"
        "None detected\n\n"
        "### Silent Drops\n"
        "None detected\n\n"
        "### Logic Disagreements\n"
        "None detected\n\n"
        "### Summary\n"
        "All checks passed.\n"
    )


def _fail_response(findings: list[tuple[str, str]]) -> str:
    """Return FAIL audit markdown with the given (severity, summary) findings.

    Args:
        findings: list of (severity, summary) tuples.
    """
    lines = [
        "**Verdict:** FAIL\n\n",
        "### Issues Found\n",
    ]
    for severity, summary in findings:
        lines.append(f"- [Severity: {severity}] {summary}\n")
        lines.append(f"  Impact: Something bad could happen.\n")
        lines.append(f"  Recommended fix: Fix the issue.\n")
    lines += [
        "\n### Silent Drops\n",
        "None detected\n\n",
        "### Logic Disagreements\n",
        "None detected\n\n",
        "### Summary\n",
        f"{len(findings)} issue(s) found.\n",
    ]
    return "".join(lines)


def _patch_response(new_filename: str = "fix_01.py", content: str = "# fix") -> str:
    """Return a valid fixer response that creates a new file via unified diff.

    Creating a new file (/dev/null → b/<name>) avoids context-matching issues
    on subsequent rounds — each patch targets a fresh file that doesn't exist yet.

    The trailing newline after the +line is load-bearing: git apply requires a
    newline after the last hunk line; parse_patch_response strips the outer fence
    but the inner newline must survive.
    """
    return (
        "```diff\n"
        "# rationale: fix issues found by auditor\n"
        f"--- /dev/null\n"
        f"+++ b/{new_filename}\n"
        "@@ -0,0 +1,1 @@\n"
        f"+{content}\n"
        "\n"
        "```\n"
    )


def _broken_patch_response() -> str:
    """Return a fixer response with a diff that will NOT apply (wrong context)."""
    return (
        "```diff\n"
        "# rationale: attempt to fix but this won't apply\n"
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -1,3 +1,3 @@\n"
        " this line does not exist in hello.py\n"
        " neither does this one\n"
        "-nor this\n"
        "+fix attempt\n"
        "```\n"
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_converges_after_two_clean_rounds(tmp_path: Path) -> None:
    """Auditor returns PASS+no findings twice → converged=True, rounds=2."""
    cfg, _, _ = _make_config(
        tmp_path,
        auditor_responses=[_pass_response(), _pass_response()],
        until_clean=2,
    )
    result = anneal_classic(cfg)

    assert result.converged is True
    assert result.rounds == 2
    assert result.reason == "clean"
    assert result.mode == "classic"


def test_finding_then_two_clean(tmp_path: Path) -> None:
    """1 finding round → fix applied → 2 clean rounds → converged=True, rounds=3."""
    cfg, _, _ = _make_config(
        tmp_path,
        auditor_responses=[
            _fail_response([("HIGH", "off-by-one in loop bound")]),
            _pass_response(),
            _pass_response(),
        ],
        fixer_responses=[_patch_response("fix_r1.py")],
        until_clean=2,
    )
    result = anneal_classic(cfg)

    assert result.converged is True
    assert result.rounds == 3
    assert result.reason == "clean"


def test_max_rounds_exceeded(tmp_path: Path) -> None:
    """Auditor always FAIL, fixer always trivial patch → reason=max_rounds."""
    # We need max_rounds auditor calls + max_rounds fixer calls.
    # Use max_rounds=3 to keep the test fast.
    max_r = 3
    auditor_responses = [
        _fail_response([("MEDIUM", f"issue at round {i}")]) for i in range(1, max_r + 1)
    ]
    # Each round's patch must be different so git actually applies a new change
    fixer_responses = [_patch_response(f"fix_r{i}.py") for i in range(1, max_r + 1)]

    cfg, _, _ = _make_config(
        tmp_path,
        auditor_responses=auditor_responses,
        fixer_responses=fixer_responses,
        max_rounds=max_r,
        until_clean=2,
    )
    result = anneal_classic(cfg)

    assert result.converged is False
    assert result.reason == "max_rounds"
    assert result.rounds == max_r


def test_oscillation_detected(tmp_path: Path) -> None:
    """Same finding fingerprint in 3 consecutive rounds → reason=oscillation."""
    # Round 1: FAIL with finding X + apply patch
    # Round 2: FAIL with same finding X + apply patch
    # Round 3: FAIL with same finding X → oscillation
    same_finding = [("HIGH", "persistent null-dereference bug")]
    cfg, _, _ = _make_config(
        tmp_path,
        auditor_responses=[
            _fail_response(same_finding),
            _fail_response(same_finding),
            _fail_response(same_finding),
        ],
        fixer_responses=[
            _patch_response("fix_osc_1.py"),
            _patch_response("fix_osc_2.py"),
        ],
        max_rounds=10,
        until_clean=2,
    )
    result = anneal_classic(cfg)

    assert result.converged is False
    assert result.reason == "oscillation"
    # Oscillation is detected on round 3 (after 3 rounds with the same fingerprint)
    assert result.rounds == 3


def test_patch_conflict(tmp_path: Path) -> None:
    """Fixer returns a broken diff that won't apply → reason=patch_conflict."""
    cfg, _, _ = _make_config(
        tmp_path,
        auditor_responses=[_fail_response([("HIGH", "some bug")])],
        fixer_responses=[_broken_patch_response()],
        max_rounds=5,
        until_clean=2,
    )
    result = anneal_classic(cfg)

    assert result.converged is False
    assert result.reason == "patch_conflict"
    assert result.rounds == 1


def test_budget_exceeded(tmp_path: Path) -> None:
    """max_cost_usd=0.001 → first audit response trips budget → reason=budget."""
    # Use 5000 tokens at $5/M = $0.025 — well above max_cost_usd=0.001
    heavy_response = (_fail_response([("HIGH", "expensive finding")]), 5000)

    cfg, _, _ = _make_config(
        tmp_path,
        auditor_responses=[heavy_response],
        fixer_responses=[],
        max_rounds=10,
        until_clean=2,
        max_cost_usd=0.001,
    )
    result = anneal_classic(cfg)

    assert result.converged is False
    assert result.reason == "budget"


# ── oscillation_detected unit tests ───────────────────────────────────────────


def test_oscillation_helper_not_triggered_with_short_history() -> None:
    """oscillation_detected returns False when history has fewer than 2 entries."""
    from anneal.audit.base import Finding
    f = Finding(severity="HIGH", summary="x", file="", impact="", recommended_fix="")
    assert oscillation_detected([f], []) is False
    assert oscillation_detected([f], [frozenset()]) is False


def test_oscillation_helper_triggered() -> None:
    """oscillation_detected returns True when same fingerprint appears × 3."""
    from anneal.audit.base import Finding, finding_fingerprint
    f = Finding(severity="HIGH", summary="same bug", file="x.py", impact="", recommended_fix="")
    fp = finding_fingerprint(f)
    history = [frozenset([fp]), frozenset([fp])]
    assert oscillation_detected([f], history) is True


def test_oscillation_helper_not_triggered_different_findings() -> None:
    """oscillation_detected returns False when findings differ each round."""
    from anneal.audit.base import Finding, finding_fingerprint
    f1 = Finding(severity="HIGH", summary="bug A", file="x.py", impact="", recommended_fix="")
    f2 = Finding(severity="HIGH", summary="bug B", file="x.py", impact="", recommended_fix="")
    f3 = Finding(severity="HIGH", summary="bug C", file="x.py", impact="", recommended_fix="")
    fp1 = finding_fingerprint(f1)
    fp2 = finding_fingerprint(f2)
    history = [frozenset([fp1]), frozenset([fp2])]
    assert oscillation_detected([f3], history) is False


# ── SAST pre-pass integration test ────────────────────────────────────────────


def test_sast_findings_passed_to_auditor(tmp_path: Path) -> None:
    """When sast_runners contains a FakeSastRunner, the auditor receives a
    non-empty sast_findings kwarg containing both fake findings."""
    from pathlib import Path as _Path
    from anneal.audit.base import AuditReport
    from anneal.config import AnnealConfig
    from anneal.fix.default_fixer import DefaultFixer
    from anneal.llm.mock import DeterministicMockLLM
    from anneal.sast.base import SastFinding, SastRunner
    from anneal.loop_classic import anneal_classic

    # ── Fake SAST runner returning 2 deterministic findings ──────────────────
    class FakeSastRunner:
        def run(self, worktree: _Path, changed_files: list[str]) -> list[SastFinding]:
            return [
                SastFinding(
                    severity="high",
                    file="hello.py",
                    line=1,
                    rule_id="FAKE001",
                    message="fake finding one",
                    tool="fake",
                ),
                SastFinding(
                    severity="low",
                    file="hello.py",
                    line=2,
                    rule_id="FAKE002",
                    message="fake finding two",
                    tool="fake",
                ),
            ]

    # ── Mock auditor that captures kwargs and always returns PASS ─────────────
    captured_kwargs: list[dict] = []

    class CapturingAuditor:
        def audit(  # noqa: ARG002
            self,
            diff: str,
            repo_root: _Path,
            *,
            sast_findings: str = "",
            repograph_context: str = "",
            semantic_summary: str = "",  # noqa: ARG002
            prior_attempts: str = "",  # noqa: ARG002
        ) -> AuditReport:
            captured_kwargs.append({"sast_findings": sast_findings})
            return AuditReport(
                verdict="PASS",
                findings=[],
                silent_drops=[],
                logic_disagreements=[],
                summary="All clear.",
                raw_markdown="**Verdict:** PASS\n### Issues Found\nNone detected\n"
                             "### Silent Drops\nNone detected\n"
                             "### Logic Disagreements\nNone detected\n"
                             "### Summary\nAll clear.\n",
                tokens_used=10,
            )

    repo = _init_repo(tmp_path)
    fixer_llm = DeterministicMockLLM([])
    fixer = DefaultFixer(fixer_llm)
    log_dir = tmp_path / "log"

    cfg = AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=2,
        until_clean=2,
        max_cost_usd=99.0,
        dry_run=False,
        no_worktree=False,
        diff_path=None,
        log_dir=log_dir,
        auditor=CapturingAuditor(),
        fixer=fixer,
        model="claude-haiku-4-5-20251001",
        sast_runners=[FakeSastRunner()],
    )

    result = anneal_classic(cfg)

    assert result.converged is True
    assert len(captured_kwargs) >= 1
    first_call = captured_kwargs[0]
    assert first_call["sast_findings"] != "", "auditor must receive non-empty sast_findings"
    assert "FAKE001" in first_call["sast_findings"]
    assert "FAKE002" in first_call["sast_findings"]
    assert "fake finding one" in first_call["sast_findings"]
    assert "fake finding two" in first_call["sast_findings"]


# ── Repo-graph context integration test ───────────────────────────────────────


def test_repograph_context_passed_to_auditor(tmp_path: Path) -> None:
    """When repo_graph contains a FakeRepoGraph, the auditor receives a non-empty
    repograph_context kwarg that contains the symbol name and both caller files."""
    from pathlib import Path as _Path
    from anneal.audit.base import AuditReport
    from anneal.config import AnnealConfig
    from anneal.fix.default_fixer import DefaultFixer
    from anneal.llm.mock import DeterministicMockLLM
    from anneal.repograph.base import Callsite, Symbol
    from anneal.loop_classic import anneal_classic

    # ── FakeRepoGraph test double ────────────────────────────────────────────
    class FakeRepoGraph:
        def extract_symbols(self, file_path: str) -> list[Symbol]:
            return [
                Symbol(
                    name="foo",
                    kind="function",
                    file=file_path,
                    line=1,
                    qualified_name="foo",
                )
            ]

        def find_callers(self, symbol_name: str, search_root: _Path) -> list[Callsite]:  # noqa: ARG002
            return [
                Callsite(
                    caller_file="bar.py",
                    caller_line=10,
                    caller_function="run",
                    called_symbol=symbol_name,
                ),
                Callsite(
                    caller_file="baz.py",
                    caller_line=20,
                    caller_function=None,
                    called_symbol=symbol_name,
                ),
            ]

    # ── Mock auditor that captures kwargs and always returns PASS ─────────────
    captured_kwargs: list[dict] = []

    class CapturingAuditor:
        def audit(  # noqa: ARG002
            self,
            diff: str,
            repo_root: _Path,
            *,
            sast_findings: str = "",
            repograph_context: str = "",
            semantic_summary: str = "",  # noqa: ARG002
            prior_attempts: str = "",  # noqa: ARG002
        ) -> AuditReport:
            captured_kwargs.append({"repograph_context": repograph_context})
            return AuditReport(
                verdict="PASS",
                findings=[],
                silent_drops=[],
                logic_disagreements=[],
                summary="All clear.",
                raw_markdown=(
                    "**Verdict:** PASS\n### Issues Found\nNone detected\n"
                    "### Silent Drops\nNone detected\n"
                    "### Logic Disagreements\nNone detected\n"
                    "### Summary\nAll clear.\n"
                ),
                tokens_used=10,
            )

    # ── Build a repo with a real diff so repograph can extract symbols ────────
    # _init_repo creates one commit with hello.py.  We write a diff that adds a
    # line to hello.py; diff_path causes loop_classic to apply it before the
    # first git_diff call, giving us a non-empty diff referencing hello.py.
    repo = _init_repo(tmp_path)

    diff_file = tmp_path / "initial.diff"
    diff_file.write_text(
        "--- a/hello.py\n"
        "+++ b/hello.py\n"
        "@@ -1,1 +1,2 @@\n"
        ' print("hello")\n'
        '+# repograph test\n',
        encoding="utf-8",
    )

    fixer_llm = DeterministicMockLLM([])
    fixer = DefaultFixer(fixer_llm)
    log_dir = tmp_path / "log"

    cfg = AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=2,
        until_clean=2,
        max_cost_usd=99.0,
        dry_run=False,
        no_worktree=False,
        diff_path=diff_file,
        log_dir=log_dir,
        auditor=CapturingAuditor(),
        fixer=fixer,
        model="claude-haiku-4-5-20251001",
        sast_runners=[],          # explicitly disabled — no SAST pre-pass
        repo_graph=FakeRepoGraph(),
    )

    result = anneal_classic(cfg)

    assert result.converged is True
    assert len(captured_kwargs) >= 1
    first_call = captured_kwargs[0]
    assert first_call["repograph_context"] != "", (
        "auditor must receive non-empty repograph_context"
    )
    assert "foo" in first_call["repograph_context"], (
        "repograph_context must contain the symbol name 'foo'"
    )
    assert "bar.py" in first_call["repograph_context"], (
        "repograph_context must contain caller file 'bar.py'"
    )
    assert "baz.py" in first_call["repograph_context"], (
        "repograph_context must contain caller file 'baz.py'"
    )


# ── Deterministic replay (T4.14) ──────────────────────────────────────────────


def test_deterministic_sets_temperature_and_seed(tmp_path: Path) -> None:
    """AnnealConfig(deterministic=True, seed=42) must forward temperature=0.0
    and seed=42 to the LLM adapter on every complete() call."""
    from pathlib import Path as _Path
    from anneal.audit.base import AuditReport
    from anneal.config import AnnealConfig
    from anneal.fix.default_fixer import DefaultFixer
    from anneal.llm.mock import DeterministicMockLLM
    from anneal.loop_classic import anneal_classic

    # ── Capturing LLM: records all kwargs passed to complete() ──────────────
    captured_calls: list[dict] = []

    class CapturingLLM:
        """Drop-in LLM that records temperature/seed kwargs and always returns PASS."""

        # Satisfy _apply_determinism's attribute look-up
        _temperature: float = 1.0
        _seed: int | None = None

        def complete(
            self,
            system: str,  # noqa: ARG002
            user: str,  # noqa: ARG002
            response_format: str = "text",  # noqa: ARG002
            *,
            temperature: float | None = None,
            seed: int | None = None,
        ) -> tuple[str, int]:
            # _apply_determinism sets self._temperature; honour it when caller
            # passes temperature=None (same contract as ClaudeLLM / OpenRouterLLM).
            effective_temp = self._temperature if temperature is None else temperature
            effective_seed = self._seed if seed is None else seed
            captured_calls.append({"temperature": effective_temp, "seed": effective_seed})
            return (
                "**Verdict:** PASS\n### Issues Found\nNone detected\n"
                "### Silent Drops\nNone detected\n"
                "### Logic Disagreements\nNone detected\n"
                "### Summary\nAll clear.\n",
                100,
            )

    repo = _init_repo(tmp_path)
    log_dir = tmp_path / "log"

    capturing_llm = CapturingLLM()
    from anneal.audit.pipeline_auditor import PipelineAuditor
    auditor = PipelineAuditor(capturing_llm)
    fixer = DefaultFixer(DeterministicMockLLM([]))

    cfg = AnnealConfig(
        repo=repo,
        base_ref="HEAD",
        max_rounds=2,
        until_clean=2,
        max_cost_usd=99.0,
        dry_run=False,
        no_worktree=False,
        diff_path=None,
        log_dir=log_dir,
        auditor=auditor,
        fixer=fixer,
        model="claude-haiku-4-5-20251001",
        sast_runners=[],
        deterministic=True,
        seed=42,
    )

    result = anneal_classic(cfg)

    assert result.converged is True
    assert len(captured_calls) >= 1, "auditor LLM must have been called at least once"
    # Every call must carry temperature=0.0 and seed=42
    for call in captured_calls:
        assert call["temperature"] == 0.0, f"expected temperature=0.0, got {call['temperature']}"
        assert call["seed"] == 42, f"expected seed=42, got {call['seed']}"
