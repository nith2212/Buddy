# Chat endpoints. Identity from the Bearer token; every task is ownership-checked.
#
#   POST /chat          — user sends a message about a task (or answers "mark it done?"), Buddy replies
#   POST /initiate      — user opted into chat from a check-in; Buddy speaks first
#   GET  /chat/history  — the conversation for one task, oldest first (capped)

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from auth import current_user, owned_or_404
from brain import tools
from brain.agent import answer_done_offer, run_turn
from db import get_db
from models import EmotionLog, Task, User

router = APIRouter(tags=["chat"])


# The rough reasons a user can tap (keys of brain.state_detection.EMOTION_TO_STATE).
Reason = Literal["tired", "too_much", "unclear", "afraid", "bored"]


class ChatRequest(BaseModel):
    task_id: int
    # A typed message, a tapped `reason`, or both. A bare reason tap has no message:
    # Buddy speaks first, so nothing is saved as if the user had typed it.
    message: Optional[str] = Field(default=None, min_length=1, max_length=1000, pattern=r"\S")
    reason: Optional[Reason] = None
    # A tap on "Yes, mark it done" (true) / "Not yet" (false) under Buddy's "Want me to mark it done?".
    # Sent on its own, never in-band in the message text.
    mark_done: Optional[bool] = None

    @model_validator(mode="after")
    def _needs_message_or_reason(self):
        if self.mark_done is not None:
            if self.message is not None or self.reason is not None:
                raise ValueError("send mark_done on its own")
        elif self.message is None and self.reason is None:
            raise ValueError("send a message, a reason, or both")
        return self


class InitiateRequest(BaseModel):
    task_id: int


class BuddyReply(BaseModel):
    reply: str
    state: Optional[str]
    intervention: Optional[str]
    ask_reason: bool = False  # Buddy just asked what's in the way: the app shows the reason chips
    offer_done: bool = False  # Buddy asked "Want me to mark it done?": the app shows Yes / Not yet
    task_status: Optional[str] = None  # set when this turn changed (or confirmed) the task's status


class ChatTurn(BaseModel):
    role: str
    content: str


@router.post("/chat", response_model=BuddyReply)
async def chat(payload: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_or_404(db, Task, payload.task_id, user)
    if payload.mark_done is not None:
        return answer_done_offer(db, user.id, task, payload.mark_done)
    if payload.reason:
        # Same record the notification's emotion button writes, so state detection reads it as a tap.
        db.add(EmotionLog(user_id=user.id, task_id=task.id, emotion=payload.reason))
        db.commit()
    message = payload.message.strip() if payload.message else None
    return await run_turn(db, user.id, task, mode="chat" if message else "initiate", user_message=message)


@router.post("/initiate", response_model=BuddyReply)
async def initiate(payload: InitiateRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_or_404(db, Task, payload.task_id, user)
    return await run_turn(db, user.id, task, mode="initiate")


@router.get("/chat/history", response_model=list[ChatTurn])
def chat_history(
    task_id: int,
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    owned_or_404(db, Task, task_id, user)
    return tools.get_conversation_history(db, user.id, limit=limit, task_id=task_id)
