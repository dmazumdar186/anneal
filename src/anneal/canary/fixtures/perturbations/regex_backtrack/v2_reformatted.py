"""Validate that a string contains only ASCII word characters with optional separators."""
import re

# BUG: same nested-quantifier catastrophic backtracking, just reformatted
_PATTERN = re.compile(
    r"^"
    r"([a-zA-Z0-9]+"  # one or more word chars
    r"[ \t]*"         # optional whitespace
    r")+"             # outer quantifier — causes catastrophic backtracking
    r"$"
)


def is_valid_label(value: str) -> bool:
    return bool(_PATTERN.match(value))
