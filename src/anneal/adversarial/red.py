"""Red agent: generates hybrid (test|finding) attacks against the current diff.

parse_red_response is exposed as a standalone function for unit tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from anneal.adversarial.base import (
    Attack,
    RedTurnOutput,
    attack_fingerprint,
)
from anneal.llm.base import LLM

_log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPTS_DIR / "red.md"

_MAX_ATTACKS_PER_ROUND = 5


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _finding_identifier(severity: str | None, claim: str | None) -> str:
    """Stable identifier for kind='finding' attacks used in fingerprinting."""
    key = f"{severity or ''}|{claim or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _parse_single_attack(raw: dict, idx: int) -> Attack | None:
    """Parse one attack dict from Red's JSON response.

    Returns None if the attack is malformed or missing required fields.
    Logs a warning for each skipped attack.

    Args:
        raw: Dict parsed from JSON.
        idx: 0-based index within the attacks array (used for default test_path).

    Returns:
        Attack dataclass or None if invalid.
    """
    kind = raw.get("kind")
    if kind not in ("test", "finding"):
        _log.warning("Red attack #%d has invalid kind=%r — skipping", idx, kind)
        return None

    target_files_raw = raw.get("target_files", [])
    if not isinstance(target_files_raw, list):
        target_files_raw = [str(target_files_raw)]
    target_files: tuple[str, ...] = tuple(str(f) for f in target_files_raw)

    rationale = str(raw.get("rationale", ""))

    if kind == "test":
        test_body = raw.get("test_body")
        if not test_body:
            _log.warning(
                "Red attack #%d (kind=test) missing test_body — skipping", idx
            )
            return None
        # Default test_path if Red omitted it
        test_path = raw.get("test_path") or f"tests/red/test_attack_{idx + 1:03d}.py"
        fp = attack_fingerprint("test", target_files, test_path)
        return Attack(
            kind="test",
            fingerprint=fp,
            target_files=target_files,
            rationale=rationale,
            test_path=test_path,
            test_body=str(test_body),
        )

    # kind == "finding"
    severity = raw.get("severity", "MEDIUM")
    claim = raw.get("claim")
    if not claim:
        _log.warning(
            "Red attack #%d (kind=finding) missing claim — skipping", idx
        )
        return None
    evidence = raw.get("evidence", "")
    expected = raw.get("expected")
    actual = raw.get("actual")
    identifier = _finding_identifier(severity, claim)
    fp = attack_fingerprint("finding", target_files, identifier)
    return Attack(
        kind="finding",
        fingerprint=fp,
        target_files=target_files,
        rationale=rationale,
        severity=severity,  # type: ignore[arg-type]
        claim=str(claim),
        evidence=str(evidence),
        expected=str(expected) if expected is not None else None,
        actual=str(actual) if actual is not None else None,
    )


def parse_red_response(text: str, tokens_used: int) -> RedTurnOutput:
    """Parse Red's JSON response into a RedTurnOutput.

    Handles malformed JSON gracefully — returns an empty attack list rather
    than crashing.  Caps at _MAX_ATTACKS_PER_ROUND (5) and skips any attack
    with missing required fields.

    Args:
        text: Raw LLM response text (must be a JSON object with "attacks" key).
        tokens_used: Token count to embed in the returned RedTurnOutput.

    Returns:
        RedTurnOutput with parsed attacks (possibly empty) and tokens_used.

    Example::

        output = parse_red_response('{"attacks": []}', tokens_used=500)
        assert output.attacks == []
        assert output.tokens_used == 500
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        _log.warning("Red returned malformed JSON (%s) — treating as empty round", exc)
        return RedTurnOutput(attacks=[], tokens_used=tokens_used)

    if not isinstance(data, dict):
        _log.warning("Red JSON root is not a dict (got %s) — treating as empty", type(data).__name__)
        return RedTurnOutput(attacks=[], tokens_used=tokens_used)

    raw_attacks = data.get("attacks", [])
    if not isinstance(raw_attacks, list):
        _log.warning("Red 'attacks' is not a list — treating as empty")
        return RedTurnOutput(attacks=[], tokens_used=tokens_used)

    if len(raw_attacks) > _MAX_ATTACKS_PER_ROUND:
        _log.warning(
            "Red returned %d attacks (max %d) — keeping first %d",
            len(raw_attacks),
            _MAX_ATTACKS_PER_ROUND,
            _MAX_ATTACKS_PER_ROUND,
        )
        raw_attacks = raw_attacks[:_MAX_ATTACKS_PER_ROUND]

    attacks: list[Attack] = []
    for idx, raw in enumerate(raw_attacks):
        if not isinstance(raw, dict):
            _log.warning("Red attack #%d is not a dict — skipping", idx)
            continue
        attack = _parse_single_attack(raw, idx)
        if attack is not None:
            attacks.append(attack)

    return RedTurnOutput(attacks=attacks, tokens_used=tokens_used)


class Red:
    """Red attacker. Produces hybrid (test|finding) attacks each round.

    Args:
        llm: Any object satisfying the LLM Protocol.
        prompt_path: Path to the system prompt markdown. Defaults to the bundled
            adversarial/prompts/red.md.
    """

    def __init__(self, llm: LLM, prompt_path: Path | None = None) -> None:
        self._llm = llm
        self._prompt = _load_prompt(prompt_path or _DEFAULT_PROMPT_PATH)

    def attack(
        self,
        diff: str,
        repo_root: Path,  # noqa: ARG002  # reserved for future file-inspection
        history: list[Attack] | list[dict],
    ) -> RedTurnOutput:
        """Run Red against the current diff.

        Args:
            diff: Current state of the diff under attack.
            repo_root: Worktree path. Red only sees the diff in the user message;
                this parameter is reserved for future file-inspection features.
            history: Previous attack records. Accepts either Attack dataclass objects
                or the dict shape returned by TranscriptWriter.red_history()
                (keys: fingerprint, kind, landed, round).

        Returns:
            RedTurnOutput with parsed Attack list and tokens_used.
        """
        history_lines: list[str] = []
        # Group by fingerprint to detect repeated attacks.
        # Each entry is either an Attack dataclass or a dict from red_history().
        seen: dict[str, list] = {}
        for atk in history:
            fp = atk.fingerprint if hasattr(atk, "fingerprint") else atk["fingerprint"]
            seen.setdefault(fp, []).append(atk)

        for fp, attacks in seen.items():
            last = attacks[-1]
            kind = last.kind if hasattr(last, "kind") else last["kind"]
            note = "  [REPEATED — try different angle]" if len(attacks) >= 2 else ""
            history_lines.append(
                f"- fingerprint={fp}  kind={kind}  round={len(attacks)}{note}"
            )

        history_block = (
            "## Previous Attack History\n\n" + "\n".join(history_lines)
            if history_lines
            else "## Previous Attack History\n\n(none — this is round 1)"
        )

        user_msg = (
            f"{history_block}\n\n"
            "## Current Diff Under Attack\n\n"
            "```diff\n"
            f"{diff}\n"
            "```\n\n"
            "Now produce your attacks. Return ONLY the JSON object with key \"attacks\"."
        )

        response_text, tokens_used = self._llm.complete(
            system=self._prompt,
            user=user_msg,
            response_format="json",
        )
        return parse_red_response(response_text, tokens_used)
