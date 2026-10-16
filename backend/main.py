# Entry point for the Buddy FastAPI backend.
# Starts the app, creates all DB tables on startup, and mounts the notifications router.

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth import router as auth_router
from db import Base, engine
from notifications.router import router as notifications_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables defined in models.py if they don't exist yet.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Buddy API", lifespan=lifespan)

# Server-issued token auth: POST /auth/anonymous.
app.include_router(auth_router)

# All notification-related routes: /devices/register, /checkin/action, and temp test routes.
app.include_router(notifications_router)
