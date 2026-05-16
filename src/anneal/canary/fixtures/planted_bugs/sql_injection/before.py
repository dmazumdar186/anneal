"""Fetch a user record from the database by username."""
import sqlite3


def get_user_by_username(conn: sqlite3.Connection, username: str) -> dict | None:
    # BUG: username is interpolated directly into the SQL string — SQL injection vulnerability.
    query = f"SELECT id, username, email FROM users WHERE username = '{username}'"
    cursor = conn.execute(query)
    row = cursor.fetchone()
    if row is None:
        return None
    return {"id": row[0], "username": row[1], "email": row[2]}
