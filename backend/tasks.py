# Task + subtask endpoints. Every query is scoped to the authenticated user.
#
#   POST   /tasks                              — create a task (title, optional due_date)
#   GET    /tasks                               — list the caller's tasks, newest first (capped)
#   PATCH  /tasks/{task_id}                      — edit title/due_date, or mark status
#   POST   /tasks/{task_id}/subtasks             — add a subtask
#   PATCH  /tasks/{task_id}/subtasks/{subtask_id} — edit title and/or toggle done
#   DELETE /tasks/{task_id}/subtasks/{subtask_id} — remove a subtask
#
# Marking a task done here (or via the check-in flow's task_state="done") always
# sets status/completed_at together and logs a "completed" event — state
# detection's "task marked done -> recovery" rule depends on status, not just
# task_state, so the two must never drift apart.

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import current_user, owned_or_404
from db import get_db
from models import Event, Subtask, Task, User

router = APIRouter(prefix="/tasks", tags=["tasks"])

MAX_LIST = 100
MAX_SUBTASKS_PER_TASK = 50


def _mark_done(task: Task, db: Session) -> None:
    """Shared by PATCH /tasks/{id} and the check-in flow's task_state="done" tap."""
    if task.status == "done":
        return
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    db.add(Event(user_id=task.user_id, task_id=task.id, type="completed", source="user"))


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    due_date: Optional[datetime] = None
    status: Optional[Literal["open", "done"]] = None


class SubtaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SubtaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    done: Optional[bool] = None


class SubtaskOut(BaseModel):
    id: int
    title: str
    done: bool
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: int
    title: Optional[str]
    due_date: Optional[datetime]
    status: str
    task_state: Optional[str]
    created_at: datetime
    subtasks: list[SubtaskOut] = []

    model_config = {"from_attributes": True}


def _normalize_due(due: Optional[datetime]) -> Optional[datetime]:
    if due is not None and due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)  # naive input is treated as UTC
    return due


@router.post("", status_code=201, response_model=TaskOut)
def create_task(payload: TaskCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = Task(user_id=user.id, title=payload.title.strip(), due_date=_normalize_due(payload.due_date))
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


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    task = owned_or_404(db, Task, task_id, user)

    if payload.title is not None:
        task.title = payload.title.strip()
    if "due_date" in payload.model_fields_set:
        task.due_date = _normalize_due(payload.due_date)
    if payload.status == "done":
        _mark_done(task, db)
    elif payload.status == "open":
        task.status, task.completed_at = "open", None

    db.commit()
    db.refresh(task)
    return task


# ── Subtasks ─────────────────────────────────────────────────────────────────

def _owned_subtask(db: Session, task_id: int, subtask_id: int, user: User) -> Subtask:
    row = db.execute(
        select(Subtask).where(
            Subtask.id == subtask_id, Subtask.task_id == task_id, Subtask.user_id == user.id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/{task_id}/subtasks", status_code=201, response_model=SubtaskOut)
def create_subtask(
    task_id: int,
    payload: SubtaskCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    owned_or_404(db, Task, task_id, user)  # 404s if the parent task isn't the caller's

    existing = len(db.execute(select(Subtask.id).where(Subtask.task_id == task_id)).all())
    if existing >= MAX_SUBTASKS_PER_TASK:
        raise HTTPException(status_code=422, detail=f"A task can have at most {MAX_SUBTASKS_PER_TASK} subtasks")

    subtask = Subtask(user_id=user.id, task_id=task_id, title=payload.title.strip(), position=existing)
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return subtask


@router.patch("/{task_id}/subtasks/{subtask_id}", response_model=SubtaskOut)
def update_subtask(
    task_id: int,
    subtask_id: int,
    payload: SubtaskUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    subtask = _owned_subtask(db, task_id, subtask_id, user)
    if payload.title is not None:
        subtask.title = payload.title.strip()
    if payload.done is not None:
        subtask.done = payload.done
    db.commit()
    db.refresh(subtask)
    return subtask


@router.delete("/{task_id}/subtasks/{subtask_id}", status_code=204)
def delete_subtask(
    task_id: int,
    subtask_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    subtask = _owned_subtask(db, task_id, subtask_id, user)
    db.delete(subtask)
    db.commit()
    return Response(status_code=204)
