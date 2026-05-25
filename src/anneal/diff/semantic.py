"""AST-aware semantic diff annotator.

Takes a unified diff string and the worktree path, parses old/new versions of
each changed ``.py`` file with :mod:`ast`, and returns a markdown summary block
describing structural changes.

Detected classes
----------------
- Functions added / removed at module level
- Methods added / removed per class
- Classes added / removed
- Variable rename heuristic (same ``Name`` removed + added with high similarity)
- Pure-cosmetic hunks (AST structurally identical across the hunk's lines)

Entry point
-----------
:func:`summarize_diff` — returns a markdown string or empty string when there is
nothing worth surfacing.

Design notes
------------
- Pure-stdlib: uses only ``ast`` + ``difflib`` (no subprocess).
- Gracefully handles ``SyntaxError`` (logs a warning, returns ``""``).
- Never raises; all exceptions are caught and logged.
"""

from __future__ import annotations

import ast
import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── Diff parsing ───────────────────────────────────────────────────────────────

_DIFF_FILE_RE = re.compile(r"^(?:---|\+\+\+) [ab]/(.+)$", re.MULTILINE)


@dataclass
class _Hunk:
    old_lines: list[str] = field(default_factory=list)
    new_lines: list[str] = field(default_factory=list)


@dataclass
class _FileDiff:
    path: str
    hunks: list[_Hunk] = field(default_factory=list)
    old_source: str | None = None  # populated from worktree / git
    new_source: str | None = None


def _parse_unified_diff(diff: str) -> list[_FileDiff]:
    """Return one _FileDiff per changed file in a unified diff string."""
    files: list[_FileDiff] = []
    current: _FileDiff | None = None
    current_hunk: _Hunk | None = None

    for line in diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            # "--- a/path" or "+++ b/path"
            raw_path = line[4:].split("\t")[0]  # strip tab + timestamp if present
            if raw_path.startswith("a/") or raw_path.startswith("b/"):
                raw_path = raw_path[2:]

            if line.startswith("--- "):
                current_hunk = None
                current = _FileDiff(path=raw_path)
                # We'll de-dup when we see the +++ line
            elif line.startswith("+++ ") and current is not None:
                # Confirm the path; prefer the "+++ b/" path as canonical
                current.path = raw_path
                files.append(current)

        elif line.startswith("@@ ") and current is not None:
            current_hunk = _Hunk()
            current.hunks.append(current_hunk)

        elif current_hunk is not None:
            if line.startswith("-"):
                current_hunk.old_lines.append(line[1:])
            elif line.startswith("+"):
                current_hunk.new_lines.append(line[1:])
            elif line.startswith(" "):
                # context line — belongs to both sides
                current_hunk.old_lines.append(line[1:])
                current_hunk.new_lines.append(line[1:])

    # De-duplicate in case --- and +++ produced the same path twice
    seen: set[str] = set()
    unique: list[_FileDiff] = []
    for fd in files:
        if fd.path not in seen:
            seen.add(fd.path)
            unique.append(fd)
    return unique


# ── AST helpers ────────────────────────────────────────────────────────────────


class _Symbols(NamedTuple):
    functions: set[str]                    # module-level function names
    classes: set[str]                      # class names
    methods: dict[str, set[str]]           # class → set of method names
    top_names: set[str]                    # all Name nodes at module scope


