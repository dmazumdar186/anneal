"""diff_extractor: extract changed symbols from a unified diff and build caller context."""

from __future__ import annotations

import re
from pathlib import Path

from anneal.repograph.base import RepoGraph, Symbol, format_context_as_markdown

# Matches lines like "+++ b/src/foo.py" or "+++ src/foo.py" in unified diffs.
_DIFF_FILE_RE = re.compile(r"^\+\+\+ (?:b/)?(.+\.py)$", re.MULTILINE)


def extract_changed_symbols(diff: str, worktree: Path, graph: RepoGraph) -> list[Symbol]:
    """Return all symbols defined in Python files mentioned in *diff*.

    Parses the unified diff to find changed ``.py`` files, then uses *graph*
    to extract every symbol defined in those files (as they exist on disk at
    *worktree*).

    Args:
        diff:     Unified diff string (e.g. from ``git diff``).
        worktree: Absolute path to the worktree root.
        graph:    A :class:`~anneal.repograph.base.RepoGraph` implementation.

    Returns:
        Deduplicated list of :class:`~anneal.repograph.base.Symbol` objects.
        Empty list when the diff contains no Python files.
    """
    changed_py_files: list[str] = _DIFF_FILE_RE.findall(diff)
    if not changed_py_files:
        return []

    symbols: list[Symbol] = []
    seen_qualified: set[str] = set()

    for rel_path in changed_py_files:
        abs_path = worktree / rel_path
        if not abs_path.exists():
            continue
        for sym in graph.extract_symbols(str(abs_path)):
            if sym.qualified_name not in seen_qualified:
                seen_qualified.add(sym.qualified_name)
                symbols.append(sym)

    return symbols


def build_context_for_diff(diff: str, worktree: Path, graph: RepoGraph) -> str:
    """Build a markdown caller-context block for all changed symbols in *diff*.

    1. Extracts changed symbols via :func:`extract_changed_symbols`.
    2. For each symbol, locates callers across the worktree.
    3. Renders the result with :func:`~anneal.repograph.base.format_context_as_markdown`.

    Args:
        diff:     Unified diff string.
        worktree: Absolute path to the worktree root.
        graph:    A :class:`~anneal.repograph.base.RepoGraph` implementation.

    Returns:
        Markdown string.  Empty string when there are no changed Python symbols
        or when no callers are found anywhere.
    """
    symbols = extract_changed_symbols(diff, worktree, graph)
    if not symbols:
        return ""

    callers_by_symbol: dict[str, list] = {}
    any_callers = False

    for sym in symbols:
        callers = graph.find_callers(sym.name, worktree)
        callers_by_symbol[sym.name] = callers
        if callers:
            any_callers = True

    if not any_callers:
        return ""

    return format_context_as_markdown(symbols, callers_by_symbol)
