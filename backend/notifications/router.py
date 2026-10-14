# FastAPI router for all notification-related endpoints.
#
# Production endpoints:
#   POST /devices/register  — upserts a user's Expo push token
#   POST /checkin/action    — handles notification button taps, drives the check-in stage machine
#
# Temporary dev/test endpoints (remove before production):
#   POST /tasks/create      — creates a bare task row for testing
#   POST /test/send-push    — triggers send_push directly via curl

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models import DeviceToken, EmotionLog, Task
from notifications.service import send_push

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterDeviceRequest(BaseModel):
    user_id: str
    expo_push_token: str  # Must be a valid ExponentPushToken[...] string.


class CheckinActionRequest(BaseModel):
    user_id: str
    task_id: int
    stage: Literal["task_state", "emotion", "chat_opt_in"]  # Which step of the check-in flow.
    value: str  # The button value the user tapped.


# ---------------------------------------------------------------------------
# POST /devices/register
# ---------------------------------------------------------------------------

@router.post("/devices/register", status_code=200)
def register_device(payload: RegisterDeviceRequest, db: Session = Depends(get_db)):
    # Upsert: update token if user already exists, otherwise insert a new row.
    row = db.query(DeviceToken).filter(DeviceToken.user_id == payload.user_id).first()
    if row:
        row.expo_push_token = payload.expo_push_token
    else:
        row = DeviceToken(user_id=payload.user_id, expo_push_token=payload.expo_push_token)
        db.add(row)
    db.commit()
    return {"status": "ok"}


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
                "actions": [
                    {"label": "😊 Good", "value": "good"},
                    {"label": "😐 Neutral", "value": "neutral"},
                    {"label": "😔 Low", "value": "low"},
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
async def checkin_action(payload: CheckinActionRequest, db: Session = Depends(get_db)):
    logger.info(
        "checkin_action user_id=%s task_id=%s stage=%s value=%s",
        payload.user_id,
        payload.task_id,
        payload.stage,
        payload.value,
    )

    task = db.query(Task).filter(Task.id == payload.task_id, Task.user_id == payload.user_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if payload.stage == "task_state":
        # Save what state the task is in, then prompt for emotion.
        task.task_state = payload.value
        db.commit()
        return _emotion_picker_response(task.id)

    if payload.stage == "emotion":
        # Create a new emotion log row, then prompt for chat opt-in.
        log = EmotionLog(user_id=payload.user_id, task_id=task.id, emotion=payload.value)
        db.add(log)
        db.commit()
        return _chat_opt_in_response(task.id)

    if payload.stage == "chat_opt_in":
        # Update the most recent emotion log with the chat opt-in decision.
        log = db.query(EmotionLog).filter(
            EmotionLog.task_id == task.id,
            EmotionLog.user_id == payload.user_id,
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


# ---------------------------------------------------------------------------
# POST /tasks/create  (temporary — remove before production)
# ---------------------------------------------------------------------------

@router.post("/tasks/create")
def create_task(user_id: str, db: Session = Depends(get_db)):
    # Creates a bare task row. Used during dev to get a task_id for testing /checkin/action.
    task = Task(user_id=user_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"task_id": task.id}


# ---------------------------------------------------------------------------
# POST /test/send-push  (temporary — remove before production)
# ---------------------------------------------------------------------------

@router.post("/test/send-push")
async def test_send_push(user_id: str, db: Session = Depends(get_db)):
    # Triggers send_push directly so you can verify FCM delivery end-to-end via curl.
    ticket = await send_push(
        db=db,
        user_id=user_id,
        title="Backend test 🚀",
        body="This came from your FastAPI send_push function!",
        data={"source": "test"},
    )
    return {"ticket": ticket}
