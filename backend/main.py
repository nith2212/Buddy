# Entry point for the Buddy FastAPI backend.
# Starts the app, creates all DB tables on startup, and mounts the routers.

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth import router as auth_router
from db import Base, engine
from me import router as me_router
from notifications.router import router as notifications_router
from tasks import router as tasks_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables defined in models.py if they don't exist yet.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Buddy API", lifespan=lifespan)

# Server-issued token auth: POST /auth/anonymous.
app.include_router(auth_router)

# Notification routes: /devices/register, /checkin/action.
app.include_router(notifications_router)

# Tasks (POST/GET /tasks) and account deletion (DELETE /me).
app.include_router(tasks_router)
app.include_router(me_router)
