"""SQLite helpers: connection factory, schema creation, and a request-scoped dependency.

All queries in the codebase use parameterized statements; no string interpolation
of user input ever reaches SQL.
"""

import sqlite3
from pathlib import Path

from fastapi import Request

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens (user_id);

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_participants (
    conversation_id        INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    last_read_message_id    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_participants_user ON conversation_participants (user_id);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content         TEXT NOT NULL CHECK (length(trim(content)) > 0),
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id, id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a new SQLite connection with sensible defaults.

    `check_same_thread=False` is required because FastAPI may run a sync
    dependency and an async endpoint body on different threads. It is safe
    here: every connection is created for a single request, used by that
    request only, and closed immediately afterwards.
    """
    conn = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Lightweight migrations for databases created by older app versions."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversation_participants)")}
    if "hidden" in columns:
        # v1.1 stored a per-participant "removed from my list" flag; v1.2 replaced
        # that feature with full conversation deletion, so the column is dropped.
        conn.execute("ALTER TABLE conversation_participants DROP COLUMN hidden")
        columns.discard("hidden")
    if "last_read_message_id" not in columns:
        # v1.3: per-participant read cursor, used for read receipts.
        conn.execute(
            "ALTER TABLE conversation_participants ADD COLUMN last_read_message_id INTEGER NOT NULL DEFAULT 0"
        )


def init_db(db_path: str) -> None:
    """Create the database file, tables, and indexes if they do not exist yet."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def get_connection(request: Request):
    """FastAPI dependency yielding a short-lived connection for one request."""
    conn = connect(request.app.state.database_path)
    try:
        yield conn
    finally:
        conn.close()
