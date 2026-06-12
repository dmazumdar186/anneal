"""Unit tests for the anneal batch subcommand and batch runner.

Tests:
  1. Two-entry refs-file: both rows are dispatched and aggregated in results.
  2. One-row failure: batch continues and the final report includes the failure
     alongside successful rows.

Both tests mock the underlying classic-mode loop so no real LLM or git
operations are performed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anneal.batch import BatchEntry, BatchRowResult, BatchSummary, _parse_refs_file, run_batch
from anneal.result import AnnealResult


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_result(converged: bool = True, rounds: int = 2, cost: float = 0.01) -> AnnealResult:
    return AnnealResult(
        converged=converged,
        rounds=rounds,
        reason="clean" if converged else "max_rounds",
        final_diff=None,
        log_dir=None,
        total_cost_usd=cost,
        mode="classic",
    )


def _write_json_refs(tmp_path: Path, entries: list[dict]) -> Path:
    refs_file = tmp_path / "refs.json"
    refs_file.write_text(json.dumps(entries), encoding="utf-8")
    return refs_file


def _write_text_refs(tmp_path: Path, lines: list[str]) -> Path:
    refs_file = tmp_path / "refs.txt"
    refs_file.write_text("\n".join(lines), encoding="utf-8")
    return refs_file


# ── Test 1: two-entry refs-file, both rows invoked and aggregated ──────────────


def test_batch_two_rows_both_dispatched(tmp_path: Path) -> None:
    """Both refs-file entries are dispatched; results aggregated correctly."""
    refs_file = _write_json_refs(
        tmp_path,
        [
            {"repo": str(tmp_path / "repo_a"), "ref": "HEAD~1"},
            {"repo": str(tmp_path / "repo_b"), "ref": "HEAD~1"},
        ],
    )

    result_a = _make_result(converged=True, cost=0.01)
    result_b = _make_result(converged=False, rounds=10, cost=0.02)
    call_count = 0

    def _fake_run_one(entry, mode, tier, api_keys, extra_kwargs):
        nonlocal call_count
        call_count += 1
        label = entry.label()
        if "repo_a" in entry.repo:
            result = result_a
        else:
            result = result_b
        return BatchRowResult(
            label=label,
            repo=entry.repo,
            ref=entry.ref,
            diff_file=entry.diff_file,
            status="ok",
            converged=result.converged,
            rounds=result.rounds,
            reason=result.reason,
            cost_usd=result.total_cost_usd,
            log_dir=None,
            error=None,
            wall_seconds=0.1,
        )

    with patch("anneal.batch._run_one", side_effect=_fake_run_one):
        summary = run_batch(
            refs_file,
            mode="classic",
            max_workers=2,
            tier="balanced",
            api_keys={},
            extra_kwargs={},
        )

    # Both rows were dispatched
    assert call_count == 2, f"Expected 2 _run_one calls, got {call_count}"

    assert summary.total == 2
    assert summary.ok == 2
    assert summary.failed == 0
    assert summary.converged == 1  # only repo_a converged
    assert abs(summary.total_cost_usd - 0.03) < 1e-9

    # Results file written
    out_path = refs_file.with_suffix(refs_file.suffix + ".batch_results.json")
    assert out_path.exists(), "batch_results.json must be written"
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["total"] == 2
    assert len(data["rows"]) == 2

    labels = {r["label"] for r in data["rows"]}
    assert any("repo_a" in lbl for lbl in labels)
    assert any("repo_b" in lbl for lbl in labels)


# ── Test 2: one row fails, batch continues and reports the failure ─────────────


def test_batch_one_row_fails_continues(tmp_path: Path) -> None:
    """When one row raises an exception, the batch continues; summary reflects the failure."""
    refs_file = _write_json_refs(
        tmp_path,
        [
            {"repo": str(tmp_path / "repo_good"), "ref": "HEAD~1"},
            {"repo": str(tmp_path / "repo_bad"), "ref": "HEAD~1"},
        ],
    )

    ok_row_result = BatchRowResult(
        label="repo_good@HEAD~1",
        repo=str(tmp_path / "repo_good"),
        ref="HEAD~1",
        diff_file=None,
        status="ok",
        converged=True,
        rounds=2,
        reason="clean",
        cost_usd=0.01,
        log_dir=None,
        error=None,
        wall_seconds=0.1,
    )

    def _fake_run_one(entry, mode, tier, api_keys, extra_kwargs):
        if "repo_bad" in entry.repo:
            # Simulate a row-level failure (e.g. MissingCredentials, GitOperationError)
            raise RuntimeError("Simulated failure for repo_bad")
        return ok_row_result

    with patch("anneal.batch._run_one", side_effect=_fake_run_one):
        summary = run_batch(
            refs_file,
            mode="classic",
            max_workers=2,
            tier="balanced",
            api_keys={},
            extra_kwargs={},
        )

    assert summary.total == 2
    assert summary.ok == 1
    assert summary.failed == 1
    assert summary.converged == 1

    # The failed row must appear in the output with status="failed"
    failed_rows = [r for r in summary.rows if r.status == "failed"]
    assert len(failed_rows) == 1
    assert "repo_bad" in failed_rows[0].repo
    assert failed_rows[0].error is not None
    assert "Simulated failure" in failed_rows[0].error

    # Output file still written even when some rows fail
    out_path = refs_file.with_suffix(refs_file.suffix + ".batch_results.json")
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["failed"] == 1


# ── Test 3: parse_refs_file — JSON and plain-text formats ─────────────────────


def test_parse_refs_file_json(tmp_path: Path) -> None:
    refs_file = _write_json_refs(
        tmp_path,
        [
            {"repo": "/dev/foo", "ref": "HEAD~1"},
            {"repo": "/dev/bar", "ref": "abc123", "diff_file": "patch.diff"},
        ],
    )
    entries = _parse_refs_file(refs_file)
    assert len(entries) == 2
    assert entries[0].repo == "/dev/foo"
    assert entries[0].ref == "HEAD~1"
    assert entries[0].diff_file is None
    assert entries[1].diff_file == "patch.diff"


def test_parse_refs_file_plain_text(tmp_path: Path) -> None:
    refs_file = _write_text_refs(tmp_path, ["/dev/foo:HEAD~1", "# comment", "/dev/bar:abc123"])
    entries = _parse_refs_file(refs_file)
    assert len(entries) == 2
    assert entries[0].repo == "/dev/foo"
    assert entries[0].ref == "HEAD~1"
    assert entries[1].ref == "abc123"


# ── Test 4: CLI smoke — batch subcommand wired into main() ────────────────────


def test_batch_cli_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI dispatches to _run_batch; exits 0 when all rows succeed."""
    refs_file = _write_json_refs(
        tmp_path,
        [{"repo": str(tmp_path / "repo_a"), "ref": "HEAD~1"}],
    )

    ok_row = BatchRowResult(
        label="repo_a@HEAD~1",
        repo=str(tmp_path / "repo_a"),
        ref="HEAD~1",
        diff_file=None,
        status="ok",
        converged=True,
        rounds=2,
        reason="clean",
        cost_usd=0.01,
        log_dir=None,
        error=None,
        wall_seconds=0.1,
    )

    def _fake_run_batch(refs_path, *, mode, max_workers, tier, api_keys, extra_kwargs):
        # Write the expected output file so CLI doesn't crash on the print
        out = refs_path.with_suffix(refs_path.suffix + ".batch_results.json")
        out.write_text(json.dumps({"rows": []}), encoding="utf-8")
        return BatchSummary(
            total=1,
            ok=1,
            failed=0,
            skipped=0,
            converged=1,
            total_cost_usd=0.01,
            wall_seconds=0.5,
            rows=[ok_row],
        )

    import anneal.batch as batch_mod
    monkeypatch.setattr(batch_mod, "run_batch", _fake_run_batch)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "anneal",
            "batch",
            str(refs_file),
            "--mode", "classic",
            "--max-workers", "2",
            "--tier", "balanced",
        ],
    )

    from anneal.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0


