"""Fixer router: dispatches to a specialized Fixer based on a Finding's content.

Usage::

    from anneal.fix.router import route_fixer
    fixer = route_fixer(finding, default=my_llm_fixer)

The router is USABLE but NOT wired as the loop's default — ``DefaultFixer``
remains the loop's default fixer to preserve existing behavior.

Specialized fixers are instantiated fresh on each call so they always receive
the correct LLM instance (no stale-None cache).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anneal.fix.base import Fixer
    from anneal.audit.base import Finding

# Keyword sets — matched case-insensitively against Finding.summary
_SECURITY_KEYWORDS = re.compile(
    r"\b(security|vulnerabilit(?:y|ies)|injection|xss|csrf|auth(?:entication|orization)?|"
    r"sql\s+injection|command\s+injection|path\s+traversal|insecure|privilege|exploit)\b",
    re.IGNORECASE,
)
_TEST_KEYWORDS = re.compile(
    r"\b(test|coverage|untested|missing\s+test|no\s+test|lacking\s+test|test\s+gap)\b",
    re.IGNORECASE,
)
_REFACTOR_KEYWORDS = re.compile(
    r"\b(refactor|duplication|duplicate|code\s+smell|naming|readabilit(?:y|ies)|"
    r"complexity|maintainabilit(?:y|ies)|dead\s+code|unused)\b",
    re.IGNORECASE,
)

def route_fixer(finding: "Finding", default: "Fixer | None" = None) -> "Fixer":
    """Return the most appropriate Fixer for the given Finding.

    Dispatch priority (first match wins):

    1. Security keywords in ``finding.summary`` → :class:`SecurityFixer`
    2. Test/coverage keywords → :class:`TestFixer`
    3. Refactor/style keywords → :class:`RefactorFixer`
    4. Fallback → *default* if provided, else :class:`DefaultFixer`

    A fresh fixer instance is created on every call so specialized fixers
    always receive the correct LLM (no stale-None module-level cache).
    The router is called per-finding; cost is dominated by LLM calls, not
    object construction.

    .. note::
        The loop does not yet call ``route_fixer`` per-finding; that is a
        future enhancement.  This function is exposed so callers can invoke
        it directly or integrate it into custom loop variants.

    Args:
        finding: A single :class:`~anneal.audit.base.Finding` from an audit report.
        default: Optional pre-constructed fixer to use as the fallback instead of
            a bare :class:`DefaultFixer`.

    Returns:
        The selected :class:`~anneal.fix.base.Fixer` instance.

    Example::

        fixer = route_fixer(finding)
        # or, with a pre-configured default:
        fixer = route_fixer(finding, default=my_llm_fixer)
    """
    from anneal.fix.default_fixer import DefaultFixer
    from anneal.fix.security_fixer import SecurityFixer
    from anneal.fix.test_fixer import TestFixer
    from anneal.fix.refactor_fixer import RefactorFixer

    text = finding.summary

    if _SECURITY_KEYWORDS.search(text):
        return SecurityFixer(None)

    if _TEST_KEYWORDS.search(text):
        return TestFixer(None)

    if _REFACTOR_KEYWORDS.search(text):
        return RefactorFixer(None)

    if default is not None:
        return default

    return DefaultFixer(None)
