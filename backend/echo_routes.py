# The user's Echo page: GET /echo/week. Read-only and scoped to the caller (identity from the token only).
# What it may show is decided in brain/echo.py ("The user's Echo page"): kind, earned things only.

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import current_user
from brain import echo
from db import get_db
from models import User

router = APIRouter(prefix="/echo", tags=["echo"])


@router.get("/week")
def echo_week(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return echo.this_week(db, user.id, datetime.now(timezone.utc))
