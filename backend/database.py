"""
database.py
-----------
SQLite database setup for the Buddy accountability companion.

Tables:
  users         — registered users (demo: single user, id=1)
  tasks         — user tasks with status and due date
  task_events   — event log per task (postponed, completed, missed_checkin, etc.)
  agent_memory  — persistent key/value memory per user (learned preferences, patterns)
  conversations — full conversation history with optional reasoning JSON per assistant turn
"""

import sqlite3

DB_PATH = "companion.db"


def get_conn():
    """Open and return a SQLite connection with row_factory for dict-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist. Safe to call on every startup."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            title        TEXT NOT NULL,
            status       TEXT DEFAULT 'pending',
            created_at   TEXT NOT NULL,
            due_at       TEXT,
            completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS task_events (
            id                 INTEGER PRIMARY KEY,
            task_id            INTEGER NOT NULL,
            event_type         TEXT NOT NULL,
            note               TEXT,
            user_response_text TEXT,
            detected_state     TEXT,
            created_at         TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            id            INTEGER PRIMARY KEY,
            user_id       INTEGER NOT NULL,
            memory_key    TEXT NOT NULL,
            memory_value  TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            reasoning  TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()
    print("DB initialized.")
