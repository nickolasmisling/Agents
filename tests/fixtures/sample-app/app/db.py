"""SQLite schema and connection helpers."""

import sqlite3
from contextlib import contextmanager

from . import DB_PATH
from .utils import utc_now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY,
    batch_no TEXT UNIQUE NOT NULL,
    product TEXT,
    site TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    planned_qty REAL,
    actual_qty REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    lot_no TEXT NOT NULL,
    name TEXT NOT NULL,
    qty REAL
);

CREATE TABLE IF NOT EXISTS signatures (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    meaning TEXT,
    signed_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_materials_batch ON materials (batch_id);
CREATE INDEX IF NOT EXISTS idx_signatures_batch ON signatures (batch_id);
"""


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def session(path=None):
    """Open a connection, commit on success, roll back on error, always close."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_audit(conn, table_name, record_id, action, old_value, new_value, user_id):
    conn.execute(
        "INSERT INTO audit_log (table_name, record_id, action, old_value, new_value, user_id, at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            table_name,
            record_id,
            action,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
            user_id,
            utc_now_iso(),
        ),
    )
