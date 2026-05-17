from __future__ import annotations

import sqlite3

from flask import current_app, g

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bloggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('standard', 'premium')),
    bio TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS visitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blogger_id INTEGER NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (blogger_id) REFERENCES bloggers(id)
);

CREATE TABLE IF NOT EXISTS visitor_sessions (
    session_token TEXT PRIMARY KEY,
    visitor_id INTEGER,
    visitor_type TEXT NOT NULL DEFAULT 'anonymous' CHECK(visitor_type IN ('anonymous', 'authenticated')),
    persona_segment TEXT NOT NULL,
    device_type TEXT NOT NULL,
    region TEXT NOT NULL,
    profile_encrypted TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY (visitor_id) REFERENCES visitors(id)
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blogger_id INTEGER,
    post_id INTEGER,
    session_token TEXT NOT NULL,
    visitor_id INTEGER,
    visitor_type TEXT NOT NULL DEFAULT 'anonymous' CHECK(visitor_type IN ('anonymous', 'authenticated')),
    event_type TEXT NOT NULL,
    path TEXT NOT NULL,
    dwell_seconds INTEGER NOT NULL DEFAULT 0,
    details_encrypted TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (blogger_id) REFERENCES bloggers(id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (session_token) REFERENCES visitor_sessions(session_token),
    FOREIGN KEY (visitor_id) REFERENCES visitors(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blogger_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    session_token TEXT NOT NULL,
    visitor_id INTEGER,
    visitor_type TEXT NOT NULL DEFAULT 'anonymous' CHECK(visitor_type IN ('anonymous', 'authenticated')),
    author_alias TEXT NOT NULL,
    content_encrypted TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (blogger_id) REFERENCES bloggers(id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (session_token) REFERENCES visitor_sessions(session_token),
    FOREIGN KEY (visitor_id) REFERENCES visitors(id)
);

CREATE INDEX IF NOT EXISTS idx_activity_blogger_event
ON activity_logs (blogger_id, event_type, occurred_at);

CREATE INDEX IF NOT EXISTS idx_activity_post_event
ON activity_logs (post_id, event_type, occurred_at);

CREATE INDEX IF NOT EXISTS idx_comments_post_created
ON comments (post_id, created_at);
"""

MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_visitor_sessions_type
ON visitor_sessions (visitor_type, visitor_id);

CREATE INDEX IF NOT EXISTS idx_activity_visitor_type
ON activity_logs (visitor_type, visitor_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_comments_visitor_type
ON comments (visitor_type, visitor_id, created_at);
"""


def get_db() -> sqlite3.Connection:
    shared_db = current_app.extensions.get("shared_db")
    if shared_db is not None:
        return shared_db

    if "db" not in g:
        database = current_app.config["DATABASE"]
        g.db = sqlite3.connect(
            database,
            detect_types=sqlite3.PARSE_DECLTYPES,
            uri=database.startswith("file:"),
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=TRUNCATE")
    return g.db


def close_db(_error: Exception | None = None) -> None:
    if current_app.extensions.get("shared_db") is not None:
        return

    db = g.pop("db", None)
    if db is not None:
        db.close()


def _table_columns(db: sqlite3.Connection, table: str) -> set[str]:
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _ensure_column(
    db: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    if column not in _table_columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _migrate_existing_schema(db: sqlite3.Connection) -> None:
    _ensure_column(db, "visitor_sessions", "visitor_id", "visitor_id INTEGER NULL")
    _ensure_column(
        db,
        "visitor_sessions",
        "visitor_type",
        "visitor_type TEXT NOT NULL DEFAULT 'anonymous'",
    )
    _ensure_column(db, "activity_logs", "visitor_id", "visitor_id INTEGER NULL")
    _ensure_column(
        db,
        "activity_logs",
        "visitor_type",
        "visitor_type TEXT NOT NULL DEFAULT 'anonymous'",
    )
    _ensure_column(db, "comments", "visitor_id", "visitor_id INTEGER NULL")
    _ensure_column(
        db,
        "comments",
        "visitor_type",
        "visitor_type TEXT NOT NULL DEFAULT 'anonymous'",
    )


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    _migrate_existing_schema(db)
    db.executescript(MIGRATION_INDEXES)
    db.commit()
