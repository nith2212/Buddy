"""
tools.py
--------
Database access layer for the Buddy accountability companion.
All DB reads and writes go through these functions — nothing else touches the DB directly.
"""

import json
from datetime import datetime
from database import get_conn


def get_task_history(task_id: int) -> dict:
    """Return the task row and all associated events, ordered by creation time."""
    conn = get_conn()
    c    = conn.cursor()
    task   = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    events = c.execute(
        "SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    return {
        "task":   dict(task) if task else None,
        "events": [dict(e) for e in events],
    }


def get_user_memory(user_id: int) -> dict:
    """Return all agent memory for a user as a flat key/value dict."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT memory_key, memory_value FROM agent_memory WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    conn.close()
    return {row["memory_key"]: row["memory_value"] for row in rows}


def update_memory(user_id: int, key: str, value: str):
    """
    Upsert a memory key for a user.
    SQLite lacks native ON CONFLICT UPDATE, so we INSERT-ignore then UPDATE.
    """
    conn = get_conn()
    now  = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO agent_memory (user_id, memory_key, memory_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        """,
        (user_id, key, value, now),
    )
    conn.execute(
        """
        UPDATE agent_memory SET memory_value = ?, updated_at = ?
        WHERE user_id = ? AND memory_key = ?
        """,
        (value, now, user_id, key),
    )
    conn.commit()
    conn.close()


def log_event(
    task_id: int,
    event_type: str,
    note: str = None,
    user_response_text: str = None,
    detected_state: str = None,
):
    """Append an event to the task event log."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO task_events
            (task_id, event_type, note, user_response_text, detected_state, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, event_type, note, user_response_text, detected_state, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def save_conversation_turn(user_id: int, role: str, content: str, reasoning: str = None):
    """Persist a single conversation turn. reasoning is a JSON string (assistant turns only)."""
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO conversations (user_id, role, content, reasoning, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, role, content, reasoning, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_conversation_history(user_id: int, limit: int = 20) -> list:
    """Return the last `limit` conversation turns, oldest first."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT role, content FROM conversations
        WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_reasoning_history(user_id: int) -> list:
    """
    Return all stored reasoning snapshots for assistant turns, parsed from JSON.
    Each item includes the original timestamp.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT reasoning, created_at FROM conversations
        WHERE user_id = ? AND role = 'assistant' AND reasoning IS NOT NULL
        ORDER BY created_at ASC
        """,
        (user_id,),
    ).fetchall()
    conn.close()

    history = []
    for r in rows:
        try:
            parsed = json.loads(r["reasoning"])
            parsed["timestamp"] = r["created_at"]
            history.append(parsed)
        except Exception:
            continue
    return history


def complete_task(task_id: int):
    """Mark a task as completed and log the completion event."""
    conn = get_conn()
    conn.execute(
        "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), task_id),
    )
    conn.commit()
    conn.close()
    log_event(task_id, "completed", note="User marked task as done")
