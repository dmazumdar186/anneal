"""Validate that a string contains only ASCII word characters with optional separators."""
import re


def _compile_label_pattern() -> re.Pattern:
    # BUG: nested quantifier still present after refactor into a factory function
    return re.compile(r"^([a-zA-Z0-9]+[ \t]*)+$")


_PATTERN = _compile_label_pattern()


def is_valid_label(value: str) -> bool:
    return bool(_PATTERN.match(value))