# ── Test 5: judge-parallelism flags forwarded to run_batch extra_kwargs ─────────


def test_batch_cli_judge_flags_forwarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--no-parallel-judge and --judge-max-workers reach run_batch's extra_kwargs."""
    refs_file = _write_json_refs(
        tmp_path,
        [{"repo": str(tmp_path / "repo_a"), "ref": "HEAD~1"}],
    )

    captured_extra_kwargs: dict = {}

    def _fake_run_batch(refs_path, *, mode, max_workers, tier, api_keys, extra_kwargs):
        captured_extra_kwargs.update(extra_kwargs)
        # Write the expected output file so CLI print doesn't crash
        out = refs_path.with_suffix(refs_path.suffix + ".batch_results.json")
        out.write_text(json.dumps({"rows": []}), encoding="utf-8")
        return BatchSummary(
            total=1,
            ok=1,
            failed=0,
            skipped=0,
            converged=1,
            total_cost_usd=0.00,
            wall_seconds=0.1,
            rows=[
                BatchRowResult(
                    label="repo_a@HEAD~1",
                    repo=str(tmp_path / "repo_a"),
                    ref="HEAD~1",
                    diff_file=None,
                    status="ok",
                    converged=True,
                    rounds=1,
                    reason="clean",
                    cost_usd=0.00,
                    log_dir=None,
                    error=None,
                    wall_seconds=0.1,
                )
            ],
        )

    import anneal.batch as batch_mod
    monkeypatch.setattr(batch_mod, "run_batch", _fake_run_batch)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "anneal",
            "batch",
            str(refs_file),
            "--mode", "adversarial",
            "--no-parallel-judge",
            "--judge-max-workers", "2",
        ],
    )

    from anneal.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0

    # Verify flags were forwarded
    assert captured_extra_kwargs.get("parallel_judge") is False, (
        f"parallel_judge should be False, got {captured_extra_kwargs.get('parallel_judge')!r}"
    )
    assert captured_extra_kwargs.get("judge_max_workers") == 2, (
        f"judge_max_workers should be 2, got {captured_extra_kwargs.get('judge_max_workers')!r}"
    )
