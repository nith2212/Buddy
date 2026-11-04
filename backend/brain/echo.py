# Echo, step E1: a weekly count of each user's week, for Buddy only (PIVOTS.md "Echo, in steps").
#
# - Counted by code, no model call: nothing can be invented, and it spends no Groq quota.
# - For Buddy, never for the user: no push, no user-facing text. Buddy gets at most one line, and
#   that line tells it to be gentler. It never quotes these facts (owner decision 2026-11-04).
# - Runs for anyone with a task, including tasks they ignore (ignoring is data). No tasks: skipped.
# - Saved as memory rows echo.week.<week end date> (source "echo"), the last KEEP_WEEKS kept.
#   DELETE /me wipes them with the rest of memory.
#
# The week ends Sunday 23:00 India time. cron-job.org calls POST /cron/echo then (cron.py).

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from brain.state_detection import as_utc
from models import EmotionLog, Event, Memory, Message, Subtask, Task

WEEK_TZ = ZoneInfo("Asia/Kolkata")
WEEK_END = time(23, 0)          # Sunday 23:00 in WEEK_TZ
IGNORE_WINDOW = timedelta(hours=12)  # a check-in with no tap or chat on that task within this is "ignored"
KEEP_WEEKS = 8
KEY_PREFIX = "echo.week."

# When Buddy gets the "be gentle" line (any one is enough)
AWAY_DAYS = 5                   # task untouched this many days
AWAY_IGNORED = 2                # check-ins ignored this week
ECHO_FRESH = timedelta(days=8)  # older facts are stale: no line


def week_window(now: datetime) -> tuple[datetime, datetime]:
    """(start, end) in UTC of the last week that has ended by `now`. Weeks end Sunday 23:00 India time."""
    local = as_utc(now).astimezone(WEEK_TZ)
    days_back = (local.weekday() - 6) % 7  # Monday=0 ... Sunday=6
    end = datetime.combine(local.date() - timedelta(days=days_back), WEEK_END, tzinfo=WEEK_TZ)
    if end > local:
        end -= timedelta(days=7)
    end = end.astimezone(timezone.utc)
    return end - timedelta(days=7), end


def week_id(end: datetime) -> str:
    return as_utc(end).astimezone(WEEK_TZ).date().isoformat()


