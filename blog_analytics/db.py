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
    persona_segment TEXT NOT NULL,
    device_type TEXT NOT NULL,
    region TEXT NOT NULL,
    profile_encrypted TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blogger_id INTEGER,
    post_id INTEGER,
    session_token TEXT NOT NULL,
    event_type TEXT NOT NULL,
    path TEXT NOT NULL,
    dwell_seconds INTEGER NOT NULL DEFAULT 0,
    details_encrypted TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (blogger_id) REFERENCES bloggers(id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (session_token) REFERENCES visitor_sessions(session_token)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    blogger_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    session_token TEXT NOT NULL,
    author_alias TEXT NOT NULL,
    content_encrypted TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (blogger_id) REFERENCES bloggers(id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    FOREIGN KEY (session_token) REFERENCES visitor_sessions(session_token)
);

CREATE INDEX IF NOT EXISTS idx_activity_blogger_event
ON activity_logs (blogger_id, event_type, occurred_at);

CREATE INDEX IF NOT EXISTS idx_activity_post_event
ON activity_logs (post_id, event_type, occurred_at);

CREATE INDEX IF NOT EXISTS idx_comments_post_created
ON comments (post_id, created_at);
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
    return g.db


def close_db(_error: Exception | None = None) -> None:
    if current_app.extensions.get("shared_db") is not None:
        return

    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
