# Test setup. DATABASE_URL / INVITE_CODE must be set before db.py and auth.py are imported.

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="buddy-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["INVITE_CODE"] = "test-invite"

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import models  # noqa: E402
from auth import current_user, owned_or_404, router as auth_router  # noqa: E402
from db import Base, SessionLocal, engine, get_db  # noqa: E402

# Generic probe routes built only from current_user + owned_or_404: they exercise the
# scoping mechanism that real endpoints will use, without adding product endpoints in Step 1.
KINDS = {
    "task": (models.Task, "title"),
    "device_token": (models.DeviceToken, "expo_push_token"),
    "event": (models.Event, "type"),
    "memory": (models.Memory, "value"),
}


def build_probe_app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/probe/{kind}")
    def list_rows(kind: str, user=Depends(current_user), db: Session = Depends(get_db)):
        model, _ = KINDS[kind]
        rows = db.execute(select(model).where(model.user_id == user.id)).scalars().all()
        return [r.id for r in rows]

    @app.get("/probe/{kind}/{row_id}")
    def read_row(kind: str, row_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
        model, field = KINDS[kind]
        row = owned_or_404(db, model, row_id, user)
        return {"id": row.id, "value": getattr(row, field)}

    @app.patch("/probe/{kind}/{row_id}")
    def modify_row(kind: str, row_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
        model, field = KINDS[kind]
        row = owned_or_404(db, model, row_id, user)
        setattr(row, field, "modified")
        db.commit()
        return {"id": row.id}

    return app


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(build_probe_app())


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def api():
    """Client for the real app (all routers); tables come from the autouse fresh_db fixture."""
    from main import app
    return TestClient(app)