def _in(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    dt = as_utc(dt)
    return dt is not None and start <= dt < end


def _cause_totals(db: Session, user_id: str) -> dict[str, int]:
    totals = {}
    for row in db.execute(select(Memory).where(Memory.user_id == user_id,
                                               Memory.key.startswith("pattern.blocker."))).scalars():
        try:
            totals[row.key.removeprefix("pattern.blocker.")] = int(row.value)
        except (TypeError, ValueError):
            pass
    return totals


def _previous(db: Session, user_id: str, before: str) -> Optional[dict]:
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    older = sorted((r for r in rows if r.key.removeprefix(KEY_PREFIX) < before), key=lambda r: r.key)
    if not older:
        return None
    try:
        return json.loads(older[-1].value)
    except (TypeError, ValueError):
        return None


def week_facts(db: Session, user_id: str, start: datetime, end: datetime) -> Optional[dict]:
    """Everything Echo counts for one user's week, or None when they have no tasks to count."""
    tasks = db.execute(select(Task).where(Task.user_id == user_id)).scalars().all()
    tasks = [t for t in tasks if as_utc(t.created_at) < end
             and (t.status == "open" or _in(t.completed_at, start, end))]
    if not tasks:
        return None
    ids = [t.id for t in tasks]

    # Every moment the user touched a task (their own actions only, never Buddy's or the scheduler's).
    touches: dict[int, list[datetime]] = {t.id: [as_utc(t.created_at)] for t in tasks}
    for t in tasks:
        if t.updated_at:
            touches[t.id].append(as_utc(t.updated_at))
    for s in db.execute(select(Subtask).where(Subtask.user_id == user_id, Subtask.task_id.in_(ids))).scalars():
        touches[s.task_id].append(as_utc(s.updated_at or s.created_at))
    for m in db.execute(select(Message).where(Message.user_id == user_id, Message.task_id.in_(ids),
                                              Message.role == "user")).scalars():
        touches[m.task_id].append(as_utc(m.created_at))
    taps = db.execute(select(EmotionLog).where(EmotionLog.user_id == user_id, EmotionLog.task_id.in_(ids))
                      ).scalars().all()
    for e in taps:
        touches[e.task_id].append(as_utc(e.created_at))

    events = db.execute(select(Event).where(Event.user_id == user_id, Event.task_id.in_(ids),
                                            or_(Event.type == "checkin_sent", Event.type == "postponed"))
                        ).scalars().all()

    per_task = []
    for t in tasks:
        if t.status != "open":
            continue
        seen = [d for d in touches[t.id] if d < end]
        sent = [as_utc(e.created_at) for e in events if e.task_id == t.id and e.type == "checkin_sent"
                and _in(e.created_at, start, end)]
        # judged only once the window has passed by the end of the week
        judged = [s for s in sent if s + IGNORE_WINDOW <= end]
        ignored = sum(1 for s in judged if not any(s <= d <= s + IGNORE_WINDOW for d in seen))
        per_task.append({
            "id": t.id,
            "days_untouched": (end - max(seen)).days if seen else None,
            "checkins_sent": len(sent),
            "checkins_ignored": ignored,
            "postponed": sum(1 for e in events if e.task_id == t.id and e.type == "postponed"
                             and _in(e.created_at, start, end)),
        })

    tapped: dict[str, int] = {}
    for e in taps:
        if e.emotion and _in(e.created_at, start, end):
            tapped[e.emotion] = tapped.get(e.emotion, 0) + 1

    totals = _cause_totals(db, user_id)
    prev = _previous(db, user_id, week_id(end))
    if prev is not None:
        before = prev.get("cause_totals", {})
        confirmed = {c: n - before.get(c, 0) for c, n in totals.items() if n - before.get(c, 0) > 0}
    else:
        # first Echo for this user: count the per-task causes confirmed during the week
        confirmed = {}
        for row in db.execute(select(Memory).where(Memory.user_id == user_id,
                                                   Memory.key.startswith("blocker.task."))).scalars():
            if _in(row.updated_at, start, end) and row.value:
                confirmed[row.value] = confirmed.get(row.value, 0) + 1

    steps_done = db.execute(select(Subtask).where(Subtask.user_id == user_id, Subtask.task_id.in_(ids),
                                                  Subtask.done.is_(True))).scalars().all()
    return {
        "week": week_id(end),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "first_week": prev is None,
        "causes_confirmed": confirmed,
        "cause_totals": totals,
        "reasons_tapped": tapped,
        "tasks_finished": sum(1 for t in tasks if _in(t.completed_at, start, end)),
        "steps_done": sum(1 for s in steps_done if _in(s.updated_at, start, end)),
        "open_tasks": per_task,
    }


def run_echo(db: Session, user_id: str, now: datetime) -> str:
    """Count and save one user's last finished week. Returns 'saved', 'already_done' or 'no_tasks'."""
    start, end = week_window(now)
    key = KEY_PREFIX + week_id(end)
    if db.execute(select(Memory.id).where(Memory.user_id == user_id, Memory.key == key)).first():
        return "already_done"
    facts = week_facts(db, user_id, start, end)
    if facts is None:
        return "no_tasks"
    db.add(Memory(user_id=user_id, key=key, value=json.dumps(facts), confidence=1.0, source="echo"))
    db.flush()  # so the new week counts toward KEEP_WEEKS below
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    for old in sorted(rows, key=lambda r: r.key, reverse=True)[KEEP_WEEKS:]:
        db.delete(old)
    db.commit()
    return "saved"


def latest(db: Session, user_id: str, now: datetime) -> Optional[dict]:
    """The newest saved week, if it's fresh enough to use."""
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    if not rows:
        return None
    try:
        facts = json.loads(max(rows, key=lambda r: r.key).value)
        if as_utc(now) - datetime.fromisoformat(facts["end"]) > ECHO_FRESH:
            return None
        return facts
    except (TypeError, ValueError, KeyError):
        return None


def buddy_line(facts: Optional[dict], task_id: int) -> Optional[str]:
    """The one line Buddy may get from Echo: a cue to go gentle on a task they've been away from.
    Never a number, never the facts themselves: Buddy must not say them."""
    if not facts:
        return None
    task = next((t for t in facts.get("open_tasks", []) if t.get("id") == task_id), None)
    if not task:
        return None
    away = (task.get("days_untouched") or 0) >= AWAY_DAYS or task.get("checkins_ignored", 0) >= AWAY_IGNORED
    if not away:
        return None
    return ("Context, never mention it: they've been away from this task for a while. Be extra gentle and "
            "low-pressure, and glad they're here. Don't bring up time away, check-ins, or anything you know "
            "about their week.")