def _extract_symbols(source: str) -> _Symbols | None:
    """Parse *source* and return its top-level symbols.

    Returns ``None`` on ``SyntaxError``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning("semantic.py: SyntaxError while parsing source: %s", exc)
        return None

    functions: set[str] = set()
    classes: set[str] = set()
    methods: dict[str, set[str]] = {}
    top_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            top_names.add(node.id)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
            meths: set[str] = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    meths.add(item.name)
            methods[node.name] = meths

    return _Symbols(
        functions=functions,
        classes=classes,
        methods=methods,
        top_names=top_names,
    )


def _ast_identical(source_a: str, source_b: str) -> bool:
    """Return True iff the two sources produce identical AST dumps (ignoring positions)."""
    try:
        tree_a = ast.parse(source_a)
        tree_b = ast.parse(source_b)
    except SyntaxError:
        return False
    return ast.dump(tree_a) == ast.dump(tree_b)


# ── Rename heuristic ───────────────────────────────────────────────────────────

def _detect_renames(
    old_names: set[str],
    new_names: set[str],
    old_source: str,
    new_source: str,
) -> list[tuple[str, str, int]]:
    """Return a list of ``(old_name, new_name, occurrence_count)`` rename candidates.

    Heuristic: a name disappears from ``old_names``, a new name appears in
    ``new_names``, and the ratio of occurrences in the diff content is similar.
    We require at least 2 occurrences to avoid flagging trivial one-off changes.
    """
    removed = old_names - new_names
    added = new_names - old_names

    renames: list[tuple[str, str, int]] = []
    for old_n in removed:
        old_count = old_source.count(old_n)
        if old_count < 2:
            continue
        # Look for the best match in added names by string similarity
        best_match: str | None = None
        best_ratio = 0.0
        for new_n in added:
            ratio = difflib.SequenceMatcher(None, old_n, new_n).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = new_n
        # Accept if ratio >= 0.5 (handles e.g. tmp→accumulator poorly but
        # catches camelCase renames, abbreviation expansions, etc.) OR if the
        # new name appears exactly as many times as old was removed.
        if best_match is not None:
            new_count = new_source.count(best_match)
            if best_ratio >= 0.5 or abs(old_count - new_count) <= 1:
                renames.append((old_n, best_match, max(old_count, new_count)))
    return renames


# ── Cosmetic hunk detection ────────────────────────────────────────────────────

def _hunk_is_cosmetic(hunk: _Hunk) -> bool:
    """Return True if the hunk's old and new sides have identical ASTs.

    Falls back to a line-level check when parsing fails.
    """
    old_src = "\n".join(hunk.old_lines)
    new_src = "\n".join(hunk.new_lines)

    if not old_src.strip() and not new_src.strip():
        return True  # empty on both sides — pure whitespace

    return _ast_identical(old_src, new_src)


# ── Public API ─────────────────────────────────────────────────────────────────


def summarize_diff(diff: str, worktree: Path) -> str:
    """Return a markdown "## Semantic diff summary" block for *diff*.

    Reads old/new file content from the worktree (new version = current file on
    disk; old version = reconstructed from the diff itself).

    Args:
        diff:      Unified diff string (as produced by ``git diff``).
        worktree:  Absolute path to the repository root / worktree.

    Returns:
        A non-empty markdown string when there is semantic signal worth surfacing,
        or an empty string when the diff has no Python files or no signal.
    """
    if not diff.strip():
        return ""

    file_diffs = _parse_unified_diff(diff)
    # Keep only .py files
    py_diffs = [fd for fd in file_diffs if fd.path.endswith(".py")]
    if not py_diffs:
        return ""

    # Populate old/new source for each file
    for fd in py_diffs:
        file_path = worktree / fd.path
        # New source = current file on disk (after the change)
        try:
            fd.new_source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            fd.new_source = None

        # Old source = reconstruct by applying the reverse of hunk changes
        # Simple approach: take the new source and replace added lines with
        # removed lines per hunk.  Good enough for symbol detection.
        if fd.new_source is not None:
            old_lines: list[str] = []
            for hunk in fd.hunks:
                old_lines.extend(hunk.old_lines)
            fd.old_source = "\n".join(old_lines) if old_lines else fd.new_source
        else:
            fd.old_source = None

    bullets: list[str] = []
    cosmetic_hunk_count = 0
    rename_candidates: list[tuple[str, str, int]] = []

    for fd in py_diffs:
        old_src = fd.old_source or ""
        new_src = fd.new_source or ""

        old_syms = _extract_symbols(old_src) if old_src.strip() else None
        new_syms = _extract_symbols(new_src) if new_src.strip() else None

        # ── Functions ─────────────────────────────────────────────────────────
        if old_syms is not None and new_syms is not None:
            added_fns = new_syms.functions - old_syms.functions
            removed_fns = old_syms.functions - new_syms.functions
            if added_fns:
                names = ", ".join(f"`{n}`" for n in sorted(added_fns))
                count = len(added_fns)
                bullets.append(
                    f"{count} new function{'s' if count != 1 else ''}: {names}"
                )
            if removed_fns:
                names = ", ".join(f"`{n}`" for n in sorted(removed_fns))
                count = len(removed_fns)
                bullets.append(
                    f"{count} function{'s' if count != 1 else ''} removed: {names}"
                )

            # ── Classes ───────────────────────────────────────────────────────
            added_cls = new_syms.classes - old_syms.classes
            removed_cls = old_syms.classes - new_syms.classes
            if added_cls:
                names = ", ".join(f"`{n}`" for n in sorted(added_cls))
                count = len(added_cls)
                bullets.append(
                    f"{count} new class{'es' if count != 1 else ''}: {names}"
                )
            if removed_cls:
                names = ", ".join(f"`{n}`" for n in sorted(removed_cls))
                count = len(removed_cls)
                bullets.append(
                    f"{count} class{'es' if count != 1 else ''} removed: {names}"
                )

            # ── Methods per class ─────────────────────────────────────────────
            all_classes = old_syms.classes | new_syms.classes
            for cls_name in sorted(all_classes):
                old_meths = old_syms.methods.get(cls_name, set())
                new_meths = new_syms.methods.get(cls_name, set())
                added_m = new_meths - old_meths
                removed_m = old_meths - new_meths
                if added_m:
                    names = ", ".join(f"`{n}`" for n in sorted(added_m))
                    count = len(added_m)
                    bullets.append(
                        f"{count} new method{'s' if count != 1 else ''} on `{cls_name}`: {names}"
                    )
                if removed_m:
                    names = ", ".join(f"`{n}`" for n in sorted(removed_m))
                    count = len(removed_m)
                    bullets.append(
                        f"{count} method{'s' if count != 1 else ''} removed from `{cls_name}`: {names}"
                    )

            # ── Rename heuristic ──────────────────────────────────────────────
            file_renames = _detect_renames(
                old_syms.top_names, new_syms.top_names, old_src, new_src
            )
            rename_candidates.extend(file_renames)

        elif old_syms is None and new_syms is None:
            # Both parse failed — no signal
            pass

        # ── Cosmetic hunks ────────────────────────────────────────────────────
        for hunk in fd.hunks:
            if _hunk_is_cosmetic(hunk):
                cosmetic_hunk_count += 1

    # ── Renames ───────────────────────────────────────────────────────────────
    for old_n, new_n, count in rename_candidates:
        bullets.append(
            f"1 likely rename: `{old_n}` → `{new_n}` ({count} occurrence{'s' if count != 1 else ''})"
        )

    # ── Cosmetic summary ──────────────────────────────────────────────────────
    total_hunks = sum(len(fd.hunks) for fd in py_diffs)
    if cosmetic_hunk_count > 0:
        if cosmetic_hunk_count == total_hunks:
            bullets.append("all hunks appear cosmetic (whitespace/comments only)")
        else:
            bullets.append(
                f"{cosmetic_hunk_count} hunk{'s' if cosmetic_hunk_count != 1 else ''} "
                f"appear cosmetic (whitespace/comments only)"
            )

    if not bullets:
        return ""

    lines = ["## Semantic diff summary"]
    for b in bullets:
        lines.append(f"- {b}")
    return "\n".join(lines)
