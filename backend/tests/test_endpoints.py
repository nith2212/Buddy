import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

import models

UTC = timezone.utc

INVITE = {"X-Invite-Code": "test-invite"}
TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


@pytest.fixture
def users(api):
    a_id, a_h = register(api)
    b_id, b_h = register(api)
    return (a_id, a_h), (b_id, b_h)


def make_task(api, headers, title="write report", **extra):
    r = api.post("/tasks", json={"title": title, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── auth required everywhere ────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("post", "/devices/register", {"expo_push_token": TOKEN_A}),
    ("post", "/checkin/action", {"task_id": 1, "stage": "task_state", "value": "done"}),
    ("post", "/tasks", {"title": "x"}),
    ("get", "/tasks", None),
    ("delete", "/me", None),
    ("delete", "/tasks/1", None),
    ("post", "/me/onboarding", {"click_time": "evening"}),
])
def test_protected_endpoints_need_token(api, method, path, body):
    r = getattr(api, method)(path, **({"json": body} if body else {}))
    assert r.status_code == 401
    r = getattr(api, method)(path, headers={"Authorization": "Bearer nope"}, **({"json": body} if body else {}))
    assert r.status_code == 401


def test_dev_routes_are_gone(api, users):
    (_, h), _ = users
    assert api.post("/tasks/create?user_id=x", headers=h).status_code in (404, 405)
    assert api.post("/test/send-push?user_id=x", headers=h).status_code in (404, 405)


# ── /devices/register ───────────────────────────────────────────────────────

def device_rows(db):
    return db.execute(select(models.DeviceToken)).scalars().all()


def test_register_device_uses_token_identity_not_body(api, users, db):
    (a_id, a_h), (b_id, _) = users
    # A forged user_id in the body must be ignored.
    r = api.post("/devices/register", json={"expo_push_token": TOKEN_A, "user_id": b_id}, headers=a_h)
    assert r.status_code == 200
    rows = device_rows(db)
    assert [(d.user_id, d.expo_push_token) for d in rows] == [(a_id, TOKEN_A)]


def test_register_is_idempotent_and_supports_multiple_devices(api, users, db):
    (a_id, a_h), _ = users
    for tok in (TOKEN_A, TOKEN_A, TOKEN_B):
        assert api.post("/devices/register", json={"expo_push_token": tok}, headers=a_h).status_code == 200
    assert sorted(d.expo_push_token for d in device_rows(db)) == sorted([TOKEN_A, TOKEN_B])


def test_token_moves_to_new_owner_without_duplicates(api, users, db):
    (a_id, a_h), (b_id, b_h) = users
    api.post("/devices/register", json={"expo_push_token": TOKEN_A}, headers=a_h)
    api.post("/devices/register", json={"expo_push_token": TOKEN_A}, headers=b_h)
    rows = device_rows(db)
    assert len(rows) == 1 and rows[0].user_id == b_id


@pytest.mark.parametrize("bad", ["", "abc", "ExponentPushToken[]", "ExponentPushToken[x"])
def test_register_rejects_malformed_token(api, users, bad):
    (_, a_h), _ = users
    assert api.post("/devices/register", json={"expo_push_token": bad}, headers=a_h).status_code == 422


# ── /tasks ──────────────────────────────────────────────────────────────────

def test_create_and_list_tasks_are_scoped(api, users):
    (_, a_h), (_, b_h) = users
    a_task = make_task(api, a_h, "A's task", due_date="2026-11-01T10:00:00Z")
    make_task(api, b_h, "B's task")
    listed = api.get("/tasks", headers=a_h).json()
    assert [t["id"] for t in listed] == [a_task]
    assert listed[0]["title"] == "A's task" and listed[0]["status"] == "open"
    assert listed[0]["due_date"].startswith("2026-11-01T10:00:00")


def test_task_validation_and_caps(api, users):
    (_, h), _ = users
    assert api.post("/tasks", json={"title": ""}, headers=h).status_code == 422
    assert api.post("/tasks", json={"title": "x" * 201}, headers=h).status_code == 422
    assert api.post("/tasks", json={"title": "ok", "due_date": "not-a-date"}, headers=h).status_code == 422
    assert api.get("/tasks?limit=101", headers=h).status_code == 422
    assert api.get("/tasks?status=bogus", headers=h).status_code == 422
    # naive due dates are accepted and treated as UTC
    assert api.post("/tasks", json={"title": "ok", "due_date": "2026-11-01T10:00:00"}, headers=h).status_code == 201


