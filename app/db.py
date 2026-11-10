import sqlite3, threading
SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, customer_name TEXT, plan_tier TEXT, subject TEXT, body TEXT,
  channel TEXT, created_at TEXT, override TEXT, triage TEXT);
CREATE TABLE IF NOT EXISTS categories(name TEXT PRIMARY KEY, team TEXT, base INTEGER, keywords TEXT);
CREATE TABLE IF NOT EXISTS learned(category TEXT, word TEXT, n INTEGER, PRIMARY KEY(category, word));
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, created_at TEXT, reasons TEXT, mode TEXT,
  severity TEXT, status TEXT, error TEXT, to_addr TEXT, subject TEXT, body TEXT, steps TEXT);
"""

class DB:
    """Tiny thread-safe SQLite wrapper (FastAPI runs sync routes in a thread pool)."""
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.conn.executescript(SCHEMA)

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            self.conn.execute(sql, args)
            self.conn.commit()
