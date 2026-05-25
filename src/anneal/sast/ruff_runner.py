"""RuffRunner: runs `ruff check` as a SAST pre-pass and returns SastFinding objects."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from anneal.sast.base import SastFinding, SastSeverity

logger = logging.getLogger(__name__)

# Env vars forwarded to the ruff child process.  No API keys or secrets.
_RUFF_ENV_PASSTHROUGH = {"SYSTEMROOT", "PATH"}

# Ruff exit codes:
#   0  — no findings
#   1  — findings were found (not a tool error)
#   2+ — tool error (bad config, crash, etc.)
_RUFF_FINDINGS_EXIT_CODE = 1
_RUFF_ERROR_EXIT_CODE_MIN = 2


def _map_severity(rule_id: str) -> SastSeverity:
    """Map a ruff rule ID prefix to an anneal severity level.

    Mapping:
        S*  (flake8-bandit / security)  → "high"
        E*, W* (pycodestyle errors/warns) → "medium"
        F*  (pyflakes: unused/undefined)  → "low"
        everything else                   → "info"
    """
    if not rule_id:
        return "info"
    prefix = rule_id[0].upper()
    if prefix == "S":
        return "high"
    if prefix in ("E", "W"):
        return "medium"
    if prefix == "F":
        return "low"
    return "info"


def _build_child_env() -> dict[str, str]:
    """Return a stripped environment with only safe keys forwarded."""
    return {k: v for k, v in os.environ.items() if k in _RUFF_ENV_PASSTHROUGH}


class RuffRunner:
    """SAST runner that wraps `ruff check --output-format=json`.

    Args:
        ruff_path: Explicit path to the ruff executable.  Defaults to
                   ``shutil.which("ruff")``.  Pass an explicit path in tests
                   to avoid depending on the system PATH.
    """

    def __init__(self, ruff_path: str | None = None) -> None:
        self._ruff_path: str | None = ruff_path if ruff_path is not None else shutil.which("ruff")

    # ------------------------------------------------------------------
    # SastRunner protocol
    # ------------------------------------------------------------------

    def run(self, worktree: Path, changed_files: list[str]) -> list[SastFinding]:
        """Run ruff against the Python files in ``changed_files``.

        Non-.py files are silently skipped before ruff is invoked.  If ruff is
        not installed (``shutil.which`` returned None and no explicit path was
        given) a warning is logged and an empty list is returned without raising.

        Args:
            worktree:      Absolute path to the git worktree root.
            changed_files: Relative file paths to analyse.

        Returns:
            List of :class:`~anneal.sast.base.SastFinding` objects.
        """
        if self._ruff_path is None:
            logger.warning(
                "ruff is not installed or not on PATH — skipping ruff SAST pre-pass. "
                "Install ruff (`pip install ruff`) to enable this check."
            )
            return []

        py_files = [f for f in changed_files if f.endswith(".py")]
        if not py_files:
            logger.debug("RuffRunner: no Python files in changed_files, skipping.")
            return []

        abs_py_files = [str(worktree / f) for f in py_files]

        cmd = [
            self._ruff_path,
            "check",
            "--output-format=json",
            "--no-cache",
            *abs_py_files,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=worktree,
                env=_build_child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            logger.warning("RuffRunner: ruff timed out after 30 s — returning no findings.")
            return []
        except FileNotFoundError:
            logger.warning(
                "RuffRunner: ruff executable not found at %r — returning no findings.",
                self._ruff_path,
            )
            return []

        # ruff exits 1 when it found issues; that is normal, not a tool failure.
        if result.returncode >= _RUFF_ERROR_EXIT_CODE_MIN:
            logger.warning(
                "RuffRunner: ruff exited with code %d (tool error). stderr: %s",
                result.returncode,
                result.stderr.decode("utf-8", errors="replace"),
            )
            return []

        return self._parse_output(result.stdout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_output(self, raw: bytes) -> list[SastFinding]:
        """Parse ruff JSON output into :class:`SastFinding` objects.

        Args:
            raw: Raw bytes from ruff's stdout.

        Returns:
            List of :class:`SastFinding`.  Empty on parse errors or empty output.
        """
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("RuffRunner: failed to parse ruff JSON output: %s", exc)
            return []

        findings: list[SastFinding] = []
        for item in data:
            try:
                rule_id: str = item.get("code") or ""
                message: str = item.get("message") or ""
                filename: str = item.get("filename") or ""
                location: dict = item.get("location") or {}
                line: int = int(location.get("row", 0))
                findings.append(
                    SastFinding(
                        severity=_map_severity(rule_id),
                        file=filename,
                        line=line,
                        rule_id=rule_id,
                        message=message,
                        tool="ruff",
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("RuffRunner: skipping malformed ruff finding %r: %s", item, exc)

        return findings
