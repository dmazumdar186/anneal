"""Fetch a user record from the database by username."""
import sqlite3


def _build_query(username: str) -> str:
    # BUG: query construction is extracted to a helper but the injection is still here
    return f"SELECT id, username, email FROM users WHERE username = '{username}'"


def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict | None:
    query = _build_query(username)
    cursor = conn.execute(query)
    row = cursor.fetchone()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "email": row[2]}
