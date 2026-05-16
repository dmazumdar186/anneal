"""Canary suite runner — fixture discovery, diff synthesis, catch-logic, transcripts.

Public API
----------
run_canary(auditor, fixtures_dir, ...) -> CanaryReport
    Run all fixtures (or a subset) and return an aggregate report.  Also writes
    per-fixture transcripts and canary_report.json to disk when save_transcripts=True.

FixtureResult
    Outcome for a single fixture: caught flag, regex match, raw AuditReport, cost.

CanaryReport
    Aggregate over planted_bugs / perturbations / clean_diffs with pass/fail verdict.

Pass criteria (per plan):
    planted_bugs  : 100% catch rate  (any miss → overall_pass=False)
    perturbations : ≥90% catch rate
    clean_diffs   : 0 false positives (any clean diff flagged → overall_pass=False)

Diff synthesis uses stdlib difflib so the runner is dependency-free and cross-platform.
No subprocess, no git commands.
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import re
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import anneal
from anneal.audit.base import AuditReport
from anneal.cost import CostTracker

if TYPE_CHECKING:
    from anneal.audit.base import Auditor


# ── Types ──────────────────────────────────────────────────────────────────────

CanaryCategory = Literal["planted_bug", "perturbation", "clean_diff"]
CanarySubset = Literal["planted", "perturb", "clean", "all"]

_PLANTED_PASS_RATE = 1.0   # 100%
_PERTURB_PASS_RATE = 0.90  # ≥90%
# clean_diffs: zero false positives → any false-positive yields overall_pass=False


# ── Per-fixture result ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FixtureResult:
    """Outcome of running the auditor against a single fixture.

    Attributes
    ----------
    fixture_name:
        Relative path-like key, e.g. ``"planted_bugs/off_by_one"`` or
        ``"perturbations/off_by_one/v1_renamed.py"``.
    category:
        One of ``"planted_bug"``, ``"perturbation"``, ``"clean_diff"``.
    caught:
        For planted/perturbation: True when the expected regex matched at least one
        finding summary.  For clean_diff: True when verdict==PASS and findings==0.
    matched_finding_summary:
        The first finding summary that matched the expected regex (or None).
    expected_signature_regex:
        The regex from meta.json that was used to test planted/perturbation fixtures.
        None for clean_diffs.
    audit_report:
        The full parsed AuditReport returned by the auditor.
    tokens_used:
        Total tokens consumed for this fixture's auditor call.
    cost_usd:
        Estimated USD cost for this fixture's auditor call.
    error:
        Populated with the exception message when auditor.audit() raised.
        caught is False when error is set.
    """

    fixture_name: str
    category: CanaryCategory
    caught: bool
    matched_finding_summary: str | None
    expected_signature_regex: str | None
    audit_report: AuditReport
    tokens_used: int
    cost_usd: float
    error: str | None = None


# ── Aggregate report ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CanaryReport:
    """Aggregate result of a full (or subset) canary run.

    Attributes
    ----------
    ran_at:
        ISO-8601 UTC timestamp when the run started.
    tier:
        Tier string passed to run_canary (e.g. "balanced").
    models:
        Per-role model identifiers, e.g. ``{"auditor": "claude-haiku-4-5-20251001"}``.
    planted_bugs:
        Sub-suite summary: total, caught_round_1, rate, details.
    perturbations:
        Sub-suite summary: total, caught, rate, failed.
    clean_diffs:
        Sub-suite summary: total, false_positives, rate.
    total_cost_usd:
        Sum of all per-fixture costs.
    overall_pass:
        True when all three sub-suites meet their pass thresholds.
    """

    ran_at: str
    tier: str
    models: dict[str, str]
    planted_bugs: dict
    perturbations: dict
    clean_diffs: dict
    total_cost_usd: float
    overall_pass: bool


# ── Diff synthesis helpers ─────────────────────────────────────────────────────

def _synthesize_diff_planted(before_py_path: Path) -> str:
    """Synthesize a unified diff that introduces the buggy file from /dev/null.

    Mimics ``git diff --no-index /dev/null <file>`` output so the auditor sees
    the same format as a real git diff.

    Args:
        before_py_path: Path to the ``before.py`` (buggy) file.

    Returns:
        Unified diff string with ``--- /dev/null`` and ``+++ b/<name>`` headers.
    """
    content = before_py_path.read_text(encoding="utf-8")
    lines_after = content.splitlines(keepends=True)
    # Ensure last line ends with newline for clean diff output
    if lines_after and not lines_after[-1].endswith("\n"):
        lines_after[-1] = lines_after[-1] + "\n"

    diff_lines = list(
        difflib.unified_diff(
            [],               # /dev/null → empty
            lines_after,
            fromfile="/dev/null",
            tofile=f"b/{before_py_path.name}",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


def _synthesize_diff_clean(before_py_path: Path, after_py_path: Path) -> str:
    """Synthesize a unified diff from before.py → after.py.

    Args:
        before_py_path: The original (before) file.
        after_py_path: The modified (after) file.

    Returns:
        Unified diff string with proper headers.
    """
    before_text = before_py_path.read_text(encoding="utf-8")
    after_text = after_py_path.read_text(encoding="utf-8")

    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{before_py_path.name}",
            tofile=f"b/{after_py_path.name}",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


# ── Fixture discovery ──────────────────────────────────────────────────────────

def _load_meta(meta_path: Path) -> dict:
    """Load and return the parsed JSON from a meta.json file."""
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _discover_planted(fixtures_dir: Path) -> list[dict]:
    """Walk fixtures_dir/planted_bugs/ and return one descriptor per fixture.

    Each descriptor:
        {
            "fixture_name": "planted_bugs/off_by_one",
            "category": "planted_bug",
            "diff": <synthesized unified diff str>,
            "expected_regex": <str from meta.json>,
        }
    """
    results = []
    planted_root = fixtures_dir / "planted_bugs"
    if not planted_root.exists():
        return results

    for subdir in sorted(planted_root.iterdir()):
        if not subdir.is_dir():
            continue
        before = subdir / "before.py"
        meta_path = subdir / "meta.json"
        if not before.exists() or not meta_path.exists():
            continue
        meta = _load_meta(meta_path)
        diff = _synthesize_diff_planted(before)
        results.append({
            "fixture_name": f"planted_bugs/{subdir.name}",
            "category": "planted_bug",
            "diff": diff,
            "expected_regex": meta.get("expected_finding_signature_regex", ""),
        })
    return results


def _discover_perturbations(fixtures_dir: Path) -> list[dict]:
    """Walk fixtures_dir/perturbations/ and return one descriptor per variant.

    Each variant (v1_renamed.py, v2_reformatted.py, v3_restructured.py) is its
    own fixture, sharing the meta.json expected regex from the parent dir.

    Each descriptor:
        {
            "fixture_name": "perturbations/off_by_one/v1_renamed.py",
            "category": "perturbation",
            "diff": <synthesized unified diff str>,
            "expected_regex": <str from meta.json>,
        }
    """
    results = []
    perturb_root = fixtures_dir / "perturbations"
    if not perturb_root.exists():
        return results

    for subdir in sorted(perturb_root.iterdir()):
        if not subdir.is_dir():
            continue
        meta_path = subdir / "meta.json"
        if not meta_path.exists():
            continue
        meta = _load_meta(meta_path)
        expected_regex = meta.get("expected_finding_signature_regex", "")

        # Collect all variant .py files (v1_*.py, v2_*.py, v3_*.py, etc.)
        for variant_file in sorted(subdir.glob("v*.py")):
            diff = _synthesize_diff_planted(variant_file)
            results.append({
                "fixture_name": f"perturbations/{subdir.name}/{variant_file.name}",
                "category": "perturbation",
                "diff": diff,
                "expected_regex": expected_regex,
            })
    return results


def _discover_clean(fixtures_dir: Path) -> list[dict]:
    """Walk fixtures_dir/clean_diffs/ and return one descriptor per fixture.

    Each descriptor:
        {
            "fixture_name": "clean_diffs/add_docstring",
            "category": "clean_diff",
            "diff": <synthesized unified diff str>,
            "expected_regex": None,
        }
    """
    results = []
    clean_root = fixtures_dir / "clean_diffs"
    if not clean_root.exists():
        return results

    for subdir in sorted(clean_root.iterdir()):
        if not subdir.is_dir():
            continue
        before = subdir / "before.py"
        after = subdir / "after.py"
        meta_path = subdir / "meta.json"
        if not before.exists() or not after.exists() or not meta_path.exists():
            continue
        diff = _synthesize_diff_clean(before, after)
        results.append({
            "fixture_name": f"clean_diffs/{subdir.name}",
            "category": "clean_diff",
            "diff": diff,
            "expected_regex": None,
        })
    return results


# ── Catch logic ────────────────────────────────────────────────────────────────

def _check_caught(
    report: AuditReport,
    category: CanaryCategory,
    expected_regex: str | None,
) -> tuple[bool, str | None]:
    """Determine whether the auditor output counts as 'caught' for this category.

    Returns:
        (caught: bool, matched_finding_summary: str | None)
    """
    if category in ("planted_bug", "perturbation"):
        if not expected_regex:
            # No regex to match — treat as caught if there are any findings
            if report.findings:
                return True, report.findings[0].summary
            return False, None
        for f in report.findings:
            if re.search(expected_regex, f.summary, re.IGNORECASE):
                return True, f.summary
        return False, None

    else:  # clean_diff
        caught = report.verdict == "PASS" and len(report.findings) == 0
        return caught, None


# ── Per-fixture output ─────────────────────────────────────────────────────────

def _save_fixture_outputs(
    log_dir: Path,
    result: FixtureResult,
) -> None:
    """Write audit.md, audit.json, and result.json for one fixture.

    Output directory: log_dir/<fixture_name_with_slashes_as_underscores>/
    (slashes → underscores to keep it as a flat single directory level)
    """
    slug = result.fixture_name.replace("/", "_")
    out_dir = log_dir / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # audit.md — raw markdown from the LLM
    (out_dir / "audit.md").write_text(result.audit_report.raw_markdown, encoding="utf-8")

    # audit.json — serialised AuditReport (findings as dicts)
    audit_dict = {
        "verdict": result.audit_report.verdict,
        "findings": [
            {
                "severity": f.severity,
                "summary": f.summary,
                "file": f.file,
                "impact": f.impact,
                "recommended_fix": f.recommended_fix,
                "line_start": f.line_start,
                "line_end": f.line_end,
            }
            for f in result.audit_report.findings
        ],
        "silent_drops": result.audit_report.silent_drops,
        "logic_disagreements": result.audit_report.logic_disagreements,
        "summary": result.audit_report.summary,
        "tokens_used": result.audit_report.tokens_used,
    }
    (out_dir / "audit.json").write_text(
        json.dumps(audit_dict, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # result.json — FixtureResult as dict (without the full audit_report to keep it small)
    result_dict = {
        "fixture_name": result.fixture_name,
        "category": result.category,
        "caught": result.caught,
        "matched_finding_summary": result.matched_finding_summary,
        "expected_signature_regex": result.expected_signature_regex,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "error": result.error,
    }
    (out_dir / "result.json").write_text(
        json.dumps(result_dict, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Main runner ────────────────────────────────────────────────────────────────

def run_canary(
    auditor: "Auditor",
    fixtures_dir: Path | None = None,
    subset: CanarySubset = "all",
    log_dir: Path | None = None,
    tier: str = "balanced",
    auditor_model: str = "unknown",
    judge_model: str | None = None,
    cost_tracker: CostTracker | None = None,
    save_transcripts: bool = True,
) -> CanaryReport:
    """Run the canary suite and return an aggregate CanaryReport.

    Reads fixtures from fixtures_dir (defaults to the bundled fixtures under
    src/anneal/canary/fixtures/).  For each fixture, calls auditor.audit() once
    on the synthesized diff, checks the finding signature, and (when
    save_transcripts=True) persists per-fixture outputs to log_dir.

    The aggregate canary_report.json is written to the top of log_dir.

    Args:
        auditor:
            Any object satisfying the Auditor protocol.
        fixtures_dir:
            Root of the canary fixtures tree.  Defaults to the bundled fixtures
            packaged alongside anneal.
        subset:
            Which sub-suite(s) to run: "planted", "perturb", "clean", or "all".
        log_dir:
            Where to write transcripts and canary_report.json.  Defaults to
            ``Path.cwd() / ".canary" / <ISO-8601-no-colons>``.
        tier:
            Tier string embedded in the report (informational).
        auditor_model:
            Model identifier embedded in the report (informational).
        judge_model:
            Optional judge model identifier embedded in the report.
        cost_tracker:
            If provided, each fixture's token usage is added to it.  If not
            provided, an internal tracker (budget=$999) is used so costs are
            still computed but never abort the run.
        save_transcripts:
            If True (default), write per-fixture and aggregate outputs to disk.

    Returns:
        A populated CanaryReport.
    """
    # ── Defaults ──
    if fixtures_dir is None:
        fixtures_dir = Path(anneal.__file__).parent / "canary" / "fixtures"

    ran_at = datetime.now(tz=timezone.utc).isoformat()

    if log_dir is None:
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_dir = Path.cwd() / ".canary" / ts

    if save_transcripts:
        log_dir.mkdir(parents=True, exist_ok=True)

    # Internal cost tracker if caller didn't provide one (no budget enforcement)
    _internal_tracker = CostTracker(max_usd=999_999.0)
    _tracker = cost_tracker if cost_tracker is not None else _internal_tracker

    # ── Discover fixtures based on subset ──
    planted_descriptors: list[dict] = []
    perturb_descriptors: list[dict] = []
    clean_descriptors: list[dict] = []

    if subset in ("planted", "all"):
        planted_descriptors = _discover_planted(fixtures_dir)
    if subset in ("perturb", "all"):
        perturb_descriptors = _discover_perturbations(fixtures_dir)
    if subset in ("clean", "all"):
        clean_descriptors = _discover_clean(fixtures_dir)

    all_descriptors = planted_descriptors + perturb_descriptors + clean_descriptors

    # ── Run each fixture ──
    fixture_results: list[FixtureResult] = []

    # Use a dummy repo_root (the runner doesn't use the filesystem for repo ops)
    repo_root = Path.cwd()

    from anneal.cost import _PRICES_USD_PER_MILLION, _DEFAULT_PRICE  # noqa: PLC0415

    def _tokens_to_usd(tokens: int, model: str) -> float:
        price = _PRICES_USD_PER_MILLION.get(model, _DEFAULT_PRICE)
        return tokens * price / 1_000_000.0

    for desc in all_descriptors:
        fixture_name: str = desc["fixture_name"]
        category: CanaryCategory = desc["category"]
        diff: str = desc["diff"]
        expected_regex: str | None = desc["expected_regex"]

        # Run auditor — catch any exception so the suite continues
        error: str | None = None
        try:
            report = auditor.audit(diff, repo_root)
        except Exception:  # noqa: BLE001
            error = traceback.format_exc().strip()
            # Build a minimal stub AuditReport so FixtureResult is fully typed
            from anneal.audit.base import AuditReport as _AR  # noqa: PLC0415
            report = _AR(
                verdict="FAIL",
                findings=[],
                silent_drops=[],
                logic_disagreements=[],
                summary="",
                raw_markdown=f"[error: {error}]",
                tokens_used=0,
            )

        tokens_used = report.tokens_used
        cost_usd = _tokens_to_usd(tokens_used, auditor_model)

        # Record cost
        try:
            _tracker.add(tokens_used, auditor_model)
        except Exception:  # BudgetExceeded — canary should keep going (internal tracker has no limit)
            pass

        # Determine caught
        caught: bool
        matched: str | None
        if error:
            caught = False
            matched = None
        else:
            caught, matched = _check_caught(report, category, expected_regex)

        result = FixtureResult(
            fixture_name=fixture_name,
            category=category,
            caught=caught,
            matched_finding_summary=matched,
            expected_signature_regex=expected_regex,
            audit_report=report,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            error=error,
        )
        fixture_results.append(result)

        if save_transcripts:
            _save_fixture_outputs(log_dir, result)

    # ── Aggregate ──
    planted_results = [r for r in fixture_results if r.category == "planted_bug"]
    perturb_results = [r for r in fixture_results if r.category == "perturbation"]
    clean_results = [r for r in fixture_results if r.category == "clean_diff"]

    # planted_bugs sub-report
    p_total = len(planted_results)
    p_caught = sum(1 for r in planted_results if r.caught)
    p_rate = p_caught / p_total if p_total else 1.0
    planted_report: dict = {
        "total": p_total,
        "caught_round_1": p_caught,
        "rate": p_rate,
        "details": [
            {
                "fixture_name": r.fixture_name,
                "caught": r.caught,
                "matched_finding_summary": r.matched_finding_summary,
                "error": r.error,
            }
            for r in planted_results
        ],
    }

    # perturbations sub-report
    v_total = len(perturb_results)
    v_caught = sum(1 for r in perturb_results if r.caught)
    v_rate = v_caught / v_total if v_total else 1.0
    v_failed = [
        {
            "fixture_name": r.fixture_name,
            "matched_finding_summary": r.matched_finding_summary,
            "error": r.error,
        }
        for r in perturb_results
        if not r.caught
    ]
    perturb_report: dict = {
        "total": v_total,
        "caught": v_caught,
        "rate": v_rate,
        "failed": v_failed,
    }

    # clean_diffs sub-report
    c_total = len(clean_results)
    c_fp = sum(1 for r in clean_results if not r.caught)
    c_rate = 1.0 - (c_fp / c_total) if c_total else 1.0
    clean_report: dict = {
        "total": c_total,
        "false_positives": c_fp,
        "rate": c_rate,
    }

    # Overall pass
    planted_ok = (p_total == 0) or (p_rate >= _PLANTED_PASS_RATE)
    perturb_ok = (v_total == 0) or (v_rate >= _PERTURB_PASS_RATE)
    clean_ok = (c_total == 0) or (c_fp == 0)
    overall_pass = planted_ok and perturb_ok and clean_ok

    # Total cost
    total_cost = sum(r.cost_usd for r in fixture_results)

    # Models dict
    models: dict[str, str] = {"auditor": auditor_model}
    if judge_model:
        models["judge"] = judge_model

    report_obj = CanaryReport(
        ran_at=ran_at,
        tier=tier,
        models=models,
        planted_bugs=planted_report,
        perturbations=perturb_report,
        clean_diffs=clean_report,
        total_cost_usd=total_cost,
        overall_pass=overall_pass,
    )

    # Write aggregate report
    if save_transcripts:
        report_dict = dataclasses.asdict(report_obj)
        (log_dir / "canary_report.json").write_text(
            json.dumps(report_dict, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return report_obj
