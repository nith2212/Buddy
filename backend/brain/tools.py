# Database access layer for Buddy's brain. All DB reads/writes the agent needs go
# through these functions — nothing else in brain/ touches the DB directly.
#
# Rewritten against the real deployed schema (models.py / SQLAlchemy), replacing
# the hackathon version that queried a raw-sqlite schema via a `database.py`
# module that was never ported (import would fail — database.py doesn't exist
# in this repo). Every function takes `db: Session`, passed in by the caller
# (FastAPI endpoint or cron job), matching the rest of the codebase's pattern —
# nothing here opens or closes its own connection.
#
# Every user-scoped query filters by user_id; nothing here trusts a bare id
# from the caller without it. Conversation turns go to the `Message` table
# (role/content/reasoning columns already exist there) rather than the old
# hack of packing "content|||reasoning_json" into a text field.

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Event, Memory, Message, Task

VALID_EVENT_TYPES = {
    "postponed", "completed", "progress_logged", "emotion_picked",
    "notification_sent", "notification_ignored", "checkin_initiated",
    "checkin_responded", "silence", "echo_ran",
}
VALID_EMOTIONS = {"overwhelmed", "tired", "unclear", "bored", "anxious"}


# ── Task history ──────────────────────────────────────────────────────────────

def get_task_history(db: Session, user_id: str, task_id: int) -> dict:
    """Return the task row (scoped to user_id) and its events, oldest first."""
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    ).scalar_one_or_none()
    events = db.execute(
        select(Event)
        .where(Event.task_id == task_id, Event.user_id == user_id)
        .order_by(Event.created_at.asc())
    ).scalars().all()
    return {
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "task_state": task.task_state,
            "due_date": task.due_date,
        } if task else None,
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "payload": e.payload,
                "detected_state": e.detected_state,
                "source": e.source,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


# ── Memory ────────────────────────────────────────────────────────────────────

def get_user_memory(db: Session, user_id: str) -> list[dict]:
    """
    Return all memory rows for a user, highest confidence first. A list of dicts
    (not a flat key/value map) so callers can see confidence and source —
    the system-prompt injection shows all three so Buddy can weigh trust.
    """
    rows = db.execute(
        select(Memory).where(Memory.user_id == user_id).order_by(Memory.confidence.desc())
    ).scalars().all()
    return [{"key": r.key, "value": r.value, "confidence": r.confidence, "source": r.source} for r in rows]


def update_memory(db: Session, user_id: str, key: str, value: str, confidence: float = 0.5, source: str = "buddy") -> None:
    """
    Upsert a memory entry for (user_id, key).

    Key naming convention (enforce in callers):
      onboarding.*  — seeded from form, confidence=0.3, source='onboarding'
      buddy.last_*  — written after each conversation turn
      buddy.recent_* — rolling window (e.g. last 3 interventions)
      echo.*        — Echo's weekly pattern observations, highest trust
    """
    row = db.execute(
        select(Memory).where(Memory.user_id == user_id, Memory.key == key)
    ).scalar_one_or_none()
    if row:
        row.value, row.confidence, row.source = value, confidence, source
    else:
        db.add(Memory(user_id=user_id, key=key, value=value, confidence=confidence, source=source))
    db.commit()


# ── Event logging ─────────────────────────────────────────────────────────────

def log_event(
    db: Session,
    user_id: str,
    event_type: str,
    task_id: Optional[int] = None,
    payload: Optional[str] = None,
    detected_state: Optional[str] = None,
    source: str = "system",
) -> int:
    """
    Append a row to `events`. Returns the new row's id.

    source: 'user' (direct self-report) | 'buddy' (agent-inferred/generated) | 'system' (scheduler).
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {VALID_EVENT_TYPES}")

    event = Event(
        user_id=user_id, task_id=task_id, type=event_type,
        payload=payload, detected_state=detected_state, source=source,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event.id


def log_emotion_pick(db: Session, user_id: str, emotion: str, task_id: Optional[int] = None) -> int:
    """Log an emotion-picker tap. Source is always 'user' — the highest-trust signal."""
    if emotion not in VALID_EMOTIONS:
        raise ValueError(f"Invalid emotion '{emotion}'. Must be one of: {VALID_EMOTIONS}")
    return log_event(db, user_id, "emotion_picked", task_id=task_id, payload=emotion, source="user")


# ── Conversation history ───────────────────────────────────────────────────────

def save_conversation_turn(
    db: Session,
    user_id: str,
    role: str,
    content: str,
    task_id: Optional[int] = None,
    reasoning: Optional[dict] = None,
) -> int:
    """Persist one turn to `messages`. role: 'user' | 'assistant'. Returns the new row's id."""
    message = Message(
        user_id=user_id, task_id=task_id, role=role, content=content,
        reasoning=json.dumps(reasoning) if reasoning else None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message.id


def get_conversation_history(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    """Return the last `limit` turns as {"role", "content"} dicts, oldest first."""
    rows = db.execute(
        select(Message).where(Message.user_id == user_id).order_by(Message.created_at.desc()).limit(limit)
    ).scalars().all()
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def get_reasoning_history(db: Session, user_id: str) -> list[dict]:
    """Return all stored reasoning snapshots for assistant turns, oldest first."""
    rows = db.execute(
        select(Message)
        .where(Message.user_id == user_id, Message.role == "assistant", Message.reasoning.is_not(None))
        .order_by(Message.created_at.asc())
    ).scalars().all()
    history = []
    for m in rows:
        try:
            parsed = json.loads(m.reasoning)
        except (TypeError, ValueError):
            continue
        parsed["timestamp"] = m.created_at
        history.append(parsed)
    return history


# ── Task actions ──────────────────────────────────────────────────────────────

def complete_task(db: Session, user_id: str, task_id: int) -> None:
    """Mark a task done (scoped to user_id) and log the completion event. No-op if not found/owned."""
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    ).scalar_one_or_none()
    if not task:
        return
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    log_event(db, user_id, "completed", task_id=task_id, payload="User marked task as done", source="user")
