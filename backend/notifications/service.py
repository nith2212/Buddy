# Push notification service layer.
# send_push() — sends a single push via Expo's push API.
# send_daily_checkin() — scheduler entry point for the daily task-state notification.

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from models import DeviceToken

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

logger = logging.getLogger(__name__)


async def send_push(
    db: Session,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
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


async def send_daily_checkin(db: Session, user_id: str) -> dict | None:
    """
    Scheduler entry point. Sends the initial task-state check-in notification.
    Wire bandit logic here to choose the optimal time/content before calling send_push.
    """
    return await send_push(
        db=db,
        user_id=user_id,
        title="Daily Check-in 🌟",
        body="How's your task going today?",
        data={
            "stage": "task_state",
            "actions": [
                {"label": "Not started", "value": "not_started"},
                {"label": "In progress", "value": "in_progress"},
                {"label": "Done", "value": "done"},
            ],
        },
    )
