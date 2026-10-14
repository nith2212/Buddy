"""
database.py
-----------
SQLite database setup for Buddy V2.

Tables:
  users       — registered users (demo: single user, id=1)
  onboarding  — written once at setup, cold-start seed for memory
  tasks       — user tasks with status and deadline
  events      — everything observable: taps, completions, silence, chat turns, Echo runs
  memory      — structured per-user memory with confidence + source (replaces flat KV)
"""

import sqlite3

DB_PATH = "companion.db"


def get_conn():
    """Open and return a SQLite connection with row_factory for dict-like row access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all V2 tables if they don't exist. Safe to call on every startup."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            email               TEXT UNIQUE,
            created_at          TEXT DEFAULT (datetime('now')),
            onboarding_complete INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS onboarding (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id               INTEGER NOT NULL,
            preferred_work_time   TEXT,
            work_session_style    TEXT,
            procrastination_style TEXT,
            notification_opted_in INTEGER DEFAULT 1,
            created_at            TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER DEFAULT 1,
            title      TEXT NOT NULL,
            deadline   TEXT,
            status     TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # events is the single source of truth for everything observable.
    # event_type enum (enforced in app layer, not DB):
    #   postponed | completed | progress_logged | emotion_picked |
    #   notification_sent | notification_ignored | checkin_initiated |
    #   checkin_responded | silence | conversation_turn | echo_ran
    #
    # source: "buddy" | "user" | "system"
    #   - "user"   = direct self-report (emotion tap, explicit completion)
    #   - "buddy"  = agent-inferred or agent-generated
    #   - "system" = scheduler, migration, automated
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL DEFAULT 1,
            task_id    INTEGER,
            event_type TEXT NOT NULL,
            note       TEXT,
            source     TEXT DEFAULT 'system',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    """)

    # memory key namespace convention:
    #   onboarding.*          — seeded from form, confidence 0.3
    #   buddy.last_*          — written after each conversation turn
    #   buddy.recent_*        — rolling window (e.g. last 3 interventions)
    #   echo.pattern.*        — behavioral patterns from nightly Echo run
    #   echo.belief.*         — tentative interpretive observations (hypotheses, not facts)
    #   echo.notification.*   — learned notification timing/copy preferences
    #   echo.intervention.*   — which interventions work for which states
    #
    # source trust order: "onboarding" < "buddy" < "echo"
    # When keys overlap, higher confidence wins (Echo's version replaces onboarding once it exists).
    c.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL DEFAULT 1,
            key        TEXT NOT NULL,
            value      TEXT,
            confidence REAL DEFAULT 0.5,
            source     TEXT DEFAULT 'buddy',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_user_key
        ON memory (user_id, key)
    """)

    conn.commit()
    conn.close()
    print("DB initialized (V2 schema).")


def migrate_from_hackathon():
    """
    One-time migration from hackathon schema to V2 schema.

    What this does:
    - Inserts a default user (id=1) if not present
    - Copies tasks from old tasks table (adds user_id=1)
    - Backfills events from task_events + conversations — conservatively,
      everything becomes conversation_turn (no clever state inference,
      because old emotional_state was LLM-inferred, not user self-report)
    - Backfills memory from old agent_memory flat KV at confidence=0.5, source='buddy'
    - Inserts one echo_ran event to flag that pre-migration data is noisy baseline

    Safe to call multiple times — uses INSERT OR IGNORE throughout.
    """
    conn = get_conn()
    c = conn.cursor()

    # 1. Default user
    c.execute("""
        INSERT OR IGNORE INTO users (id, email, onboarding_complete)
        VALUES (1, 'default@buddy.local', 1)
    """)

    # 2. Copy tasks — add user_id=1, map old columns to new schema
    # Old: id, user_id, title, status, created_at, due_at, completed_at
    # New: id, user_id, title, deadline, status, created_at
    try:
        old_tasks = c.execute("""
            SELECT id, title, status, created_at, due_at FROM tasks
        """).fetchall()
        for t in old_tasks:
            c.execute("""
                INSERT OR IGNORE INTO tasks (id, user_id, title, deadline, status, created_at)
                VALUES (?, 1, ?, ?, ?, ?)
            """, (t["id"], t["title"], t.get("due_at"), t["status"], t["created_at"]))
    except Exception as e:
        print(f"[migrate] tasks copy skipped or partial: {e}")

    # 3. Backfill events from task_events
    # Everything becomes conversation_turn with source='buddy'.
    # We do NOT try to re-infer emotional_state as event_type — that data was
    # LLM-guessed, not user self-reported, and mislabeling it as emotion_picked
    # would teach Echo wrong patterns from day one.
    try:
        old_events = c.execute("""
            SELECT task_id, event_type, note, user_response_text, created_at
            FROM task_events
        """).fetchall()
        for e in old_events:
            # Preserve real event types (postponed, completed) — only reclassify
            # ambiguous ones that don't map cleanly to V2 event_type enum
            v2_event_type = e["event_type"]
            if v2_event_type not in (
                "postponed", "completed", "progress_logged",
                "checkin_initiated", "checkin_responded", "silence"
            ):
                v2_event_type = "conversation_turn"

            note = e.get("note") or e.get("user_response_text")
            c.execute("""
                INSERT OR IGNORE INTO events
                    (user_id, task_id, event_type, note, source, created_at)
                VALUES (1, ?, ?, ?, 'buddy', ?)
            """, (e["task_id"], v2_event_type, note, e["created_at"]))
    except Exception as e:
        print(f"[migrate] task_events backfill skipped or partial: {e}")

    # 4. Backfill events from conversations table
    try:
        old_convos = c.execute("""
            SELECT user_id, role, content, created_at FROM conversations
        """).fetchall()
        for row in old_convos:
            source = "user" if row["role"] == "user" else "buddy"
            c.execute("""
                INSERT OR IGNORE INTO events
                    (user_id, task_id, event_type, note, source, created_at)
                VALUES (?, NULL, 'conversation_turn', ?, ?, ?)
            """, (row["user_id"], row["content"][:500], source, row["created_at"]))
    except Exception as e:
        print(f"[migrate] conversations backfill skipped or partial: {e}")

    # 5. Backfill memory from old flat KV store
    try:
        old_memory = c.execute("""
            SELECT user_id, memory_key, memory_value, updated_at FROM agent_memory
        """).fetchall()
        for row in old_memory:
            # Remap old flat keys to new buddy.* namespace
            new_key = f"buddy.{row['memory_key']}"
            c.execute("""
                INSERT OR IGNORE INTO memory
                    (user_id, key, value, confidence, source, created_at, updated_at)
                VALUES (?, ?, ?, 0.5, 'buddy', ?, ?)
            """, (row["user_id"], new_key, row["memory_value"],
                  row["updated_at"], row["updated_at"]))
    except Exception as e:
        print(f"[migrate] agent_memory backfill skipped or partial: {e}")

    # 6. Insert echo_ran baseline marker so Echo knows on its first real run
    #    that historical data is noisy, not pristine behavioral signal
    c.execute("""
        INSERT OR IGNORE INTO events
            (user_id, task_id, event_type, note, source)
        VALUES (
            1, NULL, 'echo_ran',
            'pre-migration data loaded, treat as low-confidence baseline',
            'system'
        )
    """)

    conn.commit()
    conn.close()
    print("[migrate] Hackathon → V2 migration complete.")