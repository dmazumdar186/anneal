"""Unit tests for anneal.repograph — symbol extraction and caller finding."""

from __future__ import annotations

from pathlib import Path

import pytest

from anneal.repograph.base import format_context_as_markdown
from anneal.repograph.diff_extractor import build_context_for_diff, extract_changed_symbols
from anneal.repograph.python_graph import PythonRepoGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def graph() -> PythonRepoGraph:
    return PythonRepoGraph()


# ---------------------------------------------------------------------------
# Test 1 — extract_symbols: happy-path with functions, class, and methods
# ---------------------------------------------------------------------------

def test_extract_symbols_happy_path(tmp_path: Path, graph: PythonRepoGraph) -> None:
    src = tmp_path / "sample.py"
    src.write_text(
        """\
def standalone():
    pass


async def async_func():
    pass


class MyClass:
    def method_a(self):
        pass

    def method_b(self):
        pass
""",
        encoding="utf-8",
    )

    symbols = graph.extract_symbols(str(src))
    by_qname = {s.qualified_name: s for s in symbols}

    # Top-level functions
    assert "standalone" in by_qname
    assert by_qname["standalone"].kind == "function"
    assert by_qname["standalone"].line == 1

    assert "async_func" in by_qname
    assert by_qname["async_func"].kind == "function"
    assert by_qname["async_func"].line == 5

    # Class
    assert "MyClass" in by_qname
    assert by_qname["MyClass"].kind == "class"
    assert by_qname["MyClass"].line == 9

    # Methods
    assert "MyClass.method_a" in by_qname
    assert by_qname["MyClass.method_a"].kind == "method"
    assert by_qname["MyClass.method_a"].line == 10

    assert "MyClass.method_b" in by_qname
    assert by_qname["MyClass.method_b"].kind == "method"
    assert by_qname["MyClass.method_b"].line == 13


# ---------------------------------------------------------------------------
# Test 2 — extract_symbols: graceful return on SyntaxError
# ---------------------------------------------------------------------------

def test_extract_symbols_syntax_error(tmp_path: Path, graph: PythonRepoGraph) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def (:\n    pass\n", encoding="utf-8")

    result = graph.extract_symbols(str(bad))
    assert result == [], "Expected empty list on SyntaxError, got: %r" % result


# ---------------------------------------------------------------------------
# Test 3 — find_callers: detects calls in two files
# ---------------------------------------------------------------------------

def test_find_callers_two_files(tmp_path: Path, graph: PythonRepoGraph) -> None:
    # definer.py — defines foo (calls here should NOT be picked up unless foo
    # itself is called inside the file, which it isn't).
    definer = tmp_path / "definer.py"
    definer.write_text("def foo():\n    pass\n", encoding="utf-8")

    # caller_a.py — calls foo at module scope
    caller_a = tmp_path / "caller_a.py"
    caller_a.write_text("from definer import foo\n\nfoo()\n", encoding="utf-8")

    # caller_b.py — calls foo inside a function
    caller_b = tmp_path / "caller_b.py"
    caller_b.write_text(
        "def run():\n    foo()\n",
        encoding="utf-8",
    )

    callers = graph.find_callers("foo", tmp_path)
    assert len(callers) == 2, f"Expected 2 callsites, got {len(callers)}: {callers}"

    files = {cs.caller_file for cs in callers}
    assert "caller_a.py" in files
    assert "caller_b.py" in files

    # The call in caller_b is inside a function named "run"
    b_cs = next(cs for cs in callers if cs.caller_file == "caller_b.py")
    assert b_cs.caller_function == "run"

    # The call in caller_a is at module scope
    a_cs = next(cs for cs in callers if cs.caller_file == "caller_a.py")
    assert a_cs.caller_function is None


# ---------------------------------------------------------------------------
# Test 4 — find_callers: __pycache__ directory is skipped
# ---------------------------------------------------------------------------

def test_find_callers_skips_pycache(tmp_path: Path, graph: PythonRepoGraph) -> None:
    # Real caller
    real = tmp_path / "real_caller.py"
    real.write_text("bar()\n", encoding="utf-8")

    # Fake pycache file that also calls bar — should be skipped
    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    cached = pycache_dir / "cached.py"
    cached.write_text("bar()\n", encoding="utf-8")

    callers = graph.find_callers("bar", tmp_path)
    caller_files = {cs.caller_file for cs in callers}

    assert "real_caller.py" in caller_files
    # No entry from __pycache__
    assert not any("__pycache__" in f for f in caller_files), (
        f"__pycache__ entries leaked into callers: {caller_files}"
    )


# ---------------------------------------------------------------------------
# Test 5 — build_context_for_diff: produces markdown with symbol + callers
# ---------------------------------------------------------------------------

def test_build_context_for_diff(tmp_path: Path, graph: PythonRepoGraph) -> None:
    # Write the "changed" file that the diff references
    changed = tmp_path / "utils.py"
    changed.write_text("def compute():\n    return 42\n", encoding="utf-8")

    # Two callers
    (tmp_path / "main.py").write_text(
        "def run():\n    compute()\n",
        encoding="utf-8",
    )
    (tmp_path / "helper.py").write_text(
        "compute()\n",
        encoding="utf-8",
    )

    # Unified diff that marks utils.py as changed
    diff = (
        "diff --git a/utils.py b/utils.py\n"
        "--- a/utils.py\n"
        "+++ b/utils.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def compute():\n"
        "+def compute():  # modified\n"
        "     return 42\n"
    )

    result = build_context_for_diff(diff, tmp_path, graph)

    assert result, "Expected non-empty markdown block"
    assert "## Repo-Graph Context" in result
    assert "`compute`" in result
    # Should mention both callers
    assert "main.py" in result
    assert "helper.py" in result
