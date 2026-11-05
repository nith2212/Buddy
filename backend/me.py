# DELETE /me — wipes every row belonging to the caller, then the user itself, in one transaction.

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from auth import current_user
from db import get_db
from models import (
    DeviceToken, EmotionLog, Event, Memory, Message, Onboarding, Subtask, Task, User,
)

router = APIRouter(tags=["me"])

# Children before parents so foreign keys hold (tasks are referenced by subtasks, events, messages, emotion_logs).
_USER_TABLES = [EmotionLog, Subtask, Event, Message, Memory, Onboarding, DeviceToken, Task]


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for model in _USER_TABLES:
        db.execute(delete(model).where(model.user_id == user.id))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    return Response(status_code=204)
