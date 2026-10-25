# Chat endpoints. Identity from the Bearer token; every task is ownership-checked.
#
#   POST /chat          — user sends a message about a task, Buddy replies
#   POST /initiate      — user opted into chat from a check-in; Buddy speaks first
#   GET  /chat/history  — the conversation for one task, oldest first (capped)

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import current_user, owned_or_404
from brain import tools
from brain.agent import run_turn
from db import get_db
from models import Task, User

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    task_id: int
    message: str = Field(min_length=1, max_length=1000, pattern=r"\S")


class InitiateRequest(BaseModel):
    task_id: int


class BuddyReply(BaseModel):
    reply: str
    state: Optional[str]
    intervention: Optional[str]


class ChatTurn(BaseModel):
    role: str
    content: str


@router.post("/chat", response_model=BuddyReply)
async def chat(payload: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = owned_or_404(db, Task, payload.task_id, user)
    return await run_turn(db, user.id, task, mode="chat", user_message=payload.message.strip())


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
