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
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from brain.state_detection import EMOTION_TO_STATE, as_utc
from models import Event, Memory, Message, Task

VALID_EVENT_TYPES = {
    "postponed", "completed", "progress_logged", "emotion_picked",
    "notification_sent", "notification_ignored", "checkin_initiated",
    "checkin_responded", "silence", "echo_ran",
}
VALID_EMOTIONS = set(EMOTION_TO_STATE)  # the reasons a user can tap


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


def update_memory(
    db: Session, user_id: str, key: str, value: str,
    confidence: float = 0.5, source: str = "buddy", commit: bool = True,
) -> None:
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
    if commit:
        db.commit()
    else:
        db.flush()  # make the row visible to later queries in the same transaction


def get_memory_entry(db: Session, user_id: str, key: str) -> Optional[Memory]:
    return db.execute(
        select(Memory).where(Memory.user_id == user_id, Memory.key == key)
    ).scalar_one_or_none()


def record_confirmed_cause(db: Session, user_id: str, task_id: int, cause: str, commit: bool = True) -> None:
    """
    Remember a cause the user CONFIRMED: blocker.task.<id> = the cause, and pattern.blocker.<cause>
    counts how often it has been confirmed. Only called for confirmed causes, never guesses.
    """
    if cause not in VALID_EMOTIONS:
        raise ValueError(f"Invalid cause '{cause}'. Must be one of: {VALID_EMOTIONS}")
    update_memory(db, user_id, f"blocker.task.{task_id}", cause, confidence=0.9, source="user", commit=False)
    row = get_memory_entry(db, user_id, f"pattern.blocker.{cause}")
    try:
        count = int(row.value) if row else 0
    except (TypeError, ValueError):
        count = 0
    update_memory(db, user_id, f"pattern.blocker.{cause}", str(count + 1), confidence=0.8, source="buddy", commit=False)
    if commit:
        db.commit()



def task_confirmations(db: Session, user_id: str, task_id: int) -> list[tuple[str, datetime]]:
    """Each time a cause was confirmed for this task, and so counted in pattern.blocker.<cause>: (cause, when).
    The turn that counted it stores it as reasoning["saved_cause"]. Turns saved before that existed
    (2026-11-09) don't, so a task with none falls back to its blocker.task row: one confirmation."""
    found = []
    rows = db.execute(select(Message.reasoning, Message.created_at).where(
        Message.user_id == user_id, Message.task_id == task_id, Message.role == "assistant",
        Message.reasoning.is_not(None))).all()
    for raw, at in rows:
        try:
            cause = json.loads(raw).get("saved_cause")
        except (TypeError, ValueError, AttributeError):
            continue
        if cause:
            found.append((cause, as_utc(at)))
    if not found:
        row = get_memory_entry(db, user_id, f"blocker.task.{task_id}")
        if row is not None and row.value:
            found.append((row.value, as_utc(row.updated_at or row.created_at)))
    return found


def forget_task_causes(db: Session, user_id: str, task_id: int,
                       confirmations: list[tuple[str, datetime]]) -> None:
    """A task was deleted: forget its cause and take its confirmations back out of the pattern counts,
    so "everything about it is gone" is true. A count that reaches 0 is removed. Doesn't commit."""
    for cause, n in Counter(cause for cause, _ in confirmations).items():
        row = get_memory_entry(db, user_id, f"pattern.blocker.{cause}")
        if row is None:
            continue
        try:
            left = int(row.value) - n
        except (TypeError, ValueError):
            left = 0
        if left > 0:
            row.value = str(left)
        else:
            db.delete(row)
    db.execute(delete(Memory).where(Memory.user_id == user_id, Memory.key == f"blocker.task.{task_id}"))


# ── The person's name (onboarding screen 2, optional) ─────────────────────────
# Kept as a memory row so DELETE /me and the isolation rules cover it. It never reaches the writer as a raw row
# (agent._CAUSE_KEYS skips "profile."): one controlled line says how to use it (agent._name_line).

NAME_KEY = "profile.name"
NAME_MAX = 30


def clean_name(raw: Optional[str]) -> Optional[str]:
    """What they want to be called: one line, plain spaces, at most NAME_MAX characters. None when empty."""
    if not raw:
        return None
    name = " ".join("".join(ch for ch in raw if ch.isprintable()).split())[:NAME_MAX].strip()
    return name or None


def get_name(db: Session, user_id: str) -> Optional[str]:
    row = get_memory_entry(db, user_id, NAME_KEY)
    return clean_name(row.value) if row else None


def short_name(name: Optional[str]) -> Optional[str]:
    """For tight spots like a notification title: the first word, at most 15 characters."""
    return name.split()[0][:15] if name else None


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
    commit: bool = True,
) -> int:
    """Persist one turn to `messages`. role: 'user' | 'assistant'. Returns the new row's id."""
    message = Message(
        user_id=user_id, task_id=task_id, role=role, content=content,
        reasoning=json.dumps(reasoning, default=str) if reasoning else None,
    )
    db.add(message)
    if commit:
        db.commit()
        db.refresh(message)
    else:
        db.flush()
    return message.id


def get_conversation_history(
    db: Session, user_id: str, limit: int = 20, task_id: Optional[int] = None,
) -> list[dict]:
    """Return the last `limit` turns as {"role", "content"} dicts, oldest first."""
    q = select(Message).where(Message.user_id == user_id)
    if task_id is not None:
        q = q.where(Message.task_id == task_id)
    rows = db.execute(q.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)).scalars().all()
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
