"""SQLite persistence. Each service call owns its connection/transaction."""
import sqlite3
from contextlib import contextmanager


@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path):
    """Create missing tables. Safe to run on new or existing databases.

    Every statement is CREATE TABLE IF NOT EXISTS, so an existing baseline
    database keeps its expenses and audit events and gains only the
    idempotency_keys table (added by H001). Running it again changes nothing.
    """
    with connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY,
            employee TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
            reviewer TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id TEXT NOT NULL REFERENCES expenses(id),
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        -- H001: one row per Idempotency-Key. The primary key makes a key
        -- usable only once; the CHECK repeats the API's key rule as a guard.
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY
                CHECK(length(key) BETWEEN 1 AND 100 AND key NOT GLOB '*[^A-Za-z0-9_.-]*'),
            request_hash TEXT NOT NULL,
            expense_id TEXT NOT NULL UNIQUE REFERENCES expenses(id),
            response_status INTEGER NOT NULL,
            response_body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        ''')
