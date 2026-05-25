"""PythonRepoGraph: AST-based symbol extractor and caller finder for Python files."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from anneal.repograph.base import Callsite, RepoGraph, Symbol

logger = logging.getLogger(__name__)

# Directories to skip when walking the repo.
_SKIP_DIRS: frozenset[str] = frozenset({".venv", "__pycache__", ".git", ".anneal", "node_modules"})

# Maximum callers returned per symbol to avoid runaway on hot symbols.
_CALLER_CAP = 50


class _ScopeTracker(ast.NodeVisitor):
    """AST visitor that records Call nodes and their enclosing function scope."""

    def __init__(self, symbol_name: str, rel_path: str) -> None:
        self._symbol_name = symbol_name
        self._rel_path = rel_path
        self._scope_stack: list[str] = []
        self.callsites: list[Callsite] = []

    # ------------------------------------------------------------------
    # Scope tracking
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Classes themselves are not a function scope for "caller_function",
        # but methods inside them push their own scope via visit_FunctionDef.
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    # ------------------------------------------------------------------
    # Call detection
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        matched = False
        if isinstance(node.func, ast.Name) and node.func.id == self._symbol_name:
            matched = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == self._symbol_name:
            matched = True

        if matched:
            # caller_function: the innermost enclosing *function* in the scope
            # stack. Class names pushed via visit_ClassDef don't count by
            # themselves — only function/method names do.  We find the last
            # entry that was pushed by a FunctionDef.  Since we mix class names
            # into the stack for qualified_name tracking, we need to be a bit
            # careful: take the full dotted scope as the "caller_function" string
            # so the reader can see "ClassName.method_name".
            caller_function = ".".join(self._scope_stack) if self._scope_stack else None
            self.callsites.append(
                Callsite(
                    caller_file=self._rel_path,
                    caller_line=node.lineno,
                    caller_function=caller_function,
                    called_symbol=self._symbol_name,
                )
            )

        self.generic_visit(node)


class PythonRepoGraph:
    """Implements :class:`~anneal.repograph.base.RepoGraph` for Python source files.

    Uses the stdlib ``ast`` module — no third-party dependencies.

    Example::

        graph = PythonRepoGraph()
        symbols = graph.extract_symbols("src/utils.py")
        callers = graph.find_callers("my_func", Path("."))
    """

    # ------------------------------------------------------------------
    # RepoGraph protocol
    # ------------------------------------------------------------------

    def extract_symbols(self, file_path: str) -> list[Symbol]:
        """Parse *file_path* and return all function, class, and method symbols.

        Args:
            file_path: Path to a ``.py`` file (absolute or relative).

        Returns:
            Ordered list of :class:`~anneal.repograph.base.Symbol` objects.
            Returns an empty list if the file cannot be parsed.
        """
        path = Path(file_path)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            logger.warning("PythonRepoGraph.extract_symbols: SyntaxError in %s — %s", file_path, exc)
            return []
        except OSError as exc:
            logger.warning("PythonRepoGraph.extract_symbols: cannot read %s — %s", file_path, exc)
            return []

        rel = str(path)  # keep as-is; callers may pass relative or absolute
        symbols: list[Symbol] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    Symbol(
                        name=node.name,
                        kind="class",
                        file=rel,
                        line=node.lineno,
                        qualified_name=node.name,
                    )
                )
                # Collect methods inside this class.
                for child in ast.walk(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Only direct methods (not nested functions inside methods)
                        # are emitted as "method".  We detect direct children by
                        # checking that the child's parent in the class body is
                        # a direct item (ast.walk visits all depths, so we filter
                        # by checking the child is directly in node.body).
                        if child in node.body:
                            symbols.append(
                                Symbol(
                                    name=child.name,
                                    kind="method",
                                    file=rel,
                                    line=child.lineno,
                                    qualified_name=f"{node.name}.{child.name}",
                                )
                            )

        # Top-level functions (not inside any class).
        top_level_class_names: set[str] = {
            n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n in tree.body
        }
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    Symbol(
                        name=node.name,
                        kind="function",
                        file=rel,
                        line=node.lineno,
                        qualified_name=node.name,
                    )
                )

        return symbols

    def find_callers(self, symbol_name: str, search_root: Path) -> list[Callsite]:
        """Walk *search_root* and return call sites that reference *symbol_name*.

        Skips ``.venv/``, ``__pycache__/``, ``.git/``, and ``.anneal/``.
        Results are capped at 50 per symbol.

        Args:
            symbol_name: Simple (unqualified) name of the symbol to search for.
            search_root: Directory root to walk.

        Returns:
            Up to 50 :class:`~anneal.repograph.base.Callsite` objects.
        """
        callsites: list[Callsite] = []

        for py_file in self._walk_python_files(search_root):
            if len(callsites) >= _CALLER_CAP:
                break
            rel_path = str(py_file.relative_to(search_root))
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError as exc:
                logger.warning("PythonRepoGraph.find_callers: SyntaxError in %s — %s", py_file, exc)
                continue
            except OSError as exc:
                logger.warning("PythonRepoGraph.find_callers: cannot read %s — %s", py_file, exc)
                continue

            tracker = _ScopeTracker(symbol_name, rel_path)
            tracker.visit(tree)

            remaining = _CALLER_CAP - len(callsites)
            callsites.extend(tracker.callsites[:remaining])

        return callsites

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _walk_python_files(root: Path):
        """Yield all ``.py`` files under *root*, skipping ignored directories."""
        for item in root.iterdir():
            if item.is_dir():
                if item.name in _SKIP_DIRS:
                    continue
                yield from PythonRepoGraph._walk_python_files(item)
            elif item.is_file() and item.suffix == ".py":
                yield item
