# SQLAlchemy ORM models for Buddy.
#
# Identity: `users` holds server-issued accounts (uuid id, sha256 of the bearer token).
# Every per-user table carries an indexed `user_id`; all access must be filtered by it.
#
# Check-in tables (device_tokens, tasks, emotion_logs) predate the users table and were extended in place.

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


def _ts(**kw):
    return mapped_column(DateTime(timezone=True), default=utcnow, **kw)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # sha256 hex of the bearer token; the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="UTC")
    created_at: Mapped[datetime] = _ts()


class DeviceToken(Base):
    """One Expo push token per device; a user may have several."""
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    expo_push_token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = _ts(onupdate=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # legacy bare tasks have none
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")  # open | done
    # Set when the user taps a task_state button (not_started / in_progress / done).
    task_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    emotion_logs: Mapped[list["EmotionLog"]] = relationship("EmotionLog", back_populates="task")
    subtasks: Mapped[list["Subtask"]] = relationship("Subtask", back_populates="task")


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=utcnow)

    task: Mapped["Task"] = relationship("Task", back_populates="subtasks")


class EmotionLog(Base):
    """Legacy check-in table; superseded by events(type='emotion') in a later step."""
    __tablename__ = "emotion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    emotion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chat_opt_in: Mapped[Optional[bool]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _ts()

    task: Mapped["Task"] = relationship("Task", back_populates="emotion_logs")


class Event(Base):
    """Single source of truth for everything observable (check-ins, completions, silence, echo runs)."""
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    detected_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="system")  # user | buddy | system
    created_at: Mapped[datetime] = _ts()


class Memory(Base):
    __tablename__ = "memory"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_memory_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    source: Mapped[str] = mapped_column(String, nullable=False, default="buddy")  # onboarding | buddy | echo
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(onupdate=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON, assistant turns only
    created_at: Mapped[datetime] = _ts()


class Onboarding(Base):
    __tablename__ = "onboarding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True)
    preferred_work_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    work_session_style: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    procrastination_style: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notification_opted_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _ts()
