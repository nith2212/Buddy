# DELETE /me — wipes every row belonging to the caller, then the user itself, in one transaction.
# POST /me/onboarding — saves (or replaces) the caller's first-launch answers, name included. Every answer is optional.

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import current_user
from brain import tools
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


# The questionnaire's choices, as the app sends them.
Days = Literal["school", "work", "own_projects", "mix"]
ClickTime = Literal["morning", "afternoon", "evening", "late_night", "changes"]
GetsInWay = Literal["unclear", "too_much", "afraid", "bored", "tired", "not_sure"]
_WAY_ORDER = ["unclear", "too_much", "afraid", "bored", "tired", "not_sure"]


class OnboardingAnswers(BaseModel):
    name: Optional[str] = Field(default=None, max_length=60)  # what Buddy calls them; cleaned and capped on save
    days: Optional[Days] = None
    click_time: Optional[ClickTime] = None
    gets_in_way: list[GetsInWay] = Field(default_factory=list, max_length=len(_WAY_ORDER))


@router.post("/me/onboarding", response_model=OnboardingAnswers)
def save_onboarding(answers: OnboardingAnswers, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What the person said about themselves: "you said", never a confirmed cause, so nothing here touches
    the cause memory. click_time sets when check-ins may go out (cron.CHECKIN_HOURS)."""
    row = db.execute(select(Onboarding).where(Onboarding.user_id == user.id)).scalar_one_or_none()
    if row is None:
        row = Onboarding(user_id=user.id)
        db.add(row)
    picked = set(answers.gets_in_way)
    row.days, row.click_time = answers.days, answers.click_time
    row.gets_in_way = ",".join(w for w in _WAY_ORDER if w in picked) or None
    # The name is a memory row (so Buddy can use it, sparingly); sent again without one, it's forgotten.
    name = tools.clean_name(answers.name)
    if name:
        tools.update_memory(db, user.id, tools.NAME_KEY, name, confidence=1.0, source="onboarding", commit=False)
    else:
        db.execute(delete(Memory).where(Memory.user_id == user.id, Memory.key == tools.NAME_KEY))
    db.commit()
    return OnboardingAnswers(name=name, days=row.days, click_time=row.click_time,
                             gets_in_way=row.gets_in_way.split(",") if row.gets_in_way else [])
