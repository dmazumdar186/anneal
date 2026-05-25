"""repograph base types: Symbol, Callsite, RepoGraph Protocol, and markdown formatter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Symbol:
    """A named symbol extracted from source code.

    Attributes:
        name:           Simple identifier (e.g. ``"my_func"``).
        kind:           One of ``"function"``, ``"method"``, or ``"class"``.
        file:           Path to the file (relative to the worktree root).
        line:           1-based line number where the symbol is defined.
        qualified_name: Dot-separated qualified name
                        (e.g. ``"module.ClassName.method_name"``).
    """

    name: str
    kind: Literal["function", "method", "class"]
    file: str
    line: int
    qualified_name: str


@dataclass(frozen=True)
class Callsite:
    """A single location in the codebase that calls a symbol.

    Attributes:
        caller_file:     Path to the calling file (relative to worktree root).
        caller_line:     1-based line number of the call expression.
        caller_function: Name of the enclosing function or method, or ``None``
                         if the call is at module scope.
        called_symbol:   The symbol name as it appears at the call site (simple
                         name, not necessarily qualified).
    """

    caller_file: str
    caller_line: int
    caller_function: str | None
    called_symbol: str


@runtime_checkable
class RepoGraph(Protocol):
    """Protocol that all language-specific repo-graph implementations must satisfy."""

    def extract_symbols(self, file_path: str) -> list[Symbol]:
        """Return all top-level and class-member symbols defined in *file_path*.

        Args:
            file_path: Absolute or worktree-relative path to the source file.

        Returns:
            List of :class:`Symbol` objects.  Empty list on parse error or if
            the file contains no supported symbols.
        """
        ...

    def find_callers(self, symbol_name: str, search_root: Path) -> list[Callsite]:
        """Locate every call to *symbol_name* under *search_root*.

        Args:
            symbol_name: Simple (unqualified) name to search for.
            search_root: Directory to walk recursively.

        Returns:
            Up to 50 :class:`Callsite` objects.  Empty list when nothing is
            found or on error.
        """
        ...


def format_context_as_markdown(
    symbols: list[Symbol],
    callers_by_symbol: dict[str, list[Callsite]],
) -> str:
    """Render changed symbols and their callers as a readable markdown block.

    Suitable for injection into an LLM audit prompt so the auditor understands
    the call-graph impact of a diff.

    Args:
        symbols:           Changed symbols extracted from the diff.
        callers_by_symbol: Mapping from symbol name to its callsites.

    Returns:
        A markdown string.  Empty string when *symbols* is empty.

    Example output::

        ## Repo-Graph Context

        ### `my_func` (function) — `src/utils.py:10`
        Called from 2 location(s):
        - `src/main.py:42` in `run()` — calls `my_func`
        - `tests/test_utils.py:8` in `test_my_func()` — calls `my_func`
    """
    if not symbols:
        return ""

    lines: list[str] = ["## Repo-Graph Context\n"]
    for sym in symbols:
        callers = callers_by_symbol.get(sym.name, [])
        lines.append(f"### `{sym.name}` ({sym.kind}) — `{sym.file}:{sym.line}`")
        if callers:
            lines.append(f"Called from {len(callers)} location(s):")
            for cs in callers:
                scope = f" in `{cs.caller_function}()`" if cs.caller_function else " at module scope"
                lines.append(f"- `{cs.caller_file}:{cs.caller_line}`{scope} — calls `{cs.called_symbol}`")
        else:
            lines.append("No callers found in this repo.")
        lines.append("")  # blank line between symbols

    return "\n".join(lines).rstrip() + "\n"
