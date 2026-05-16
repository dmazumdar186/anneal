"""Look up a user record and return the user's display name."""
from __future__ import annotations


def _extract_name(user: dict) -> str:
    return user["name"]


def get_display_name(user_id: int, users: dict[int, dict]) -> str:
    user = users.get(user_id)
    # BUG: _extract_name is called regardless — None still propagates into the helper
    return _extract_name(user)  # type: ignore[arg-type]
