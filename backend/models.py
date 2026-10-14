# SQLAlchemy ORM models for Buddy.
# Three tables: device_tokens, tasks, emotion_logs.

from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db import Base


class DeviceToken(Base):
    """Stores one Expo push token per user. Upserted on /devices/register."""
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    expo_push_token: Mapped[str] = mapped_column(String, nullable=False)
    # Tracks when the token was last updated — useful for pruning stale tokens.
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    """Represents a single daily check-in task for a user."""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Set when the user taps a task_state button (not_started / in_progress / done).
    task_state: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    emotion_logs: Mapped[list["EmotionLog"]] = relationship("EmotionLog", back_populates="task")


class EmotionLog(Base):
    """Records the emotion and chat opt-in response for a given task check-in."""
    __tablename__ = "emotion_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    # Set when the user taps an emotion button (good / neutral / low).
    emotion: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when the user responds to the chat opt-in prompt.
    chat_opt_in: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["Task"] = relationship("Task", back_populates="emotion_logs")
