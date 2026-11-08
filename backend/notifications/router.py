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
from brain.agent import run_turn
from db import get_db
from models import DeviceToken, EmotionLog, Task, User
from notifications.service import quoted_title
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
    # Which step of the check-in flow. "emotion_more" is the second set of reasons, behind "Something else".
    stage: Literal["task_state", "emotion", "emotion_more", "chat_opt_in"]
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

# The developer's wording (docs/notification_wording.md, approved 2026-11-08). Notifications sit on a public
# lock screen, so they hint at a cause and never name it ("you're scared"). No guilt, no therapy phrases.
# Button labels mirror the app's registered categories (src/lib/checkin-categories.ts), which draw them.

# Each reason value maps straight to a playbook state: a direct self-report, trusted over any inference.
# Android caps notification buttons at 3, so the 5 reasons come in two steps: the third button of the first
# set, "Something else" (value "more"), opens the second set. Anything outside the 5: tapping the notification
# itself opens the chat, where Buddy asks in the user's own words. "avoidance" has no button on purpose: it's
# rarely self-admitted in the moment, and gets inferred from repeated silence instead.
FIRST_REASONS = [
    {"label": "😴 Tired", "value": "tired"},
    {"label": "🤷 Where do I start?", "value": "unclear"},
    {"label": "💭 Something else", "value": "more"},
]
MORE_REASONS = [
    {"label": "😤 Too much", "value": "too_much"},
    {"label": "😬 Scared it's not good", "value": "afraid"},
    {"label": "🥱 Boring", "value": "bored"},
]
AFTER_STATUS = {
    "not_started": ("Okay! What's in the way?", "Pick whichever feels closest."),
    "in_progress": ("Ooh, you started! 🙌", "Anything slowing you down?"),
}
# One chat offer per reason. {task} is the quoted task title.
CHAT_OFFERS = {
    "tired": ("Tired, huh? 💛", "Want to chat about it, or rest for now?"),
    "too_much": ("Let's make it smaller", "Want to shrink {task} down together?"),
    "unclear": ("Let's find the start", "Want to figure out the first bit together?"),
    "afraid": ("A rough start counts 💛", "Want to find a no-pressure first step together?"),
    "bored": ("Let's make it less of a drag", "Want to find an easier way into {task} together?"),
}
DEFAULT_OFFER = ("Want to chat about it? 💬", "We can figure out {task} together.")
CLOSING_TITLE = "Got it! 💛"


def _name(task: Task) -> str:
    return quoted_title(task.title) or "your task"


def _reason_picker_response(task: Task, status: str) -> dict[str, Any]:
    """After "Not yet" or "On it": what's in the way? The first set of reasons."""
    title, body = AFTER_STATUS.get(status, AFTER_STATUS["not_started"])
    return {
        "next_stage": "emotion",
        "task_id": task.id,
        "notification": {
            "title": title,
            "body": body,
            "data": {"stage": "emotion", "task_id": task.id, "actions": FIRST_REASONS},
        },
    }


def _more_reasons_response(task: Task) -> dict[str, Any]:
    """After "Something else": the other three reasons."""
    return {
        "next_stage": "emotion_more",
        "task_id": task.id,
        "notification": {
            "title": "Okay, which one?",
            "body": "Pick the closest, or tap here to tell Buddy in your own words.",
            "data": {"stage": "emotion_more", "task_id": task.id, "actions": MORE_REASONS},
        },
    }


def _done_response(task: Task) -> dict[str, Any]:
    """They finished: celebrate it and end the check-in. No buttons, and no "what's in the way?"."""
    return {
        "next_stage": "done",
        "task_id": task.id,
        "notification": {
            "title": "Yay, you did it! 🎉",
            "body": f"{_name(task)} is done. That's one off your plate!",
            "data": {"stage": "done", "task_id": task.id},
        },
    }


def _chat_opt_in_response(task: Task, reason: str) -> dict[str, Any]:
    """After a reason: offer to figure it out together, worded for that reason."""
    title, body = CHAT_OFFERS.get(reason, DEFAULT_OFFER)
    return {
        "next_stage": "chat_opt_in",
        "task_id": task.id,
        "notification": {
            "title": title,
            "body": body.format(task=_name(task)),
            "data": {
                "stage": "chat_opt_in",
                "task_id": task.id,
                "actions": [
                    {"label": "Let's chat", "value": "yes"},
                    {"label": "Not now", "value": "no"},
                ],
            },
        },
    }


@router.post("/checkin/action")
async def checkin_action(
    payload: CheckinActionRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # async: the declined-chat branch awaits a Groq call for the tailored closing note.
    logger.info(
        "checkin_action user_id=%s task_id=%s stage=%s value=%s",
        user.id,
        payload.task_id,
        payload.stage,
        payload.value,
    )

    task = owned_or_404(db, Task, payload.task_id, user)

    if payload.stage == "task_state":
        # Save what state the task is in, then ask what's in the way (or celebrate, if it's done).
        task.task_state = payload.value
        if payload.value == "done":
            # Keep status/completed_at in lockstep with task_state — state detection's
            # "task marked done" rule reads status, and cron must stop nudging about it.
            _mark_done(task, db)
            db.commit()
            return _done_response(task)
        db.commit()
        return _reason_picker_response(task, payload.value)

    if payload.stage in ("emotion", "emotion_more"):
        if payload.value == "more":
            # "Something else" isn't a reason: show the other three, log nothing yet.
            return _more_reasons_response(task)
        # Create a new emotion log row, then prompt for chat opt-in.
        log = EmotionLog(user_id=user.id, task_id=task.id, emotion=payload.value)
        db.add(log)
        db.commit()
        return _chat_opt_in_response(task, payload.value)

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
            # The app opens the chat itself on "Let's chat", so there's no notification to show.
            return {"next_stage": "chat", "task_id": task.id}
        # User declined chat: the brain still runs and writes ONE tailored closing note.
        closing = await run_turn(db, user.id, task, mode="closing")
        return {
            "next_stage": "done",
            "task_id": task.id,
            "notification": {
                "title": CLOSING_TITLE,
                "body": closing["reply"],
                "data": {"stage": "done", "task_id": task.id},
            },
        }

    raise HTTPException(status_code=400, detail="Unknown stage")
