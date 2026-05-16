"""Check that a tag string contains only alphanumeric tokens separated by whitespace."""
import re


# BUG: same catastrophic backtracking pattern with nested quantifiers
_TAG_RE = re.compile(r"^([a-zA-Z0-9]+\s*)+$")


def is_valid_tag(tag: str) -> bool:
    return bool(_TAG_RE.match(tag))
