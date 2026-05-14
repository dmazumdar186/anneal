"""Judge agent: verifies non-executable Red findings, defaults to invalid if unsure.

Strict bias: no incentive to side with Red.  Uncertain == functionally invalid.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from anneal.adversarial.base import Attack, JudgeOutput, JudgeVerdict
from anneal.llm.base import LLM

_log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPTS_DIR / "judge.md"

_VALID_VERDICTS: frozenset[str] = frozenset(("valid", "invalid", "uncertain"))


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class Judge:
    """LLM judge for non-executable Red findings.

    Strict: defaults to ``invalid`` if the response is unparseable or the
    verdict is ``uncertain``.  The calling loop treats ``uncertain`` as
    functionally invalid — anneal will not land uncertain attacks.

    Args:
        llm: Any object satisfying the LLM Protocol. Typically a cheap model
            (Gemini Flash) — the Judge role is yes/no, not generative.
        prompt_path: Path to the system prompt markdown. Defaults to the bundled
            adversarial/prompts/judge.md.
    """

    def __init__(self, llm: LLM, prompt_path: Path | None = None) -> None:
        self._llm = llm
        self._prompt = _load_prompt(prompt_path or _DEFAULT_PROMPT_PATH)

    def judge(
        self,
        attack: Attack,
        diff: str,
        repo_root: Path,  # noqa: ARG002  # reserved for future file-read enrichment
    ) -> JudgeOutput:
        """Decide whether Red's finding-shaped attack is factually correct.

        Args:
            attack: An Attack with ``kind="finding"``.
            diff: Current diff context shown to the Judge.
            repo_root: Worktree path. Reserved for future enrichment; Judge only
                sees the diff in this implementation.

        Returns:
            JudgeOutput with verdict in {``"valid"``, ``"invalid"``, ``"uncertain"``}
            and a rationale quoting evidence from the diff.

        Raises:
            ValueError: If ``attack.kind != "finding"``. Tests are verified by
                execution, not by the Judge.
        """
        if attack.kind != "finding":
            raise ValueError(
                f"Judge.judge() only handles kind='finding', got kind='{attack.kind}'. "
                "Test attacks are verified by running them, not by the Judge."
            )

        user_msg = (
            "## Red's Attack\n\n"
            f"- kind: {attack.kind}\n"
            f"- target_files: {', '.join(attack.target_files)}\n"
            f"- severity: {attack.severity}\n"
            f"- claim: {attack.claim}\n"
            f"- evidence: {attack.evidence}\n"
            f"- expected: {attack.expected}\n"
            f"- actual: {attack.actual}\n"
            f"- rationale: {attack.rationale}\n\n"
            "## Current Diff\n\n"
            "```diff\n"
            f"{diff}\n"
            "```\n\n"
            'Return JSON only: {"verdict": "valid|invalid|uncertain", "rationale": "..."}'
        )

        response_text, tokens_used = self._llm.complete(
            system=self._prompt,
            user=user_msg,
            response_format="json",
        )

        verdict: JudgeVerdict
        rationale: str

        try:
            data = json.loads(response_text)
            raw_verdict = str(data.get("verdict", "")).lower().strip()
            rationale = str(data.get("rationale", ""))
            if raw_verdict not in _VALID_VERDICTS:
                _log.warning(
                    "Judge returned unrecognised verdict %r — defaulting to invalid",
                    raw_verdict,
                )
                verdict = "invalid"
                rationale = rationale or "judge_verdict_unrecognised"
            else:
                verdict = raw_verdict  # type: ignore[assignment]
        except (json.JSONDecodeError, AttributeError) as exc:
            _log.warning("Judge response unparseable (%s) — defaulting to invalid", exc)
            verdict = "invalid"
            rationale = "judge_response_unparseable"

        return JudgeOutput(verdict=verdict, rationale=rationale, tokens_used=tokens_used)
