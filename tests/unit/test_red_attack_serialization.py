"""Unit tests for Red attack JSON round-trip serialization (both kind=test and kind=finding).

Phase 3b1 — adversarial attack parsing and serialization.
"""

from __future__ import annotations

import json

from anneal.adversarial.base import attack_fingerprint
from anneal.adversarial.red import parse_red_response


# ---------------------------------------------------------------------------
# 1. kind=test attack parses correctly
# ---------------------------------------------------------------------------

def test_parse_red_response_test_attack() -> None:
    payload = {
        "attacks": [
            {
                "kind": "test",
                "target_files": ["src/foo.py"],
                "test_path": "tests/red/test_attack_001.py",
                "rationale": "Off-by-one in pagination.",
                "test_body": "def test_off_by_one():\n    assert False\n",
            }
        ]
    }
    output = parse_red_response(json.dumps(payload), tokens_used=400)

    assert len(output.attacks) == 1
    atk = output.attacks[0]
    assert atk.kind == "test"
    assert atk.test_path == "tests/red/test_attack_001.py"
    assert atk.test_body == "def test_off_by_one():\n    assert False\n"
    assert atk.target_files == ("src/foo.py",)
    assert atk.rationale == "Off-by-one in pagination."
    assert len(atk.fingerprint) == 16
    assert output.tokens_used == 400
    # finding fields must be None
    assert atk.severity is None
    assert atk.claim is None


# ---------------------------------------------------------------------------
# 2. kind=finding attack parses correctly
# ---------------------------------------------------------------------------

def test_parse_red_response_finding_attack() -> None:
    payload = {
        "attacks": [
            {
                "kind": "finding",
                "target_files": ["docs/PRD.md"],
                "severity": "HIGH",
                "claim": "Goal #2 has no success metric.",
                "evidence": "PRD §3.2 lists Goal #2 with no measurable outcome.",
                "rationale": "Without a metric this goal is unfalsifiable.",
                "expected": "A quantitative target.",
                "actual": "Aspirational language, no numbers.",
            }
        ]
    }
    output = parse_red_response(json.dumps(payload), tokens_used=300)

    assert len(output.attacks) == 1
    atk = output.attacks[0]
    assert atk.kind == "finding"
    assert atk.severity == "HIGH"
    assert atk.claim == "Goal #2 has no success metric."
    assert atk.evidence == "PRD §3.2 lists Goal #2 with no measurable outcome."
    assert atk.expected == "A quantitative target."
    assert atk.actual == "Aspirational language, no numbers."
    assert len(atk.fingerprint) == 16
    # test fields must be None
    assert atk.test_path is None
    assert atk.test_body is None


# ---------------------------------------------------------------------------
# 3. Malformed JSON returns empty list without crashing
# ---------------------------------------------------------------------------

def test_parse_red_response_malformed_json_returns_empty() -> None:
    output = parse_red_response("this is not json {{{{", tokens_used=100)

    assert output.attacks == []
    assert output.tokens_used == 100


# ---------------------------------------------------------------------------
# 4. More than 5 attacks → only first 5 returned
# ---------------------------------------------------------------------------

def test_parse_red_response_caps_at_five() -> None:
    attacks = [
        {
            "kind": "test",
            "target_files": [f"src/file_{i}.py"],
            "test_path": f"tests/red/test_attack_{i:03d}.py",
            "rationale": f"Attack {i}",
            "test_body": f"def test_{i}():\n    assert False\n",
        }
        for i in range(1, 8)  # 7 attacks
    ]
    payload = {"attacks": attacks}
    output = parse_red_response(json.dumps(payload), tokens_used=700)

    assert len(output.attacks) == 5


# ---------------------------------------------------------------------------
# 5. Attack missing required field is skipped; others kept
# ---------------------------------------------------------------------------

def test_parse_red_response_skips_missing_fields() -> None:
    payload = {
        "attacks": [
            {
                # Missing test_body — should be skipped
                "kind": "test",
                "target_files": ["src/bad.py"],
                "test_path": "tests/red/test_attack_001.py",
                "rationale": "No body.",
            },
            {
                # Valid attack — should be kept
                "kind": "test",
                "target_files": ["src/good.py"],
                "test_path": "tests/red/test_attack_002.py",
                "rationale": "Has body.",
                "test_body": "def test_ok():\n    assert False\n",
            },
        ]
    }
    output = parse_red_response(json.dumps(payload), tokens_used=200)

    assert len(output.attacks) == 1
    assert output.attacks[0].test_path == "tests/red/test_attack_002.py"


# ---------------------------------------------------------------------------
# 6. attack_fingerprint is stable across calls
# ---------------------------------------------------------------------------

def test_attack_fingerprint_stable() -> None:
    fp1 = attack_fingerprint("test", ("src/foo.py",), "tests/red/test_attack_001.py")
    fp2 = attack_fingerprint("test", ("src/foo.py",), "tests/red/test_attack_001.py")

    assert fp1 == fp2
    assert len(fp1) == 16

    # Different inputs → different fingerprint
    fp3 = attack_fingerprint("test", ("src/bar.py",), "tests/red/test_attack_001.py")
    assert fp3 != fp1
