# Cron-triggered endpoints, called by an external scheduler (cron-job.org).
# Render free has no in-process scheduler and an ephemeral disk, so all scheduling lives outside the app.
#
#   POST /cron/checkins — gated by X-Cron-Secret; runs hourly. Sends the daily check-in push to users with a
#                          due-soon/overdue task or an untouched one, at most once a day per person, and only
#                          inside the hours their onboarding answer picked (CHECKIN_HOURS).
#   POST /cron/echo     — gated by X-Cron-Secret; weekly (Sunday 23:00 India time): Echo counts each
#                          user's finished week for Buddy (brain/echo.py). Safe to call twice.

import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from brain import echo
from db import SessionLocal
from models import Event, Onboarding, Task, User
from notifications.service import send_daily_checkin

router = APIRouter(prefix="/cron", tags=["cron"])
logger = logging.getLogger(__name__)

DUE_SOON_WINDOW = timedelta(hours=24)
UNTOUCHED_AFTER = timedelta(hours=24)
NUDGE_COOLDOWN = timedelta(hours=20)

# When a check-in may go out, from "When do things usually click for you?" (onboarding). The cron runs at
# the top of every hour; these are the hours, India time, whose run may nudge that person.
CHECKIN_TZ = ZoneInfo("Asia/Kolkata")  # testers are in India; per-person time zones aren't stored yet
CHECKIN_HOURS = {
    "morning": range(7, 12),       # 07:00 … 11:00
    "afternoon": range(12, 17),    # 12:00 … 16:00
    "evening": range(17, 22),      # 17:00 … 21:00
    "late_night": range(21, 24),   # 21:00 … 23:00
}
DEFAULT_HOURS = range(9, 22)       # "It changes", no answer, or no onboarding: 09:00 … 21:00, as before


def in_checkin_window(click_time: Optional[str], now: datetime) -> bool:
    return now.astimezone(CHECKIN_TZ).hour in CHECKIN_HOURS.get(click_time, DEFAULT_HOURS)


def require_cron_secret(x_cron_secret: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("CRON_SECRET")
    if not expected or not x_cron_secret or not hmac.compare_digest(x_cron_secret.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid cron secret")


def _eligible_tasks(db: Session, now: datetime) -> list[Task]:
    due_or_untouched = (
        (Task.due_date.is_not(None)) & (Task.due_date <= now + DUE_SOON_WINDOW)
    ) | (
        (Task.task_state.is_(None)) & (Task.created_at <= now - UNTOUCHED_AFTER)
    )
    rows = db.execute(
        select(Task)
        .where(Task.status == "open", due_or_untouched)
        .order_by(Task.user_id, Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.asc())
    ).scalars().all()

    # At most one check-in per person per day: skip anyone nudged within the cooldown, whichever task it
    # was about. (A per-task wait let someone with 3 waiting tasks get 3 pings in 3 hours.)
    cutoff = now - NUDGE_COOLDOWN
    recent_users = set(db.execute(
        select(Event.user_id).where(Event.type == "checkin_sent", Event.created_at >= cutoff)
    ).scalars().all())

    # Only inside each person's hours (their onboarding answer, or the default).
    click_times = dict(db.execute(
        select(Onboarding.user_id, Onboarding.click_time).where(Onboarding.user_id.in_({t.user_id for t in rows}))
    ).all()) if rows else {}

    # One task per person: keep their first (most urgent, per ordering above).
    picked: dict[str, Task] = {}
    for t in rows:
        if t.user_id in recent_users or t.user_id in picked:
            continue
        if not in_checkin_window(click_times.get(t.user_id), now):
            continue
        picked[t.user_id] = t
    return list(picked.values())


@router.post("/checkins")
async def cron_checkins(_: None = Depends(require_cron_secret)):
    db = SessionLocal()
    sent, skipped, failed = [], [], []
    try:
        tasks = _eligible_tasks(db, datetime.now(timezone.utc))
        for task in tasks:
            try:
                result = await send_daily_checkin(db, task.user_id, task.id)
            except Exception:
                logger.exception("cron checkin failed for user_id=%s task_id=%s", task.user_id, task.id)
                failed.append(task.id)
                continue
            if result is None:
                # No device token registered for this user — nothing was sent, don't record a nudge.
                skipped.append(task.id)
                continue
            db.add(Event(user_id=task.user_id, task_id=task.id, type="checkin_sent", source="system"))
            db.commit()
            sent.append(task.id)
    finally:
        db.close()

    return {"attempted": len(sent) + len(skipped) + len(failed), "sent": len(sent), "skipped": len(skipped), "failed": len(failed)}


@router.post("/echo")
def cron_echo(_: None = Depends(require_cron_secret)):
    # Plain code, no model call, so it's quick and holds no session across an LLM call.
    db = SessionLocal()
    counts = {"saved": 0, "already_done": 0, "no_tasks": 0, "failed": 0}
    now = datetime.now(timezone.utc)
    try:
        for user_id in db.execute(select(User.id)).scalars().all():
            try:
                counts[echo.run_echo(db, user_id, now)] += 1
            except Exception:
                db.rollback()
                logger.exception("cron echo failed for user_id=%s", user_id)
                counts["failed"] += 1
    finally:
        db.close()
    _, end = echo.week_window(now)
    return {"week": echo.week_id(end), **counts}
