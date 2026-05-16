"""Query a product catalogue by item name."""
import sqlite3


def find_product(db: sqlite3.Connection, item_name: str) -> dict | None:
    # BUG: same SQL injection — f-string interpolation of user input
    sql = f"SELECT id, name, price FROM products WHERE name = '{item_name}'"
    cur = db.execute(sql)
    row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "price": row[2]}
