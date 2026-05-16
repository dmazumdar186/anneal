"""Validate that a string contains only ASCII word characters with optional separators."""
import re


# BUG: nested quantifiers (a+)+ cause catastrophic backtracking on non-matching inputs.
_PATTERN = re.compile(r"^([a-zA-Z0-9]+[ \t]*)+$")


def is_valid_label(value: str) -> bool:
    return bool(_PATTERN.match(value))
