"""SemgrepRunner: runs `semgrep scan` as a SAST pre-pass and returns SastFinding objects."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from anneal.sast.base import SastFinding, SastSeverity

logger = logging.getLogger(__name__)

# Env vars forwarded to the semgrep child process.  No API keys or secrets.
_SEMGREP_ENV_PASSTHROUGH = {"SYSTEMROOT", "PATH"}

# Semgrep exits 0 even when findings are present.
# Any non-zero exit code signals a tool-level failure (bad config, crash, etc.).
_SEMGREP_SUCCESS_EXIT_CODE = 0

# File extensions Semgrep can meaningfully analyse.
SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb"}

_SEVERITY_MAP: dict[str, SastSeverity] = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


def _map_severity(raw: str) -> SastSeverity:
    """Map a Semgrep severity string to an anneal severity level.

    Mapping:
        ERROR   → "high"
        WARNING → "medium"
        INFO    → "low"
        other   → "info"
    """
    return _SEVERITY_MAP.get(raw.upper(), "info")


def _build_child_env() -> dict[str, str]:
    """Return a stripped environment with only safe keys forwarded."""
    return {k: v for k, v in os.environ.items() if k in _SEMGREP_ENV_PASSTHROUGH}


class SemgrepRunner:
    """SAST runner that wraps `semgrep scan --json`.

    Complements :class:`~anneal.sast.ruff_runner.RuffRunner`: ruff is Python-only
    and fast; Semgrep covers Python, JS/TS, Go, Java, Ruby and applies deeper
    security/correctness rules via its bundled rule registry.

    Args:
        semgrep_path: Explicit path to the semgrep executable.  Defaults to
                      ``shutil.which("semgrep")``.  Pass an explicit path in tests
                      to avoid depending on the system PATH.
        config:       Semgrep config string passed via ``--config``.  Defaults to
                      ``"auto"`` (Semgrep's bundled registry for the detected languages).
    """

    #: File extensions this runner handles.  T2.6c can union this with RuffRunner's set.
    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(SUPPORTED_EXTENSIONS)

    def __init__(
        self,
        semgrep_path: str | None = None,
        config: str = "auto",
    ) -> None:
        self._semgrep_path: str | None = (
            semgrep_path if semgrep_path is not None else shutil.which("semgrep")
        )
        self._config = config

    # ------------------------------------------------------------------
    # SastRunner protocol
    # ------------------------------------------------------------------

    def run(self, worktree: Path, changed_files: list[str]) -> list[SastFinding]:
        """Run semgrep against the supported files in ``changed_files``.

        Files whose extension is not in :attr:`SUPPORTED_EXTENSIONS` are silently
        skipped before semgrep is invoked.  If semgrep is not installed a warning
        is logged and an empty list is returned without raising.

        Semgrep on Windows can be flaky (missing executable, malformed JSON output,
        or timeouts on first-run rule downloads).  All such conditions are caught
        and logged; the runner always returns a list (never raises).

        Args:
            worktree:      Absolute path to the git worktree root.
            changed_files: Relative file paths to analyse.

        Returns:
            List of :class:`~anneal.sast.base.SastFinding` objects.
        """
        if self._semgrep_path is None:
            logger.warning(
                "semgrep is not installed or not on PATH — skipping semgrep SAST pre-pass. "
                "Install semgrep (`pip install semgrep`) to enable this check."
            )
            return []

        supported_files = [
            f for f in changed_files if Path(f).suffix in self.SUPPORTED_EXTENSIONS
        ]
        if not supported_files:
            logger.debug("SemgrepRunner: no supported files in changed_files, skipping.")
            return []

        abs_files = [str(worktree / f) for f in supported_files]

        cmd = [
            self._semgrep_path,
            "scan",
            "--json",
            "--quiet",
            f"--config={self._config}",
            *abs_files,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=worktree,
                env=_build_child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,  # Semgrep is slower than ruff (rule download + analysis)
            )
        except subprocess.TimeoutExpired:
            logger.warning("SemgrepRunner: semgrep timed out after 120 s — returning no findings.")
            return []
        except FileNotFoundError:
            logger.warning(
                "SemgrepRunner: semgrep executable not found at %r — returning no findings.",
                self._semgrep_path,
            )
            return []

        # Semgrep exits 0 whether or not findings exist.  Non-zero = tool error.
        if result.returncode != _SEMGREP_SUCCESS_EXIT_CODE:
            logger.warning(
                "SemgrepRunner: semgrep exited with code %d (tool error). stderr: %s",
                result.returncode,
                result.stderr.decode("utf-8", errors="replace"),
            )
            return []

        return self._parse_output(result.stdout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_output(self, raw: bytes) -> list[SastFinding]:
        """Parse semgrep JSON output into :class:`SastFinding` objects.

        Semgrep's ``--json`` output schema (relevant fields)::

            {
              "results": [
                {
                  "check_id": "python.lang.security.audit.exec-detected",
                  "path": "src/foo.py",
                  "start": {"line": 42, "col": 1},
                  "extra": {
                    "severity": "ERROR",
                    "message": "Use of exec() detected"
                  }
                }
              ]
            }

        Args:
            raw: Raw bytes from semgrep's stdout.

        Returns:
            List of :class:`SastFinding`.  Empty on parse errors or empty output.
        """
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("SemgrepRunner: failed to parse semgrep JSON output: %s", exc)
            return []

        results = data.get("results")
        if not isinstance(results, list):
            logger.warning(
                "SemgrepRunner: unexpected JSON shape — 'results' key missing or not a list."
            )
            return []

        findings: list[SastFinding] = []
        for item in results:
            try:
                rule_id: str = item.get("check_id") or ""
                path: str = item.get("path") or ""
                start: dict = item.get("start") or {}
                line: int = int(start.get("line", 0))
                extra: dict = item.get("extra") or {}
                raw_severity: str = extra.get("severity") or ""
                message: str = extra.get("message") or ""

                findings.append(
                    SastFinding(
                        severity=_map_severity(raw_severity),
                        file=path,
                        line=line,
                        rule_id=rule_id,
                        message=message,
                        tool="semgrep",
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug(
                    "SemgrepRunner: skipping malformed semgrep finding %r: %s", item, exc
                )

        return findings
