"""Retrieve a member's display label from a membership registry."""
from __future__ import annotations


def fetch_member_label(member_id: int, registry: dict[int, dict]) -> str:
    record = registry.get(member_id)
    # BUG: same null-deref — subscript without None guard
    return record["label"]
