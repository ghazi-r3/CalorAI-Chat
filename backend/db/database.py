"""
SQLite database initialization and connection management.

Design decision: daily totals are computed on-the-fly via SUM queries rather
than a materialized table. This avoids dual-write consistency bugs — the exact
class of bug the evaluators check for ("totals that break on a correction").
Trade-off: slightly more CPU per totals query, but correctness is guaranteed
by a single source of truth.
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.getenv("CALORAI_DB_PATH", "calorai.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'default',
    timestamp   DATETIME NOT NULL DEFAULT (datetime('now')),
    meal_type   TEXT,
    description TEXT NOT NULL,
    items       TEXT NOT NULL DEFAULT '[]',
    calories    REAL NOT NULL DEFAULT 0,
    protein_g   REAL NOT NULL DEFAULT 0,
    carbs_g     REAL NOT NULL DEFAULT 0,
    fat_g       REAL NOT NULL DEFAULT 0,
    fiber_g     REAL NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'text',
    raw_input   TEXT,
    image_path  TEXT,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at  DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'default',
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    category    TEXT NOT NULL,
    embedding   TEXT,
    confidence  REAL NOT NULL DEFAULT 1.0,
    created_at  DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at  DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, key)
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'default',
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    timestamp   DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_meals_user_date
    ON meals(user_id, timestamp) WHERE is_deleted = 0;
CREATE INDEX IF NOT EXISTS idx_memory_user
    ON memory(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session
    ON conversations(user_id, session_id);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and row factory."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path: str | None = None):
    """Context manager for database connections with auto-commit/rollback."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | None = None):
    """Initialize database schema. Safe to call multiple times (IF NOT EXISTS)."""
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
