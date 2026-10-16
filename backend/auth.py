# Server-issued bearer-token auth.
#
#   POST /auth/anonymous  — gated by X-Invite-Code; creates a user and returns {user_id, token} once.
#   current_user          — the ONLY source of identity; reads Authorization: Bearer <token>.
#   owned_or_404          — fetch a row by id scoped to the caller; other users' rows look nonexistent.

import hashlib
import hmac
import os
import secrets
from typing import Optional, Type, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from models import User

router = APIRouter(prefix="/auth", tags=["auth"])

T = TypeVar("T")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    user = db.execute(select(User).where(User.token_hash == hash_token(token.strip()))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return user


def owned_or_404(db: Session, model: Type[T], row_id: int, user: User) -> T:
    """Return model row `row_id` only if it belongs to `user`; otherwise 404 (never reveal existence)."""
    row = db.execute(
        select(model).where(model.id == row_id, model.user_id == user.id)  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/anonymous", status_code=201)
def create_anonymous_user(
    x_invite_code: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    expected = os.getenv("INVITE_CODE")
    if not expected:
        # Fail closed: without a configured code, nobody can register.
        raise HTTPException(status_code=503, detail="Registration is not configured")
    if not x_invite_code or not hmac.compare_digest(x_invite_code.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid invite code")

    token = secrets.token_urlsafe(32)
    user = User(token_hash=hash_token(token))
    db.add(user)
    db.commit()
    return {"user_id": user.id, "token": token}  # the raw token is shown only here
