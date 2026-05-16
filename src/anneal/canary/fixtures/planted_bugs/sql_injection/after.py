"""Fetch a user record from the database by username."""
import sqlite3


def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict | None:
    # FIX: use a parameterized query — the DB driver escapes the value safely.
    query = "SELECT id, username, email FROM users WHERE username = ?"
    cursor = conn.execute(query, (username,))
    row = cursor.fetchone()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "email": row[2]}
