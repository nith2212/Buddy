# Push notification service layer.
# send_push() — sends a single push via Expo's push API.
# send_daily_checkin() — scheduler entry point for the daily task-state notification.

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

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


def checkin_body(title: str | None) -> str:
    """Name the task: a check-in that doesn't say which task gets ignored (and Echo counts it as ignored).
    The title leaves our server via Expo's and Google's push services (developer OK, 2026-11-04)."""
    title = " ".join((title or "").split())
    if not title:
        return "How's your task going today?"
    if len(title) > TITLE_IN_BODY:
        title = title[:TITLE_IN_BODY - 1].rstrip() + "…"
    return f"How's “{title}” going today?"


async def send_daily_checkin(db: Session, user_id: str, task_id: int) -> dict | None:
    """
    Scheduler entry point. Sends the initial task-state check-in notification.
    Wire bandit logic here to choose the optimal time/content before calling send_push.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    return await send_push(
        db=db,
        user_id=user_id,
        title="Daily Check-in 🌟",
        body=checkin_body(task.title if task else None),
        data={
            "stage": "task_state",
            "task_id": task_id,
            "actions": [
                {"label": "Not started", "value": "not_started"},
                {"label": "In progress", "value": "in_progress"},
                {"label": "Done", "value": "done"},
            ],
        },
        category_id="task_state",
    )