def test_user_id_in_task_body_is_ignored(api, users, db):
    (a_id, a_h), (b_id, _) = users
    task_id = make_task(api, a_h, user_id=b_id)
    assert db.get(models.Task, task_id).user_id == a_id


# ── /checkin/action ─────────────────────────────────────────────────────────

def test_full_checkin_flow(api, users, db):
    (a_id, a_h), _ = users
    t = make_task(api, a_h)

    r = api.post("/checkin/action", json={"task_id": t, "stage": "task_state", "value": "in_progress"}, headers=a_h)
    assert r.status_code == 200 and r.json()["next_stage"] == "emotion"
    assert db.get(models.Task, t).task_state == "in_progress"

    r = api.post("/checkin/action", json={"task_id": t, "stage": "emotion", "value": "low"}, headers=a_h)
    assert r.json()["next_stage"] == "chat_opt_in"

    r = api.post("/checkin/action", json={"task_id": t, "stage": "chat_opt_in", "value": "yes"}, headers=a_h)
    assert r.json()["next_stage"] == "chat"
    assert "notification" not in r.json()  # the app opens the chat itself; nothing to show
    log = db.execute(select(models.EmotionLog).where(models.EmotionLog.task_id == t)).scalar_one()
    assert log.user_id == a_id and log.emotion == "low" and log.chat_opt_in is True


def test_declined_chat_completes_checkin(api, users):
    (_, a_h), _ = users
    t = make_task(api, a_h)
    api.post("/checkin/action", json={"task_id": t, "stage": "emotion", "value": "good"}, headers=a_h)
    r = api.post("/checkin/action", json={"task_id": t, "stage": "chat_opt_in", "value": "no"}, headers=a_h)
    assert r.json()["next_stage"] == "done"
    assert r.json()["notification"]["title"] == "Got it! 💛"


def _action(api, h, t, stage, value):
    return api.post("/checkin/action", json={"task_id": t, "stage": stage, "value": value}, headers=h).json()


def _buttons(body):
    return [a["value"] for a in body["notification"]["data"]["actions"]]


def test_checkin_done_celebrates_and_ends(api, users, db):
    (_, a_h), _ = users
    t = make_task(api, a_h)
    body = _action(api, a_h, t, "task_state", "done")
    assert body["next_stage"] == "done"
    assert body["notification"]["title"] == "Yay, you did it! 🎉"
    assert "actions" not in body["notification"]["data"]  # no "what's in the way?" after finishing
    assert db.get(models.Task, t).status == "done"


def test_checkin_status_asks_whats_in_the_way(api, users):
    (_, a_h), _ = users
    t = make_task(api, a_h)
    not_yet = _action(api, a_h, t, "task_state", "not_started")
    on_it = _action(api, a_h, t, "task_state", "in_progress")
    assert not_yet["notification"]["title"] == "Okay! What's in the way?"
    assert on_it["notification"]["title"] == "Ooh, you started! 🙌"
    assert _buttons(not_yet) == _buttons(on_it) == ["tired", "unclear", "more"]


def test_something_else_shows_the_other_reasons_and_logs_nothing(api, users, db):
    (_, a_h), _ = users
    t = make_task(api, a_h)
    more = _action(api, a_h, t, "emotion", "more")
    assert more["next_stage"] == "emotion_more"
    assert _buttons(more) == ["too_much", "afraid", "bored"]
    assert db.scalar(select(func.count()).select_from(models.EmotionLog)) == 0  # "Something else" isn't a reason

    offer = _action(api, a_h, t, "emotion_more", "afraid")
    assert offer["next_stage"] == "chat_opt_in"
    assert offer["notification"]["title"] == "A rough start counts 💛"
    assert _buttons(offer) == ["yes", "no"]
    log = db.execute(select(models.EmotionLog).where(models.EmotionLog.task_id == t)).scalar_one()
    assert log.emotion == "afraid"


