# Task endpoints. Every query is scoped to the authenticated user.
#
#   POST /tasks  — create a task (title, optional due_date)
#   GET  /tasks  — list the caller's tasks, newest first (capped)

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import current_user
from db import get_db
from models import Task, User

router = APIRouter(prefix="/tasks", tags=["tasks"])

MAX_LIST = 100


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: Optional[datetime] = None


class TaskOut(BaseModel):
    id: int
    title: Optional[str]
    due_date: Optional[datetime]
    status: str
    task_state: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=TaskOut)
def create_task(payload: TaskCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    due = payload.due_date
    if due is not None and due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)  # naive input is treated as UTC
    task = Task(user_id=user.id, title=payload.title.strip(), due_date=due)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status: Optional[Literal["open", "done"]] = None,
    limit: int = Query(default=50, ge=1, le=MAX_LIST),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(Task).where(Task.user_id == user.id)
    if status:
        q = q.where(Task.status == status)
    return db.execute(q.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit)).scalars().all()
