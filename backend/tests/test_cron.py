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


@pytest.fixture(autouse=True)
def any_hour(monkeypatch):
    # These hit the real endpoint on the real clock, so they'd fail at night. The hours themselves are
    # tested with a fixed clock in test_checkin_windows.py.
    monkeypatch.setattr("cron.in_checkin_window", lambda click_time, now: True)


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

    async def fake_send(db_, uid, tid):
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

    async def fake_send(db_, uid, tid):
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", fake_send)

    r = api.post("/cron/checkins", headers=CRON)
    assert r.json() == {"attempted": 0, "sent": 0, "skipped": 0, "failed": 0}


def test_cron_checks_in_at_most_once_a_day_per_person(api, db, monkeypatch):
    # Nudged about one task today: their other waiting tasks wait too, but other people still get theirs.
    me, h = register(api)
    other, oh = register(api)
    api.post("/devices/register", json={"expo_push_token": TOKEN}, headers=h)
    api.post("/devices/register", json={"expo_push_token": "ExponentPushToken[eeeeeeeeeeeeeeeeeeeeee]"}, headers=oh)
    first = api.post("/tasks", json={"title": "a", "due_date": "2020-01-01T00:00:00Z"}, headers=h).json()["id"]
    api.post("/tasks", json={"title": "b", "due_date": "2020-01-02T00:00:00Z"}, headers=h)
    api.post("/tasks", json={"title": "c", "due_date": "2020-01-03T00:00:00Z"}, headers=h)
    theirs = api.post("/tasks", json={"title": "d", "due_date": "2020-01-01T00:00:00Z"}, headers=oh).json()["id"]
    db.add(models.Event(user_id=me, task_id=first, type="checkin_sent"))
    db.commit()

    sent = []

    async def fake_send(db_, uid, tid):
        sent.append((uid, tid))
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", fake_send)

    assert api.post("/cron/checkins", headers=CRON).json()["sent"] == 1
    assert sent == [(other, theirs)]
    # The next hourly run sends nothing new: both people have had today's check-in.
    assert api.post("/cron/checkins", headers=CRON).json()["attempted"] == 0


def test_cron_checks_in_again_after_the_cooldown(api, db, monkeypatch):
    me, h = register(api)
    api.post("/devices/register", json={"expo_push_token": TOKEN}, headers=h)
    task_id = api.post("/tasks", json={"title": "a", "due_date": "2020-01-01T00:00:00Z"}, headers=h).json()["id"]
    yesterday = datetime.now(timezone.utc) - timedelta(hours=21)
    db.add(models.Event(user_id=me, task_id=task_id, type="checkin_sent", created_at=yesterday))
    db.commit()

    async def fake_send(db_, uid, tid):
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", fake_send)
    assert api.post("/cron/checkins", headers=CRON).json()["sent"] == 1


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

    async def flaky_send(db_, uid, tid):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("expo is down")
        return {"status": "ok"}

    monkeypatch.setattr("cron.send_daily_checkin", flaky_send)

    r = api.post("/cron/checkins", headers=CRON)
    body = r.json()
    assert body["attempted"] == 2
    assert body["sent"] == 1 and body["failed"] == 1


def test_checkin_names_its_task_and_only_the_callers_task(api, db, monkeypatch):
    import asyncio
    from notifications import service

    uid, h = register(api)
    other, oh = register(api)
    mine = api.post("/tasks", json={"title": "Finish writing report for manager"}, headers=h).json()["id"]
    theirs = api.post("/tasks", json={"title": "Someone else's secret"}, headers=oh).json()["id"]
    sent = []

    async def fake_push(*, title, body, **kw):
        sent.append((title, body))
        return {"status": "ok"}

    monkeypatch.setattr(service, "send_push", fake_push)
    asyncio.run(service.send_daily_checkin(db, uid, mine))
    asyncio.run(service.send_daily_checkin(db, uid, theirs))   # not this user's task: no title leaks
    assert "“Finish writing report for manager”" in sent[0][1]
    assert sent[1] == ("Hey! 🌟", "How's your task going today?")
    assert "secret" not in str(sent)


def test_checkin_wording_fits_the_situation_and_changes_day_to_day():
    from notifications import service

    now = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)

    def task(due=None, title="Lab report"):
        return models.Task(title=title, due_date=due)

    assert service.checkin_situation(task(now - timedelta(hours=1)), now) == "past_due"
    assert service.checkin_situation(task(now + timedelta(hours=5)), now) == "due_soon"
    assert service.checkin_situation(task(now + timedelta(days=3)), now) == "waiting"
    assert service.checkin_situation(task(), now) == "waiting"
    # SQLite hands back naive datetimes: they're UTC.
    assert service.checkin_situation(task((now - timedelta(hours=1)).replace(tzinfo=None)), now) == "past_due"

    title, body = service.checkin_message(task(now + timedelta(hours=5)), now)
    assert title == "Heads up 🌟" and "“Lab report”" in body

    # Variants take turns by day: never the same line two days running.
    days = [service.checkin_message(task(), now + timedelta(days=d))[1] for d in range(4)]
    assert all(days[d] != days[d + 1] for d in range(3))

    # Every line names the task and never counts anything (no "3 days", no ignored check-ins).
    for _, bodies in service.CHECKIN_LINES.values():
        for line in bodies:
            filled = line.format(task="“X”")
            assert "“X”" in filled and not any(ch.isdigit() for ch in filled)

    long_body = service.checkin_message(task(title="x" * 100), now)[1]
    assert "…”" in long_body and len(long_body) < 110


def test_checkin_greets_them_by_name_and_only_their_own(api, db, monkeypatch):
    import asyncio
    from notifications import service

    now = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)
    task = models.Task(title="Lab report", due_date=now + timedelta(hours=5))
    assert service.checkin_message(task, now, "Nithya Sri")[0] == "Heads up, Nithya 🌟"   # first word only
    assert service.checkin_message(models.Task(title="Lab report"), now, "Nithya")[0] == "Hey Nithya! 🌟"
    assert service.checkin_message(task, now, None)[0] == "Heads up 🌟"                  # no name: as before
    assert service.checkin_message(None, now, "Nithya")[0] == "Hey Nithya! 🌟"

    uid, h = register(api)
    other, oh = register(api)
    api.post("/me/onboarding", json={"name": "Nithya"}, headers=h)
    mine = api.post("/tasks", json={"title": "a"}, headers=h).json()["id"]
    theirs = api.post("/tasks", json={"title": "b"}, headers=oh).json()["id"]
    sent = []

    async def fake_push(*, title, body, **kw):
        sent.append(title)
        return {"status": "ok"}

    monkeypatch.setattr(service, "send_push", fake_push)
    asyncio.run(service.send_daily_checkin(db, uid, mine))
    asyncio.run(service.send_daily_checkin(db, other, theirs))
    assert sent == ["Hey Nithya! 🌟", "Hey! 🌟"]
