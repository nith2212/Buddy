# Database setup: SQLAlchemy engine, session factory, declarative base, and FastAPI dependency.
# Defaults to SQLite locally. Set DATABASE_URL env var to switch to Postgres in production.

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./buddy.db")

engine = create_engine(
    DATABASE_URL,
    # SQLite requires this flag when used with FastAPI's threaded request handling.
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    # FastAPI dependency — yields a DB session per request and closes it after.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