def test_chat_offers_hint_at_the_cause_without_naming_it():
    # Notifications sit on a public lock screen: never spell out a fear.
    from notifications.router import CHAT_OFFERS, DEFAULT_OFFER

    assert set(CHAT_OFFERS) == {"tired", "too_much", "unclear", "afraid", "bored"}
    for title, body in [*CHAT_OFFERS.values(), DEFAULT_OFFER]:
        text = (title + " " + body).lower()
        assert not any(word in text for word in ("scared", "afraid", "fear", "lazy", "anxious"))


@pytest.mark.parametrize("stage,value", [
    ("task_state", "done"), ("emotion", "low"), ("emotion", "more"), ("emotion_more", "afraid"), ("chat_opt_in", "yes"),
])
def test_cannot_check_in_on_other_users_task(api, users, db, stage, value):
    (_, a_h), (b_id, b_h) = users
    b_task = make_task(api, b_h)
    r = api.post("/checkin/action", json={"task_id": b_task, "stage": stage, "value": value}, headers=a_h)
    assert r.status_code == 404
    assert db.get(models.Task, b_task).task_state is None
    assert db.scalar(select(func.count()).select_from(models.EmotionLog)) == 0


def test_checkin_unknown_stage_rejected(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    assert api.post("/checkin/action", json={"task_id": t, "stage": "bogus", "value": "x"}, headers=h).status_code == 422


# ── DELETE /me ──────────────────────────────────────────────────────────────

USER_TABLES = [models.EmotionLog, models.Subtask, models.Event, models.Message, models.Memory,
               models.Onboarding, models.DeviceToken, models.Task]


def seed_everything(api, db, user_id, headers, token):
    t = make_task(api, headers)
    api.post("/devices/register", json={"expo_push_token": token}, headers=headers)
    api.post("/checkin/action", json={"task_id": t, "stage": "emotion", "value": "low"}, headers=headers)
    db.add_all([
        models.Subtask(user_id=user_id, task_id=t, title="step 1"),
        models.Event(user_id=user_id, task_id=t, type="checkin_sent"),
        models.Message(user_id=user_id, task_id=t, role="user", content="hi"),
        models.Memory(user_id=user_id, key="onboarding.x", value="v"),
        models.Onboarding(user_id=user_id, click_time="evening"),
    ])
    db.commit()


def count(db, model, user_id):
    return db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))


def test_delete_me_wipes_caller_only(api, users, db):
    (a_id, a_h), (b_id, b_h) = users
    seed_everything(api, db, a_id, a_h, TOKEN_A)
    seed_everything(api, db, b_id, b_h, TOKEN_B)
    before_b = {m.__tablename__: count(db, m, b_id) for m in USER_TABLES}
    assert all(v >= 1 for v in before_b.values())

    assert api.delete("/me", headers=a_h).status_code == 204

    db.expire_all()
    assert all(count(db, m, a_id) == 0 for m in USER_TABLES)
    assert db.get(models.User, a_id) is None
    assert {m.__tablename__: count(db, m, b_id) for m in USER_TABLES} == before_b
    assert db.get(models.User, b_id) is not None
    # A's token no longer works; B's still does.
    assert api.get("/tasks", headers=a_h).status_code == 401
    assert api.get("/tasks", headers=b_h).status_code == 200


# ── delete a task ───────────────────────────────────────────────────────────

