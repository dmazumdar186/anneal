"""CLI canary smoke test — end-to-end path through cli.main with mocked auditor.

One integration smoke test: builds 2 minimal fixtures (1 planted, 1 clean),
monkeypatches build_llm to return a mock auditor, invokes cli.main, asserts
exit-0 and canary_report.json exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

from anneal.llm.mock import DeterministicMockLLM


# ── Minimal fixture helpers ────────────────────────────────────────────────────


def _make_planted(base: Path, name: str, regex: str, code: str = "for i in range(1, n): pass\n") -> None:
    d = base / "planted_bugs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "before.py").write_text(code, encoding="utf-8")
    (d / "after.py").write_text("for i in range(n): pass\n", encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({
            "name": name,
            "category": "planted_bug",
            "severity": "MEDIUM",
            "expected_finding_signature_regex": regex,
        }),
        encoding="utf-8",
    )


def _make_clean(base: Path, name: str) -> None:
    d = base / "clean_diffs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "before.py").write_text("x = 1\n", encoding="utf-8")
    (d / "after.py").write_text("x = 1  # comment\n", encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({
            "name": name,
            "category": "clean_diff",
            "expected_verdict": "PASS",
            "expected_findings_count": 0,
        }),
        encoding="utf-8",
    )


def _make_pass_response() -> str:
    return (
        "**Verdict:** PASS\n\n"
        "### Issues Found\n\n"
        "### Silent Drops\nNone detected\n\n"
        "### Logic Disagreements\nNone detected\n\n"
        "### Summary\nAll good."
    )


def _make_fail_response(summary: str) -> str:
    return (
        f"**Verdict:** FAIL\n\n"
        f"### Issues Found\n"
        f"- [Severity: MEDIUM] {summary}\n"
        f"  Impact: test\n"
        f"  Recommended fix: fix it\n\n"
        f"### Silent Drops\nNone detected\n\n"
        f"### Logic Disagreements\nNone detected\n\n"
        f"### Summary\nFound issues."
    )


# ── Smoke test ─────────────────────────────────────────────────────────────────


def test_cli_canary_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run cli.main(["canary", ...]) with mocked build_llm; assert exit-0 + report exists."""
    # Build minimal fixture tree
    fixtures_dir = tmp_path / "fixtures"
    _make_planted(fixtures_dir, "off_by_one", r"off[- ]?by[- ]?one")
    _make_clean(fixtures_dir, "clean_refactor")

    log_dir = tmp_path / ".canary"

    # Mock LLM: first call returns a FAIL with matching finding (planted),
    #           second call returns PASS (clean diff)
    mock_llm = DeterministicMockLLM([
        (_make_fail_response("off-by-one in loop"), 500),
        (_make_pass_response(), 300),
    ])
    # Patch build_llm so no real API key is needed
    def _mock_build_llm(provider, model, api_keys):  # noqa: ANN001
        return mock_llm

    # Also patch the fixtures_dir inside _run_canary so it uses our tmp fixtures
    import anneal as _anneal_pkg

    # Patch at the factory module level — _run_canary imports it from there at call time
    monkeypatch.setattr("anneal.llm.factory.build_llm", _mock_build_llm)

    # We pass --log-dir explicitly and override the fixtures_dir via monkeypatching
    # the run_canary call to use our fixtures_dir.
    from anneal.canary import runner as _runner_mod

    original_run_canary = _runner_mod.run_canary

    def _patched_run_canary(auditor, fixtures_dir=None, **kwargs):  # noqa: ANN001
        # Always redirect to our tmp fixtures, ignoring what cli computed
        return original_run_canary(auditor, fixtures_dir=tmp_path / "fixtures", **kwargs)

    monkeypatch.setattr(_runner_mod, "run_canary", _patched_run_canary)

    # Invoke cli.main — expect SystemExit(0)
    from anneal.cli import main

    sys_argv_backup = sys.argv[:]
    sys.argv = [
        "anneal",
        "canary",
        "--subset", "all",
        "--log-dir", str(log_dir),
        "--tier", "balanced",
    ]
    try:
        with pytest.raises(SystemExit) as exc_info:
            main()
    finally:
        sys.argv = sys_argv_backup

    # Exit code 0 = overall_pass=True
    assert exc_info.value.code == 0, (
        f"Expected exit code 0 (overall_pass), got {exc_info.value.code}"
    )

    # canary_report.json must exist and be parseable
    report_path = log_dir / "canary_report.json"
    assert report_path.exists(), "canary_report.json was not written"
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["overall_pass"] is True
    assert data["planted_bugs"]["total"] == 1
    assert data["clean_diffs"]["total"] == 1
