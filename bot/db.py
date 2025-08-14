import sqlite3
from contextlib import contextmanager
from typing import Iterable, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS presence_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  username TEXT NOT NULL,
  status TEXT NOT NULL,
  timestamp DATETIME NOT NULL,
  guild_id INTEGER NOT NULL
);
"""

_db_path = None

def init_db(path: str):
    global _db_path
    _db_path = path
    with sqlite3.connect(_db_path) as conn:
        conn.execute(_SCHEMA)
        conn.commit()

@contextmanager
def _conn():
    if not _db_path:
        raise RuntimeError("DB não inicializado. Chame init_db(database_file) antes.")
    conn = sqlite3.connect(_db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    try:
        yield conn
    finally:
        conn.close()

def log_presence(user_id: int, username: str, status: str, ts: str, guild_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO presence_log (user_id, username, status, timestamp, guild_id) VALUES (?, ?, ?, ?, ?)",
            (int(user_id), username, status, ts, int(guild_id)),
        )
        conn.commit()

def fetch_one(query: str, params: Tuple = ()) -> Tuple:
    with _conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchone()

def fetch_all(query: str, params: Tuple = ()) -> Iterable[Tuple]:
    with _conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()
