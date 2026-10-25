# Work-state detection: task marked done -> trust it; a tap -> trust it;
# otherwise infer from repeated silence. No keyword scanning, no "postponed"
# counter — just what we actually collect. See CLAUDE.md for the full spec.
#
# classify() is a pure function (plain values in, hypotheses out) so the rules
# are easy to table-test without a database. detect_state() is the thin,
# DB-backed wrapper every real caller uses.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Event, Subtask, Task

# Each emotion button maps straight to the playbook state it's designed for.
# "avoidance" has no button — see notifications/router.py — so it never
# appears here; it's silence-inferred only (IGNORED_STREAK_THRESHOLD below).
EMOTION_TO_STATE = {
    "tired": "fatigue",
    "too_much": "overwhelm",
    "unclear": "ambiguity",
}

# How many check-ins in a row must go unanswered before we'll claim a state
# from silence alone. Below this, we don't have enough signal to say anything.
IGNORED_STREAK_THRESHOLD = 2


@dataclass(frozen=True)
class Hypothesis:
    state: str
    confidence: float


def classify(
    *,
    task_status: str,
    due_date: Optional[datetime],
    emotion_tap: Optional[str],
    checkin_sent_at: list[datetime],
    activity_at: list[datetime],
    now: datetime,
) -> list[Hypothesis]:
    """
    Returns a ranked (here: at most one) list of {state, confidence} hypotheses.
    Empty list means "no confident claim" — caller should still send the
    standard neutral check-in, just without a tailored state-based message.
    """
    if task_status == "done":
        return [Hypothesis("recovery", 0.9)]

    if emotion_tap in EMOTION_TO_STATE:
        return [Hypothesis(EMOTION_TO_STATE[emotion_tap], 0.8)]

    streak = _consecutive_ignored(checkin_sent_at, activity_at, now)
    if streak >= IGNORED_STREAK_THRESHOLD:
        return [Hypothesis("commitment_drift" if due_date else "avoidance", 0.5)]

    return []


def _consecutive_ignored(checkin_sent_at: list[datetime], activity_at: list[datetime], now: datetime) -> int:
    """
    Walk check-ins newest-first. A check-in counts as answered if any activity
    timestamp falls in (sent_at, next_sent_at] — next_sent_at is the following
    check-in's time, or `now` for the most recent one. Returns the length of
    the unbroken "ignored" streak counting back from the most recent check-in.
    """
    sent = sorted(checkin_sent_at)
    streak = 0
    for i in range(len(sent) - 1, -1, -1):
        window_start = sent[i]
        window_end = sent[i + 1] if i + 1 < len(sent) else now
        answered = any(window_start < a <= window_end for a in activity_at)
        if answered:
            break
        streak += 1
    return streak


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    SQLite drops timezone info on round-trip for DateTime(timezone=True) columns
    (Postgres/Neon doesn't) — every value we write is already UTC (models.utcnow()),
    so a naive value here only ever means "SQLite stripped it", never "not UTC".
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def detect_state(
    db: Session,
    user_id: str,
    task_id: int,
    emotion_tap: Optional[str] = None,
) -> list[Hypothesis]:
    """DB-backed entry point: gathers a task's real history and classifies it."""
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    ).scalar_one_or_none()
    if task is None:
        return []

    sent_at = list(db.execute(
        select(Event.created_at).where(
            Event.task_id == task_id, Event.user_id == user_id, Event.type == "checkin_sent"
        )
    ).scalars().all())

    subtask_updates = list(db.execute(
        select(Subtask.updated_at).where(Subtask.task_id == task_id, Subtask.user_id == user_id)
    ).scalars().all())

    return classify(
        task_status=task.status,
        due_date=as_utc(task.due_date),
        emotion_tap=emotion_tap,
        checkin_sent_at=[as_utc(d) for d in sent_at],
        activity_at=[as_utc(task.updated_at), *(as_utc(d) for d in subtask_updates)],
        now=datetime.now(timezone.utc),
    )
