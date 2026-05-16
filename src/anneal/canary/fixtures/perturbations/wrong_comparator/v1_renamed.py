"""Determine if a computed exit code matches the special termination marker."""


def is_termination_marker(exit_code: int, marker: int = 300) -> bool:
    # BUG: same identity-vs-equality trap — `is` breaks outside CPython int cache range
    return exit_code is marker
