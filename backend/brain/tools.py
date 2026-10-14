"""
tools.py
--------
Database access layer for Buddy V2.
All DB reads and writes go through these functions — nothing else touches the DB directly.

Key changes from hackathon version:
- get_user_memory() returns full rows (key, value, confidence, source) not flat dict
- update_memory() accepts confidence + source, uses proper upsert on (user_id, key)
- log_event() matches new events table shape and returns lastrowid
- log_emotion_pick() — new, for the emotion picker tap (source='user', highest-trust signal)
- save_conversation_turn() unchanged in contract, logs to events table instead of conversations
- get_conversation_history() reads from events table (conversation_turn rows)
"""

import json
from datetime import datetime
from database import get_conn


# ── Task history ──────────────────────────────────────────────────────────────

def get_task_history(task_id: int) -> dict:
    """Return the task row and all associated events, ordered by creation time."""
    conn = get_conn()
    c    = conn.cursor()
    task   = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    events = c.execute(
        "SELECT * FROM events WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    return {
        "task":   dict(task) if task else None,
        "events": [dict(e) for e in events],
    }


# ── Memory ────────────────────────────────────────────────────────────────────

def get_user_memory(user_id: int) -> list[dict]:
    """
    Return all memory rows for a user, ordered by confidence descending.

    Returns a list of dicts — NOT a flat key/value dict — so callers can see
    confidence and source. Buddy's system prompt injection uses all three fields.

    When multiple rows exist for overlapping semantic keys (e.g. onboarding.work_time
    and echo.pattern.work_time), the highest-confidence row wins — that logic lives
    in the caller (agent.py), not here.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT key, value, confidence, source
        FROM memory
        WHERE user_id = ?
        ORDER BY confidence DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_memory(
    user_id: int,
    key: str,
    value: str,
    confidence: float = 0.5,
    source: str = "buddy",
):
    """
    Upsert a memory entry for a user.

    Key naming convention (enforce in callers):
      onboarding.*         — seeded from form, pass confidence=0.3, source='onboarding'
      buddy.last_*         — after each conversation turn
      buddy.recent_*       — rolling window (e.g. last 3 interventions)
      echo.pattern.*       — Echo's behavioral pattern observations
      echo.belief.*        — Echo's tentative interpretive hypotheses (not facts)
      echo.notification.*  — learned notification timing/copy preferences
      echo.intervention.*  — intervention effectiveness per state

    On conflict: update value, confidence, source, and updated_at.
    This means Echo can overwrite a buddy.* entry by writing to the same key
    with higher confidence — or write to a separate echo.* key and let the
    agent pick the highest-confidence one.
    """
    conn = get_conn()
    now  = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO memory (user_id, key, value, confidence, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET
            value      = excluded.value,
            confidence = excluded.confidence,
            source     = excluded.source,
            updated_at = excluded.updated_at
        """,
        (user_id, key, value, confidence, source, now, now),
    )
    conn.commit()
    conn.close()


# ── Event logging ─────────────────────────────────────────────────────────────

