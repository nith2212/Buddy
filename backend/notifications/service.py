# Push notification service layer.
# send_push() — sends a single push via Expo's push API.
# send_daily_checkin() — scheduler entry point for the daily task-state notification.

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from brain import tools
from brain.state_detection import as_utc
from models import DeviceToken, Task

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

logger = logging.getLogger(__name__)


async def send_push(
    db: Session,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    category_id: str | None = None,
) -> dict | None:
    # Look up the user's registered Expo push token.
    row = db.query(DeviceToken).filter(DeviceToken.user_id == user_id).first()
    if not row:
        logger.warning("send_push: no token for user_id=%s", user_id)
        return None

    payload = {
        "to": row.expo_push_token,
        "title": title,
        "body": body,
        "data": data or {},
        "channelId": "buddy-checkin",  # Android notification channel.
        "priority": "high",            # Bypasses Doze mode on Android.
    }
    if category_id:
        # Must match a category registered client-side via setNotificationCategoryAsync —
        # this is what makes Android render the action buttons at all.
        payload["categoryId"] = category_id

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            EXPO_PUSH_URL,
            json=payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        result = resp.json()

    ticket = result.get("data", {})

    # Log DeviceNotRegistered errors so dead tokens can be pruned later.
    if ticket.get("status") == "error":
        details = ticket.get("details", {})
        if details.get("error") == "DeviceNotRegistered":
            logger.error(
                "DeviceNotRegistered for user_id=%s token=%s — mark for pruning",
                user_id,
                row.expo_push_token,
            )
    return ticket


TITLE_IN_BODY = 60  # characters of the task title shown in a check-in
DUE_SOON = timedelta(hours=24)

# The developer's wording (docs/notification_wording.md, approved 2026-11-08). Each line asks where they are,
# because the buttons (Not yet / On it / Done!) answer that. Only true things: "due soon" means due within a
# day, and nothing ever counts days or ignored check-ins (no guilt). {task} is the quoted task title.
CHECKIN_LINES: dict[str, tuple[str, list[str]]] = {
    "past_due": ("Hey! 🌟", [
        "{task} went past its date. Where are you at with it?",
        "Checking in on {task}. It's past its date, how's it looking?",
    ]),
    "due_soon": ("Heads up 🌟", [
        "{task} is due soon. How's it going?",
        "{task} is coming up! Where are you at with it?",
    ]),
    "waiting": ("Hey! 🌟", [
        "{task} has been waiting a bit. How's it going?",
        "Checking in on {task}! Where are you at?",
        "How's {task} coming along?",
    ]),
}


def quoted_title(title: str | None) -> str | None:
    """The task title in curly quotes, cut to fit a notification; None if there's no title.
    Titles leave our server via Expo's and Google's push services (developer OK, 2026-11-04)."""
    title = " ".join((title or "").split())
    if not title:
        return None
    if len(title) > TITLE_IN_BODY:
        title = title[:TITLE_IN_BODY - 1].rstrip() + "…"
    return f"“{title}”"


def checkin_situation(task: Task, now: datetime) -> str:
    due = as_utc(task.due_date)
    if due is not None and due < now:
        return "past_due"
    if due is not None and due <= now + DUE_SOON:
        return "due_soon"
    return "waiting"


# With their name (onboarding), the title greets them by it: "Hey Nithya! 🌟".
NAMED_TITLES = {"past_due": "Hey {name}! 🌟", "due_soon": "Heads up, {name} 🌟", "waiting": "Hey {name}! 🌟"}


def checkin_message(task: Task | None, now: datetime, person: str | None = None) -> tuple[str, str]:
    """Title and body of the daily check-in. It names the task: a check-in that doesn't say which task gets
    ignored (and Echo counts it as ignored). Variants take turns by day, so the line changes day to day.
    `person` is their name, if they gave one: only its first word goes in the title, to keep it short."""
    first = tools.short_name(person)
    name = quoted_title(task.title if task else None)
    if task is None or name is None:
        return (f"Hey {first}! 🌟" if first else "Hey! 🌟"), "How's your task going today?"
    situation = checkin_situation(task, now)
    title, bodies = CHECKIN_LINES[situation]
    if first:
        title = NAMED_TITLES[situation].format(name=first)
    return title, bodies[now.date().toordinal() % len(bodies)].format(task=name)


async def send_daily_checkin(db: Session, user_id: str, task_id: int, now: datetime | None = None) -> dict | None:
    """
    Scheduler entry point. Sends the initial task-state check-in notification.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    title, body = checkin_message(task, now or datetime.now(timezone.utc), tools.get_name(db, user_id))
    return await send_push(
        db=db,
        user_id=user_id,
        title=title,
        body=body,
        data={
            "stage": "task_state",
            "task_id": task_id,
            # Labels mirror the app's registered category (src/lib/checkin-categories.ts), which draws them.
            "actions": [
                {"label": "Not yet", "value": "not_started"},
                {"label": "On it", "value": "in_progress"},
                {"label": "Done!", "value": "done"},
            ],
        },
        category_id="task_state",
    )
