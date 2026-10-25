# FastAPI router for notification-related endpoints. Identity always comes from the Bearer token.
#
#   POST /devices/register  — registers the caller's Expo push token (one user may have several devices)
#   POST /checkin/action    — handles notification button taps, drives the check-in stage machine

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import current_user, owned_or_404
from db import get_db
from models import DeviceToken, EmotionLog, Task, User
from tasks import _mark_done

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterDeviceRequest(BaseModel):
    # Expo push tokens look like ExponentPushToken[...] (or ExpoPushToken[...]).
    expo_push_token: str = Field(pattern=r"^Expo(nent)?PushToken\[[^\]]+\]$")
    platform: Optional[str] = Field(default=None, max_length=20)


class CheckinActionRequest(BaseModel):
    task_id: int
    stage: Literal["task_state", "emotion", "chat_opt_in"]  # Which step of the check-in flow.
    value: str  # The button value the user tapped.


# ---------------------------------------------------------------------------
# POST /devices/register
# ---------------------------------------------------------------------------

@router.post("/devices/register", status_code=200)
def register_device(
    payload: RegisterDeviceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Upsert by token. A token already held by another account (e.g. phone re-installed under a new
    # identity) moves to the caller, so pushes follow whoever is actually using the device.
    for _ in range(2):
        row = db.execute(
            select(DeviceToken).where(DeviceToken.expo_push_token == payload.expo_push_token)
        ).scalar_one_or_none()
        if row:
            row.user_id = user.id
            row.platform = payload.platform or row.platform
        else:
            db.add(DeviceToken(user_id=user.id, expo_push_token=payload.expo_push_token, platform=payload.platform))
        try:
            db.commit()
            return {"status": "ok"}
        except IntegrityError:
            db.rollback()  # lost a race with a concurrent insert of the same token; retry as an update
    raise HTTPException(status_code=409, detail="Could not register device")


# ---------------------------------------------------------------------------
# POST /checkin/action
# ---------------------------------------------------------------------------

def _emotion_picker_response(task_id: int) -> dict[str, Any]:
    """Returns the notification payload the client should re-present after task_state is submitted."""
    return {
        "next_stage": "emotion",
        "task_id": task_id,
        "notification": {
            "title": "How are you feeling? 😊",
            "body": "Tap to log your emotion.",
            "data": {
                "stage": "emotion",
                "task_id": task_id,
                # Each value maps straight to a playbook state (fatigue/overwhelm/
                # ambiguity) — a direct self-report, trusted over any inference.
                # "avoidance" has no button on purpose: it's rarely self-admitted
                # in the moment, and gets inferred from repeated silence instead.
                "actions": [
                    {"label": "😴 Tired", "value": "tired"},
                    {"label": "😤 Too much", "value": "too_much"},
                    {"label": "🤷 Don't know where to start", "value": "unclear"},
                ],
            },
        },
    }


def _chat_opt_in_response(task_id: int) -> dict[str, Any]:
    """Returns the notification payload the client should re-present after emotion is submitted."""
    return {
        "next_stage": "chat_opt_in",
        "task_id": task_id,
        "notification": {
            "title": "Want to talk about it? 💬",
            "body": "Buddy is here if you'd like to chat.",
            "data": {
                "stage": "chat_opt_in",
                "task_id": task_id,
                "actions": [
                    {"label": "Yes, let's chat", "value": "yes"},
                    {"label": "No thanks", "value": "no"},
                ],
            },
        },
    }


@router.post("/checkin/action")
def checkin_action(
    payload: CheckinActionRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Plain `def`: all work here is synchronous DB access, so FastAPI runs it in the threadpool.
    logger.info(
        "checkin_action user_id=%s task_id=%s stage=%s value=%s",
        user.id,
        payload.task_id,
        payload.stage,
        payload.value,
    )

    task = owned_or_404(db, Task, payload.task_id, user)

    if payload.stage == "task_state":
        # Save what state the task is in, then prompt for emotion.
        task.task_state = payload.value
        if payload.value == "done":
            # Keep status/completed_at in lockstep with task_state — state detection's
            # "task marked done" rule reads status, and cron must stop nudging about it.
            _mark_done(task, db)
        db.commit()
        return _emotion_picker_response(task.id)

    if payload.stage == "emotion":
        # Create a new emotion log row, then prompt for chat opt-in.
        log = EmotionLog(user_id=user.id, task_id=task.id, emotion=payload.value)
        db.add(log)
        db.commit()
        return _chat_opt_in_response(task.id)

    if payload.stage == "chat_opt_in":
        # Update the most recent emotion log with the chat opt-in decision.
        log = db.query(EmotionLog).filter(
            EmotionLog.task_id == task.id,
            EmotionLog.user_id == user.id,
        ).order_by(EmotionLog.id.desc()).first()

        opted_in = payload.value == "yes"
        if log:
            log.chat_opt_in = opted_in
            db.commit()

        if opted_in:
            # Client should open a chat session.
            return {
                "next_stage": "chat",
                "task_id": task.id,
                "notification": {
                    "title": "Opening chat… 💬",
                    "body": "Buddy is ready to listen.",
                    "data": {"stage": "chat", "task_id": task.id},
                },
            }
        # User declined chat — check-in is complete.
        return {
            "next_stage": "done",
            "task_id": task.id,
            "notification": {
                "title": "All done for now ✅",
                "body": "Great job checking in today!",
                "data": {"stage": "done", "task_id": task.id},
            },
        }

    raise HTTPException(status_code=400, detail="Unknown stage")