def log_event(
    user_id: int,
    event_type: str,
    note: str = None,
    task_id: int = None,
    source: str = "system",
) -> int:
    """
    Append an event to the events table. Returns the new row's id (lastrowid).

    event_type enum (enforced here, not at DB level):
      postponed | completed | progress_logged | emotion_picked |
      notification_sent | notification_ignored | checkin_initiated |
      checkin_responded | silence | conversation_turn | echo_ran

    source:
      'user'   — direct self-report (emotion tap, explicit completion message)
      'buddy'  — agent-inferred or agent-generated
      'system' — scheduler, migration, automated

    Returning lastrowid matters when the caller (e.g. log_progress_if_needed)
    needs to reference the event it just created.
    """
    valid_event_types = {
        "postponed", "completed", "progress_logged", "emotion_picked",
        "notification_sent", "notification_ignored", "checkin_initiated",
        "checkin_responded", "silence", "conversation_turn", "echo_ran",
    }
    if event_type not in valid_event_types:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {valid_event_types}")

    conn = get_conn()
    cursor = conn.execute(
        """
        INSERT INTO events (user_id, task_id, event_type, note, source)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, task_id, event_type, note, source),
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def log_emotion_pick(user_id: int, emotion: str, task_id: int = None) -> int:
    """
    Log an emotion picker tap. Source is always 'user' — this is direct self-report,
    the highest-trust signal in the system. Do not use log_event() for this directly,
    because source must never be inferred or defaulted away from 'user'.

    Valid emotions for V2 default set: overwhelmed, tired, unclear
    Full set (once Echo personalises): overwhelmed, tired, unclear, bored, anxious

    Returns the new event's id.
    """
    valid_emotions = {"overwhelmed", "tired", "unclear", "bored", "anxious"}
    if emotion not in valid_emotions:
        raise ValueError(f"Invalid emotion '{emotion}'. Must be one of: {valid_emotions}")

    return log_event(
        user_id=user_id,
        event_type="emotion_picked",
        note=emotion,
        task_id=task_id,
        source="user",
    )


# ── Conversation history ───────────────────────────────────────────────────────

def save_conversation_turn(
    user_id: int,
    role: str,
    content: str,
    task_id: int = None,
    reasoning: str = None,
):
    """
    Persist a single conversation turn to the events table as a conversation_turn event.
    reasoning is a JSON string (assistant turns only) — stored in the note field prefixed
    so it's retrievable but doesn't collide with plain note text.

    role: 'user' | 'assistant'
    """
    source = "user" if role == "user" else "buddy"

    # For assistant turns with reasoning, store content + reasoning together in note
    # so we don't need a separate column. Format: "CONTENT|||REASONING_JSON"
    if role == "assistant" and reasoning:
        note = f"{content}|||{reasoning}"
    else:
        note = content

    log_event(
        user_id=user_id,
        event_type="conversation_turn",
        note=note,
        task_id=task_id,
        source=source,
    )


def get_conversation_history(user_id: int, limit: int = 20) -> list:
    """
    Return the last `limit` conversation turns as role/content dicts, oldest first.
    Strips the reasoning suffix from assistant notes before returning.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT source, note FROM events
        WHERE user_id = ? AND event_type = 'conversation_turn'
        ORDER BY created_at DESC LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()

    history = []
    for r in reversed(rows):
        role    = "user" if r["source"] == "user" else "assistant"
        content = r["note"] or ""
        # Strip reasoning suffix if present
        if "|||" in content:
            content = content.split("|||")[0]
        history.append({"role": role, "content": content})
    return history


def get_reasoning_history(user_id: int) -> list:
    """
    Return all stored reasoning snapshots for assistant turns, parsed from JSON.
    """
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT note, created_at FROM events
        WHERE user_id = ? AND event_type = 'conversation_turn' AND source = 'buddy'
        ORDER BY created_at ASC
        """,
        (user_id,),
    ).fetchall()
    conn.close()

    history = []
    for r in rows:
        note = r["note"] or ""
        if "|||" not in note:
            continue
        try:
            _, reasoning_json = note.split("|||", 1)
            parsed = json.loads(reasoning_json)
            parsed["timestamp"] = r["created_at"]
            history.append(parsed)
        except Exception:
            continue
    return history


# ── Task actions ──────────────────────────────────────────────────────────────

def complete_task(task_id: int, user_id: int = 1):
    """Mark a task as completed and log the completion event."""
    conn = get_conn()
    conn.execute(
        "UPDATE tasks SET status = 'completed' WHERE id = ?",
        (task_id,),
    )
    conn.commit()
    conn.close()
    log_event(
        user_id=user_id,
        event_type="completed",
        note="User marked task as done",
        task_id=task_id,
        source="user",
    )