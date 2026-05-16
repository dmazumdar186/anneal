"""Look up a user record and return the user's display name."""
from __future__ import annotations


def get_display_name(
    user_id: int,
    users: dict[int, dict],
) -> str:
    # attempt to find user in the mapping
    user = users.get(
        user_id
    )

    # return the display name field
    return user["name"]  # BUG: user may be None here
