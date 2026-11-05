import pytest
from sqlalchemy import func, select

import models

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
    log = db.execute(select(models.EmotionLog).where(models.EmotionLog.task_id == t)).scalar_one()
    assert log.user_id == a_id and log.emotion == "low" and log.chat_opt_in is True


def test_declined_chat_completes_checkin(api, users):
    (_, a_h), _ = users
    t = make_task(api, a_h)
    api.post("/checkin/action", json={"task_id": t, "stage": "emotion", "value": "good"}, headers=a_h)
    r = api.post("/checkin/action", json={"task_id": t, "stage": "chat_opt_in", "value": "no"}, headers=a_h)
    assert r.json()["next_stage"] == "done"


@pytest.mark.parametrize("stage,value", [("task_state", "done"), ("emotion", "low"), ("chat_opt_in", "yes")])
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
        models.Onboarding(user_id=user_id, preferred_work_time="evening"),
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
