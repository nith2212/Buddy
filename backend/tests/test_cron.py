import os
from datetime import datetime, timedelta, timezone

import pytest

import models

INVITE = {"X-Invite-Code": "test-invite"}
CRON = {"X-Cron-Secret": "test-cron-secret"}
TOKEN = "ExponentPushToken[cccccccccccccccccccccc]"


@pytest.fixture(autouse=True)
def cron_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def test_cron_requires_secret(api):
    assert api.post("/cron/checkins").status_code == 401
    assert api.post("/cron/checkins", headers={"X-Cron-Secret": "wrong"}).status_code == 401


def test_cron_skips_user_with_no_device_token(api, db):
    _, h = register(api)
    api.post("/tasks", json={"title": "overdue", "due_date": "2020-01-01T00:00:00Z"}, headers=h)

    r = api.post("/cron/checkins", headers=CRON)
    assert r.status_code == 200
    assert r.json() == {"attempted": 1, "sent": 0, "skipped": 1, "failed": 0}
    assert db.query(models.Event).count() == 0


def test_cron_sends_and_records_event_for_due_task(api, db, monkeypatch):
    user_id, h = register(api)
    api.post("/devices/register", json={"expo_push_token": TOKEN}, headers=h)
    task_id = api.post(
        "/tasks", json={"title": "overdue", "due_date": "2020-01-01T00:00:00Z"}, headers=h
    ).json()["id"]

    async def fake_send(db_, uid):
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", fake_send)

    r = api.post("/cron/checkins", headers=CRON)
    assert r.json() == {"attempted": 1, "sent": 1, "skipped": 0, "failed": 0}

    event = db.query(models.Event).one()
    assert event.user_id == user_id and event.task_id == task_id and event.type == "checkin_sent"


def test_cron_does_not_renudge_within_cooldown(api, db, monkeypatch):
    user_id, h = register(api)
    api.post("/devices/register", json={"expo_push_token": TOKEN}, headers=h)
    task_id = api.post(
        "/tasks", json={"title": "overdue", "due_date": "2020-01-01T00:00:00Z"}, headers=h
    ).json()["id"]
    db.add(models.Event(user_id=user_id, task_id=task_id, type="checkin_sent"))
    db.commit()

    async def fake_send(db_, uid):
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", fake_send)

    r = api.post("/cron/checkins", headers=CRON)
    assert r.json() == {"attempted": 0, "sent": 0, "skipped": 0, "failed": 0}


def test_cron_ignores_untouched_task_with_no_due_date_before_window(api, db):
    _, h = register(api)
    api.post("/tasks", json={"title": "fresh, no due date"}, headers=h)

    r = api.post("/cron/checkins", headers=CRON)
    assert r.json()["attempted"] == 0


def test_cron_isolates_failure_per_user(api, db, monkeypatch):
    (_, h_a) = register(api)
    (_, h_b) = register(api)
    api.post("/devices/register", json={"expo_push_token": TOKEN}, headers=h_a)
    api.post("/devices/register", json={"expo_push_token": "ExponentPushToken[dddddddddddddddddddddd]"}, headers=h_b)
    api.post("/tasks", json={"title": "a", "due_date": "2020-01-01T00:00:00Z"}, headers=h_a)
    api.post("/tasks", json={"title": "b", "due_date": "2020-01-02T00:00:00Z"}, headers=h_b)

    calls = {"n": 0}

    async def flaky_send(db_, uid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("expo is down")
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", flaky_send)

    r = api.post("/cron/checkins", headers=CRON)
    body = r.json()
    assert body["attempted"] == 2
    assert body["sent"] == 1 and body["failed"] == 1
