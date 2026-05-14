"""CLI adversarial-mode smoke test with mocked LLMs.

Invokes main() programmatically with monkeypatched build_llm, verifies:
  - exit code matches expectation
  - manifest.json written to log_dir
  - no unhandled exceptions
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from anneal.llm.mock import DeterministicMockLLM


# ── Git fixture helper ─────────────────────────────────────────────────────────


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "--initial-branch=main"], repo)
    _git(["config", "user.email", "smoke@anneal"], repo)
    _git(["config", "user.name", "Anneal Smoke"], repo)
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "main.py"], repo)
    _git(["commit", "-m", "initial"], repo)
    return repo


# ── Smoke test ─────────────────────────────────────────────────────────────────


def test_adversarial_cli_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI adversarial mode ends cleanly with mocked LLMs; manifest.json is written."""
    import anneal.llm.factory as factory_mod

    repo = _make_repo(tmp_path)
    log_dir = tmp_path / "log"

    # Two empty Red rounds → converged (reason="clean")
    empty_red = json.dumps({"attacks": []})
    empty_blue = "```diff\n# rationale: nothing\n```\n"

    mock_responses = [
        empty_blue,   # Round 1 Blue
        empty_red,    # Round 1 Red
        empty_blue,   # Round 2 Blue
        empty_red,    # Round 2 Red
    ]
    shared_mock = DeterministicMockLLM(mock_responses)

    # Monkeypatch build_llm to return the same mock regardless of role
    monkeypatch.setattr(factory_mod, "build_llm", lambda provider, model, keys: shared_mock)

    # Monkeypatch sys.argv
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "anneal",
            "adversarial",
            "HEAD",
            "--repo", str(repo),
            "--base-ref", "HEAD",
            "--log-dir", str(log_dir),
            "--max-rounds", "5",
            "--until-clean", "2",
            "--max-cost-usd", "99.0",
            "--tier", "balanced",
        ],
    )

    from anneal.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main()

    # Converged → exit 0
    assert exc_info.value.code == 0

    # manifest.json must exist and contain a result
    manifest_path = log_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json must be written by the CLI"

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["mode"] == "adversarial"
    assert data["result"]["converged"] is True
    assert data["result"]["reason"] == "clean"
