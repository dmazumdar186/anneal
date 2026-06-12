"""batch.py — fan-out anneal across multiple repos/PRs in parallel.

Reads a refs-file (JSON array or newline-delimited repo:ref pairs) and runs
classic or adversarial mode on each entry via ThreadPoolExecutor.

Per-row failure isolation: one row raising does not halt the batch.
Results are aggregated into a single JSON summary written alongside the
refs-file as <refs-file>.batch_results.json.

Refs-file formats
-----------------
JSON array (preferred for --diff-file support)::

    [
      {"repo": "C:\\dev\\foo", "ref": "HEAD~1"},
      {"repo": "C:\\dev\\bar", "ref": "HEAD~1", "diff_file": "patch.diff"}
    ]

Plain text (one entry per line, repo_path:ref)::

    C:\\dev\\foo:HEAD~1
    C:\\dev\\bar:HEAD~1

Required keys per JSON entry:
  repo    — absolute path to the git repository
  ref     — base git ref (e.g. HEAD~1, a SHA)

Optional keys per JSON entry:
  diff_file — path to a .diff file applied before the audit loop starts
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Entry / result types ───────────────────────────────────────────────────────


@dataclass
class BatchEntry:
    """One row from the refs-file."""

    repo: str
    ref: str
    diff_file: str | None = None

    def label(self) -> str:
        """Short label for logging."""
        return f"{Path(self.repo).name}@{self.ref}"


@dataclass
class BatchRowResult:
    """Outcome for a single refs-file row."""

    label: str
    repo: str
    ref: str
    diff_file: str | None
    status: str          # "ok" | "failed" | "skipped"
    converged: bool | None
    rounds: int | None
    reason: str | None
    cost_usd: float | None
    log_dir: str | None
    error: str | None
    wall_seconds: float


@dataclass
class BatchSummary:
    """Aggregate result written to <refs-file>.batch_results.json."""

    total: int
    ok: int
    failed: int
    skipped: int
    converged: int
    total_cost_usd: float
    wall_seconds: float
    rows: list[BatchRowResult]


# ── Refs-file parser ───────────────────────────────────────────────────────────


def _parse_refs_file(path: Path) -> list[BatchEntry]:
    """Parse a refs-file into a list of BatchEntry objects.

    Supports JSON array format and plain text ``repo:ref`` format.

    Args:
        path: Path to the refs-file.

    Returns:
        List of BatchEntry instances.

    Raises:
        ValueError: If the file is malformed or empty.
        FileNotFoundError: If the file does not exist.
    """
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"refs-file is empty: {path}")

    # Try JSON first
    if text.startswith("["):
        try:
            raw: list[dict[str, Any]] = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"refs-file is invalid JSON: {exc}") from exc
        entries: list[BatchEntry] = []
        for i, item in enumerate(raw):
            if "repo" not in item:
                raise ValueError(f"refs-file row {i}: missing required key 'repo'")
            if "ref" not in item:
                raise ValueError(f"refs-file row {i}: missing required key 'ref'")
            entries.append(
                BatchEntry(
                    repo=item["repo"],
                    ref=item["ref"],
                    diff_file=item.get("diff_file"),
                )
            )
        return entries

    # Plain text: one "repo_path:ref" per line
    entries = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Split on the LAST colon so Windows absolute paths (C:\...) are safe
        # when the ref doesn't contain colons (git refs never do).
        # However, "C:\foo:HEAD~1" has two colons — split on the rightmost one.
        sep_idx = line.rfind(":")
        if sep_idx == -1:
            raise ValueError(
                f"refs-file line {lineno}: expected 'repo_path:ref', got {line!r}"
            )
        repo = line[:sep_idx]
        ref = line[sep_idx + 1:]
        if not repo or not ref:
            raise ValueError(
                f"refs-file line {lineno}: repo or ref is empty in {line!r}"
            )
        entries.append(BatchEntry(repo=repo, ref=ref))

    if not entries:
        raise ValueError(f"refs-file contains no valid entries: {path}")
    return entries


# ── Per-row worker ─────────────────────────────────────────────────────────────


def _run_one(
    entry: BatchEntry,
    mode: str,
    tier: str,
    api_keys: dict[str, str],
    extra_kwargs: dict[str, Any],
) -> BatchRowResult:
    """Run anneal (classic or adversarial) on a single BatchEntry.

    Args:
        entry:        The BatchEntry describing the repo/ref/diff_file.
        mode:         "classic" or "adversarial".
        tier:         Tier string passed to resolve_tier().
        api_keys:     Merged env dict with API credentials.
        extra_kwargs: Additional AnnealConfig fields (max_rounds, max_cost_usd, etc.).

    Returns:
        A BatchRowResult summarising the outcome.
    """
    label = entry.label()
    t0 = time.monotonic()

    try:
        from anneal.config import AnnealConfig, resolve_tier
        from anneal.audit.pipeline_auditor import PipelineAuditor
        from anneal.fix.default_fixer import DefaultFixer
        from anneal.llm.factory import build_llm

        tier_map = resolve_tier(tier)

        auditor_llm = build_llm(
            tier_map["auditor"]["provider"],
            tier_map["auditor"]["model"],
            api_keys,
        )
        fixer_llm = build_llm(
            tier_map["fixer"]["provider"],
            tier_map["fixer"]["model"],
            api_keys,
        )
        auditor = PipelineAuditor(auditor_llm)
        fixer = DefaultFixer(fixer_llm)

        repo = Path(entry.repo)
        diff_path = Path(entry.diff_file) if entry.diff_file else None

        cfg = AnnealConfig(
            repo=repo,
            base_ref=entry.ref,
            auditor=auditor,
            fixer=fixer,
            diff_path=diff_path,
            model=tier_map["auditor"]["model"],
            auditor_model=tier_map["auditor"]["model"],
            fixer_model=tier_map["fixer"]["model"],
            **extra_kwargs,
        )

        if mode == "classic":
            from anneal.loop_classic import anneal_classic
            result = anneal_classic(cfg)
        else:
            from anneal.loop_adversarial import anneal_adversarial
            from anneal.adversarial.red import Red
            from anneal.adversarial.blue import Blue
            from anneal.adversarial.judge import Judge

            red_llm = build_llm(
                tier_map["red"]["provider"],
                tier_map["red"]["model"],
                api_keys,
            )
            blue_llm = build_llm(
                tier_map["blue"]["provider"],
                tier_map["blue"]["model"],
                api_keys,
            )
            judge_llm = build_llm(
                tier_map["judge"]["provider"],
                tier_map["judge"]["model"],
                api_keys,
            )
            cfg_adv = AnnealConfig(
                repo=repo,
                base_ref=entry.ref,
                red=Red(red_llm),
                blue=Blue(blue_llm),
                judge=Judge(judge_llm),
                diff_path=diff_path,
                model=tier_map["red"]["model"],
                red_model=tier_map["red"]["model"],
                blue_model=tier_map["blue"]["model"],
                judge_model=tier_map["judge"]["model"],
                **extra_kwargs,
            )
            result = anneal_adversarial(cfg_adv)

        wall = time.monotonic() - t0
        logger.info(
            "batch row %s — %s rounds=%d cost=$%.4f",
            label,
            "CONVERGED" if result.converged else "DID NOT CONVERGE",
            result.rounds,
            result.total_cost_usd,
        )
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
            log_dir=str(result.log_dir) if result.log_dir else None,
            error=None,
            wall_seconds=round(wall, 2),
        )

    except Exception as exc:  # noqa: BLE001 — per-row isolation: log + continue
        wall = time.monotonic() - t0
        logger.error("batch row %s — FAILED: %s", label, exc, exc_info=True)
        return BatchRowResult(
            label=label,
            repo=entry.repo,
            ref=entry.ref,
            diff_file=entry.diff_file,
            status="failed",
            converged=None,
            rounds=None,
            reason=None,
            cost_usd=None,
            log_dir=None,
            error=str(exc),
            wall_seconds=round(wall, 2),
        )


# ── Public batch runner ────────────────────────────────────────────────────────


def run_batch(
    refs_file: Path,
    *,
    mode: str = "classic",
    max_workers: int = 4,
    tier: str = "balanced",
    api_keys: dict[str, str],
    extra_kwargs: dict[str, Any] | None = None,
) -> BatchSummary:
    """Fan out anneal across all entries in refs_file in parallel.

    Args:
        refs_file:    Path to the refs-file (JSON or plain text).
        mode:         "classic" or "adversarial".
        max_workers:  Max concurrent ThreadPoolExecutor workers (default 4).
        tier:         Tier string (cheap / balanced / premium / ultra).
        api_keys:     Dict of API credentials (merged shell env + .env file).
        extra_kwargs: Extra AnnealConfig fields forwarded to each worker.

    Returns:
        A BatchSummary with per-row results and aggregate stats.

    Side-effect:
        Writes <refs_file>.batch_results.json next to the refs-file.
    """
    extra_kwargs = extra_kwargs or {}
    entries = _parse_refs_file(refs_file)
    n = len(entries)
    logger.info("anneal batch: %d entries, mode=%s, max_workers=%d", n, mode, max_workers)

    row_results: list[BatchRowResult | None] = [None] * n
    _results_lock = threading.Lock()

    t0 = time.monotonic()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(_run_one, entry, mode, tier, api_keys, extra_kwargs): i
            for i, entry in enumerate(entries)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001 — safety net; _run_one should not raise
                entry = entries[idx]
                logger.error(
                    "batch worker for %s raised unexpectedly: %s", entry.label(), exc, exc_info=True
                )
                row = BatchRowResult(
                    label=entry.label(),
                    repo=entry.repo,
                    ref=entry.ref,
                    diff_file=entry.diff_file,
                    status="failed",
                    converged=None,
                    rounds=None,
                    reason=None,
                    cost_usd=None,
                    log_dir=None,
                    error=f"unexpected worker error: {exc}",
                    wall_seconds=0.0,
                )
            with _results_lock:
                row_results[idx] = row

    wall_total = time.monotonic() - t0

    # All slots must be filled at this point; cast away None for type checker
    rows: list[BatchRowResult] = row_results  # type: ignore[assignment]

    ok = sum(1 for r in rows if r.status == "ok")
    failed = sum(1 for r in rows if r.status == "failed")
    skipped = sum(1 for r in rows if r.status == "skipped")
    converged = sum(1 for r in rows if r.converged)
    total_cost = sum(r.cost_usd or 0.0 for r in rows)

    summary = BatchSummary(
        total=n,
        ok=ok,
        failed=failed,
        skipped=skipped,
        converged=converged,
        total_cost_usd=round(total_cost, 6),
        wall_seconds=round(wall_total, 2),
        rows=rows,
    )

    # Write aggregate results file — lock is not needed here (single writer post-pool)
    out_path = refs_file.with_suffix(refs_file.suffix + ".batch_results.json")
    _write_batch_results(out_path, summary)
    logger.info("anneal batch: results written to %s", out_path)

    return summary


def _write_batch_results(path: Path, summary: BatchSummary) -> None:
    """Serialize BatchSummary to JSON and write atomically.

    Args:
        path:    Destination path for the JSON file.
        summary: The BatchSummary to serialize.
    """
    data = asdict(summary)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