def test_delete_task_removes_everything_about_it_and_nothing_else(api, users, db):
    (a_id, a_h), (b_id, b_h) = users
    gone, kept = make_task(api, a_h, "Lab report"), make_task(api, a_h, "Essay")
    theirs = make_task(api, b_h, "Their task")
    for uid, h, t in ((a_id, a_h, gone), (a_id, a_h, kept), (b_id, b_h, theirs)):
        api.post("/checkin/action", json={"task_id": t, "stage": "emotion", "value": "afraid"}, headers=h)
        db.add_all([
            models.Subtask(user_id=uid, task_id=t, title="step 1"),
            models.Event(user_id=uid, task_id=t, type="checkin_sent"),
            models.Message(user_id=uid, task_id=t, role="user", content="hi"),
            models.Memory(user_id=uid, key=f"blocker.task.{t}", value="afraid"),
        ])
    # The deleted task had two causes confirmed in chat: afraid inside Echo's saved week, tired after it.
    # (Every task's blocker.task row says afraid; the turns are what was counted.)
    db.add_all([
        models.Message(user_id=a_id, task_id=gone, role="assistant", content="ok",
                       reasoning=json.dumps({"saved_cause": "afraid"}), created_at=datetime(2026, 10, 30, 9, tzinfo=UTC)),
        models.Message(user_id=a_id, task_id=gone, role="assistant", content="ok",
                       reasoning=json.dumps({"saved_cause": "tired"}), created_at=datetime(2026, 11, 5, 9, tzinfo=UTC)),
    ])
    week = {"start": "2026-10-25T17:30:00+00:00", "end": "2026-11-01T17:30:00+00:00", "checkins": {"sent": 3},
            "cause_totals": {"afraid": 2}, "causes_confirmed": {"afraid": 1},
            "open_tasks": [{"id": gone, "checkins_ignored": 2}, {"id": kept, "checkins_ignored": 0}]}
    db.add_all([
        models.Memory(user_id=a_id, key="pattern.blocker.afraid", value="2"),
        models.Memory(user_id=a_id, key="pattern.blocker.tired", value="1"),
        models.Memory(user_id=a_id, key="echo.week.2026-11-01", value=json.dumps(week)),
        models.Message(user_id=a_id, task_id=None, role="user", content="not about a task"),
        models.Memory(user_id=b_id, key="pattern.blocker.afraid", value="1"),
    ])
    db.commit()
    task_tables = [models.EmotionLog, models.Subtask, models.Event, models.Message]

    def rows_of(t):
        return {m.__tablename__: db.scalar(select(func.count()).select_from(m).where(m.task_id == t))
                for m in task_tables}

    before = {t: rows_of(t) for t in (gone, kept, theirs)}
    assert all(n >= 1 for counts in before.values() for n in counts.values())
    b_before = {m.__tablename__: count(db, m, b_id) for m in USER_TABLES}

    assert api.delete(f"/tasks/{gone}", headers=a_h).status_code == 204

    db.expire_all()
    assert api.get(f"/tasks/{gone}", headers=a_h).status_code == 404
    assert [t["id"] for t in api.get("/tasks", headers=a_h).json()] == [kept]
    assert all(n == 0 for n in rows_of(gone).values())
    assert rows_of(kept) == before[kept] and rows_of(theirs) == before[theirs]

    memory = {r.key: r.value for r in db.query(models.Memory).filter_by(user_id=a_id)}
    assert f"blocker.task.{gone}" not in memory and memory[f"blocker.task.{kept}"] == "afraid"
    # Its confirmations come out of the counts: afraid 2 -> 1 (the other task's), tired 1 -> gone.
    assert memory["pattern.blocker.afraid"] == "1" and "pattern.blocker.tired" not in memory
    # Echo's week: its row goes, and its afraid comes out of that week's totals, so next week's
    # "totals minus last week's" still counts new confirmations. Totals that name no task stay.
    saved = json.loads(memory["echo.week.2026-11-01"])
    assert [t["id"] for t in saved["open_tasks"]] == [kept] and saved["checkins"] == {"sent": 3}
    assert saved["cause_totals"] == {"afraid": 1} and saved["causes_confirmed"] == {}
    assert db.query(models.Message).filter_by(user_id=a_id, task_id=None).count() == 1
    assert {m.__tablename__: count(db, m, b_id) for m in USER_TABLES} == b_before

    # A check-in still sitting in the notification tray for the deleted task: nothing to act on.
    r = api.post("/checkin/action", json={"task_id": gone, "stage": "task_state", "value": "done"}, headers=a_h)
    assert r.status_code == 404


