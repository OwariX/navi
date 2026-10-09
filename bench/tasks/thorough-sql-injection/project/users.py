import sqlite3


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    return conn


def add_user(conn: sqlite3.Connection, name: str, email: str) -> int:
    cur = conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))
    return cur.lastrowid


def find_user(conn: sqlite3.Connection, name: str):
    """The (id, name, email) of the user with this name, or None."""
    return conn.execute(f"SELECT id, name, email FROM users WHERE name = '{name}'").fetchone()
