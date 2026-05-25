"""Unit tests for specialized fixers and the fixer router."""

from __future__ import annotations

from anneal.audit.base import Finding
from anneal.fix.security_fixer import SecurityFixer
from anneal.fix.test_fixer import TestFixer
from anneal.fix.router import route_fixer


def _make_finding(summary: str, severity: str = "MEDIUM") -> Finding:
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        summary=summary,
        file="src/foo.py",
        impact="",
        recommended_fix="",
    )


def test_test_fixer_loads_test_prompt() -> None:
    """TestFixer.prompt_path ends in test_fixer.md and the prompt text contains the role string."""
    fixer = TestFixer(llm=None)
    assert fixer.prompt_path.name == "test_fixer.md"
    assert "test-gap fixer" in fixer._prompt.lower()


def test_security_fixer_loads_security_prompt() -> None:
    """SecurityFixer.prompt_path ends in security_fixer.md and the prompt text contains the role string."""
    fixer = SecurityFixer(llm=None)
    assert fixer.prompt_path.name == "security_fixer.md"
    assert "security-specialist fixer" in fixer._prompt.lower()


def test_router_picks_security_fixer_for_security_finding() -> None:
    """router returns SecurityFixer for a finding whose summary mentions SQL injection."""
    finding = _make_finding("SQL injection in user_query()", severity="CRITICAL")
    fixer = route_fixer(finding)
    assert isinstance(fixer, SecurityFixer)


def test_router_picks_test_fixer_for_missing_test() -> None:
    """router returns TestFixer for a finding whose summary mentions missing test coverage."""
    finding = _make_finding("Missing test coverage for edge case", severity="LOW")
    fixer = route_fixer(finding)
    assert isinstance(fixer, TestFixer)
