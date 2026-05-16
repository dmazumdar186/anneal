"""Look up a user record and return the user's display name."""
from __future__ import annotations


def get_display_name(user_id: int, users: dict[int, dict]) -> str:
    user = users.get(user_id)
    # BUG: .get() returns None when key is absent; accessing ["name"] raises AttributeError/TypeError
    return user["name"]
