"""Unit tests for anneal.diff.semantic — AST-aware semantic diff annotator."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from anneal.diff.semantic import summarize_diff


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_worktree(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write *files* into *tmp_path* and return it as the worktree root."""
    for rel_path, content in files.items():
        dest = tmp_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(textwrap.dedent(content), encoding="utf-8")
    return tmp_path


def _diff_adding_function(func_name: str = "validate_input") -> str:
    """Return a minimal unified diff that adds a new module-level function."""
    return textwrap.dedent(f"""\
        --- a/mymodule.py
        +++ b/mymodule.py
        @@ -1,3 +1,8 @@
         def existing():
             pass

        +
        +def {func_name}(value):
        +    if value is None:
        +        raise ValueError("value required")
        +    return value
    """)


def _diff_removing_class(class_name: str = "LegacyProcessor") -> str:
    """Return a minimal unified diff that removes a class."""
    return textwrap.dedent(f"""\
        --- a/mymodule.py
        +++ b/mymodule.py
        @@ -1,6 +1,1 @@
         def existing():
             pass
        -
        -
        -class {class_name}:
        -    def run(self):
        -        pass
    """)


def _diff_cosmetic_only() -> str:
    """Return a diff that only changes whitespace (cosmetically identical AST)."""
    return textwrap.dedent("""\
        --- a/mymodule.py
        +++ b/mymodule.py
        @@ -1,4 +1,4 @@
         def existing():
        -    pass
        +    pass

         x = 1
    """)


# ── Test 1: new function appears in summary ────────────────────────────────────

def test_new_function_detected(tmp_path: Path) -> None:
    """summarize_diff reports a newly added function with its name."""
    # Write the NEW state of the file to disk (what the worktree looks like now)
    worktree = _make_worktree(tmp_path, {
        "mymodule.py": """\
            def existing():
                pass


            def validate_input(value):
                if value is None:
                    raise ValueError("value required")
                return value
        """
    })

    diff = _diff_adding_function("validate_input")
    result = summarize_diff(diff, worktree)

    assert result, "Expected a non-empty summary"
    assert "1 new function" in result
    assert "`validate_input`" in result


# ── Test 2: removed class appears in summary ───────────────────────────────────

def test_removed_class_detected(tmp_path: Path) -> None:
    """summarize_diff reports a class that was removed."""
    # The NEW state of the file has the class gone
    worktree = _make_worktree(tmp_path, {
        "mymodule.py": """\
            def existing():
                pass
        """
    })

    diff = _diff_removing_class("LegacyProcessor")
    result = summarize_diff(diff, worktree)

    assert result, "Expected a non-empty summary"
    assert "class" in result.lower()
    assert "removed" in result.lower() or "LegacyProcessor" in result


# ── Test 3: cosmetic-only diff → "cosmetic" in summary ────────────────────────

def test_cosmetic_only_diff(tmp_path: Path) -> None:
    """summarize_diff flags a whitespace-only diff as cosmetic."""
    # The new file is structurally identical to old — just trailing space added
    worktree = _make_worktree(tmp_path, {
        "mymodule.py": """\
            def existing():
                pass

            x = 1
        """
    })

    diff = _diff_cosmetic_only()
    result = summarize_diff(diff, worktree)

    # Either the summary is empty (no signal) OR it mentions cosmetic
    if result:
        assert "cosmetic" in result.lower(), (
            f"Expected 'cosmetic' in summary when only whitespace changed, got:\n{result}"
        )


# ── Test 4: SyntaxError in modified file → empty string, no exception ─────────

def test_syntax_error_returns_empty(tmp_path: Path) -> None:
    """summarize_diff returns empty string when modified file has a SyntaxError."""
    # Write a broken Python file to disk
    worktree = _make_worktree(tmp_path, {
        "broken.py": "def broken(\n    # missing closing paren and body\n"
    })

    diff = textwrap.dedent("""\
        --- a/broken.py
        +++ b/broken.py
        @@ -1,1 +1,2 @@
        -x = 1
        +def broken(
        +    # missing closing paren and body
    """)

    # Must not raise; must return empty string or a safe fallback
    result = summarize_diff(diff, worktree)
    assert isinstance(result, str), "summarize_diff must always return a str"
    # When the file is unparseable, there's no semantic signal to surface
    assert result == "" or "## Semantic diff summary" in result
