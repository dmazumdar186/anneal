"""Validate that a string contains only ASCII word characters with optional separators."""
import re


# FIX: replace nested quantifiers with a possessive-style flat pattern that
# does not backtrack. Matches the same language without catastrophic complexity.
_PATTERN = re.compile(r"^[a-zA-Z0-9]+(?:[ \t]+[a-zA-Z0-9]+)*$")


def is_valid_label(value: str) -> bool:
    return bool(_PATTERN.match(value))