def test_delete_task_uncounts_a_cause_from_before_turns_recorded_it(api, users, db):
    # Turns saved before 2026-11-09 don't say which cause they counted: the task's blocker row stands in.
    (a_id, a_h), _ = users
    t = make_task(api, a_h)
    db.add_all([
        models.Message(user_id=a_id, task_id=t, role="assistant", content="ok", reasoning=json.dumps({"mode": "chat"})),
        models.Memory(user_id=a_id, key=f"blocker.task.{t}", value="bored"),
        models.Memory(user_id=a_id, key="pattern.blocker.bored", value="3"),
    ])
    db.commit()
    assert api.delete(f"/tasks/{t}", headers=a_h).status_code == 204
    db.expire_all()
    memory = {r.key: r.value for r in db.query(models.Memory).filter_by(user_id=a_id)}
    assert memory == {"pattern.blocker.bored": "2"}


def test_cannot_delete_someone_elses_task(api, users):
    (_, a_h), (_, b_h) = users
    theirs = make_task(api, b_h, "Their secret plan")
    r = api.delete(f"/tasks/{theirs}", headers=a_h)
    assert r.status_code == 404 and "secret" not in r.text
    assert api.get(f"/tasks/{theirs}", headers=b_h).json()["title"] == "Their secret plan"
    assert api.delete("/tasks/999999", headers=a_h).status_code == 404


# ── onboarding ──────────────────────────────────────────────────────────────

def onboarding_of(db, user_id):
    db.expire_all()
    return db.query(models.Onboarding).filter_by(user_id=user_id).one_or_none()


def test_onboarding_saves_the_answers_and_replaces_them(api, users, db):
    (a_id, a_h), _ = users
    r = api.post("/me/onboarding", json={"days": "school", "click_time": "evening",
                                         "gets_in_way": ["tired", "afraid", "tired"]}, headers=a_h)
    assert r.status_code == 200
    assert r.json() == {"days": "school", "click_time": "evening", "gets_in_way": ["afraid", "tired"]}
    row = onboarding_of(db, a_id)
    assert (row.days, row.click_time, row.gets_in_way) == ("school", "evening", "afraid,tired")

    # Sent again (say, after a reinstall): one row, the new answers. Every answer is optional.
    assert api.post("/me/onboarding", json={"click_time": "morning"}, headers=a_h).json() == \
        {"days": None, "click_time": "morning", "gets_in_way": []}
    assert db.query(models.Onboarding).filter_by(user_id=a_id).count() == 1
    row = onboarding_of(db, a_id)
    assert (row.days, row.click_time, row.gets_in_way) == (None, "morning", None)
    assert api.post("/me/onboarding", json={}, headers=a_h).status_code == 200


@pytest.mark.parametrize("body", [
    {"click_time": "3am"},
    {"days": "everything"},
    {"gets_in_way": ["lazy"]},
    {"gets_in_way": "tired"},
])
def test_onboarding_only_takes_the_offered_choices(api, users, body):
    (_, a_h), _ = users
    assert api.post("/me/onboarding", json=body, headers=a_h).status_code == 422


def test_onboarding_answers_are_you_said_never_causes(api, users, db):
    # Picking "scared" in the questionnaire is not a confirmed cause: no cause memory, nothing for Echo.
    (a_id, a_h), _ = users
    api.post("/me/onboarding", json={"gets_in_way": ["afraid", "too_much"]}, headers=a_h)
    db.expire_all()
    assert db.query(models.Memory).filter_by(user_id=a_id).count() == 0
    assert db.query(models.EmotionLog).filter_by(user_id=a_id).count() == 0


def test_onboarding_is_only_ever_the_callers(api, users, db):
    (a_id, a_h), (b_id, b_h) = users
    api.post("/me/onboarding", json={"click_time": "late_night"}, headers=b_h)
    # Identity comes only from the token: a user_id in the body is ignored.
    api.post("/me/onboarding", json={"click_time": "morning", "user_id": b_id}, headers=a_h)
    assert onboarding_of(db, b_id).click_time == "late_night"
    assert onboarding_of(db, a_id).click_time == "morning"


# ── keep-warm ping ──────────────────────────────────────────────────────────

def test_health_is_public_and_cheap(api):
    r = api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_db_checks_connections_before_reuse():
    # Neon drops idle connections when it sleeps; pre-ping swaps a dead one for a fresh one.
    from db import engine
    assert engine.pool._pre_ping is True
