# Cron-triggered endpoints, called by an external scheduler (cron-job.org).
# Render free has no in-process scheduler and an ephemeral disk, so all scheduling lives outside the app.
#
#   POST /cron/checkins — gated by X-Cron-Secret; sends the daily check-in push to users with a
#                          due-soon/overdue task or an untouched one, skipping tasks nudged recently.

import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import Event, Task
from notifications.service import send_daily_checkin

router = APIRouter(prefix="/cron", tags=["cron"])
logger = logging.getLogger(__name__)

DUE_SOON_WINDOW = timedelta(hours=24)
UNTOUCHED_AFTER = timedelta(hours=24)
NUDGE_COOLDOWN = timedelta(hours=20)


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

    # Skip tasks nudged within the cooldown window.
    cutoff = now - NUDGE_COOLDOWN
    recent_ids = set(db.execute(
        select(Event.task_id).where(Event.type == "checkin_sent", Event.created_at >= cutoff)
    ).scalars().all())

    # One task per user: keep the first (most urgent, per ordering above) not recently nudged.
    picked: dict[str, Task] = {}
    for t in rows:
        if t.id in recent_ids or t.user_id in picked:
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
                result = await send_daily_checkin(db, task.user_id)
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
