"""Look up a user record and return the user's display name."""
from __future__ import annotations


def get_display_name(user_id: int, users: dict[int, dict]) -> str:
    user = users.get(user_id)
    # FIX: guard against None before subscripting; return a safe fallback.
    if user is None:
        return "Unknown"
    return user["name"]
