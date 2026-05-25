"""Factory: return the appropriate test runner based on the test file extension.

Usage::

    from anneal.runner.factory import get_test_runner_for
    try:
        runner = get_test_runner_for(Path("tests/red/test_foo.ts"))
    except ValueError:
        # Unsupported extension — fall back to LLM-judge
        ...
    result = runner.run(worktree, test_file)
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from anneal.runner.go_test_runner import GoTestRunner
from anneal.runner.javascript_test_runner import JavaScriptTestRunner
from anneal.runner.python_test_runner import run_python_test
from anneal.runner.sandbox import TestRunResult

# Union of the concrete runner types returned by this factory.
# PythonTestRunner is a module-level function, so we wrap it in a minimal adapter.
_JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
_GO_EXTENSIONS = {".go"}
_PY_EXTENSIONS = {".py"}


class _PythonRunnerAdapter:
    """Thin adapter so PythonTestRunner matches the same .run() interface."""

    def run(self, worktree: Path, test_file: Path | str, timeout_s: int = 30) -> TestRunResult:
        return run_python_test(worktree, str(test_file), timeout=float(timeout_s))


TestRunner = Union[_PythonRunnerAdapter, JavaScriptTestRunner, GoTestRunner]


def get_test_runner_for(test_file: Path) -> TestRunner:
    """Return the appropriate runner for ``test_file``'s extension.

    Args:
        test_file: Path to the test file (only the suffix matters).

    Returns:
        A runner object with a ``.run(worktree, test_file, timeout_s)`` method.

    Raises:
        ValueError: If no runner is registered for the file's extension.

    Examples::

        runner = get_test_runner_for(Path("tests/test_foo.py"))
        runner = get_test_runner_for(Path("src/__tests__/foo.test.ts"))
        runner = get_test_runner_for(Path("pkg/foo_test.go"))
    """
    suffix = test_file.suffix.lower()

    if suffix in _PY_EXTENSIONS:
        return _PythonRunnerAdapter()

    if suffix in _JS_EXTENSIONS:
        return JavaScriptTestRunner(framework="auto")

    if suffix in _GO_EXTENSIONS:
        return GoTestRunner()

    raise ValueError(
        f"No test runner available for '{test_file.suffix}' files "
        f"(file: {test_file}). "
        f"Supported extensions: {sorted(_PY_EXTENSIONS | _JS_EXTENSIONS | _GO_EXTENSIONS)}"
    )
