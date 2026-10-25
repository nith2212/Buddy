import pytest

import models

INVITE = {"X-Invite-Code": "test-invite"}


def register(client):
    r = client.post("/auth/anonymous", headers=INVITE)
    assert r.status_code == 201
    body = r.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def seed_rows(db, user_id):
    """One row of each kind owned by user_id; returns {kind: id}."""
    task = models.Task(user_id=user_id, title="secret task")
    dev = models.DeviceToken(user_id=user_id, expo_push_token=f"ExponentPushToken[{user_id}]")
    event = models.Event(user_id=user_id, type="checkin_sent")
    mem = models.Memory(user_id=user_id, key="onboarding.x", value="secret memory")
    db.add_all([task, dev, event, mem])
    db.flush()  # need task.id before the subtask can reference it
    subtask = models.Subtask(user_id=user_id, task_id=task.id, title="secret subtask")
    db.add(subtask)
    db.commit()
    return {
        "task": task.id, "device_token": dev.id, "event": event.id, "memory": mem.id,
        "subtask": subtask.id,
    }


@pytest.fixture
def two_users(client, db):
    a_id, a_h = register(client)
    b_id, b_h = register(client)
    return {"a": (a_id, a_h, seed_rows(db, a_id)), "b": (b_id, b_h, seed_rows(db, b_id))}


KINDS = ["task", "device_token", "event", "memory", "subtask"]


@pytest.mark.parametrize("kind", KINDS)
def test_owner_can_read_and_modify_own_row(client, two_users, kind):
    _, h, ids = two_users["a"]
    assert client.get(f"/probe/{kind}/{ids[kind]}", headers=h).status_code == 200
    assert client.patch(f"/probe/{kind}/{ids[kind]}", headers=h).status_code == 200


@pytest.mark.parametrize("kind", KINDS)
def test_cannot_read_other_users_row(client, two_users, kind):
    _, a_h, _ = two_users["a"]
    _, _, b_ids = two_users["b"]
    r = client.get(f"/probe/{kind}/{b_ids[kind]}", headers=a_h)
    assert r.status_code == 404
    assert "secret" not in r.text


@pytest.mark.parametrize("kind", KINDS)
def test_cannot_modify_other_users_row(client, two_users, db, kind):
    _, a_h, _ = two_users["a"]
    _, b_h, b_ids = two_users["b"]
    assert client.patch(f"/probe/{kind}/{b_ids[kind]}", headers=a_h).status_code == 404
    # B's row is untouched, and B can still modify it.
    assert client.get(f"/probe/{kind}/{b_ids[kind]}", headers=b_h).json()["value"] != "modified"


@pytest.mark.parametrize("kind", KINDS)
def test_listing_only_returns_own_rows(client, two_users, kind):
    _, a_h, a_ids = two_users["a"]
    assert client.get(f"/probe/{kind}", headers=a_h).json() == [a_ids[kind]]


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer not-a-real-token"},
    {"Authorization": "Bearer "},
    {"Authorization": "Basic abc"},
    {"Authorization": "garbage"},
])
def test_bad_or_missing_token_is_401(client, two_users, headers):
    _, _, ids = two_users["a"]
    assert client.get(f"/probe/task/{ids['task']}", headers=headers).status_code == 401


def test_only_token_hash_is_stored(client, db):
    r = client.post("/auth/anonymous", headers=INVITE).json()
    user = db.get(models.User, r["user_id"])
    assert user.token_hash != r["token"]
    assert len(user.token_hash) == 64


@pytest.mark.parametrize("headers,status", [
    ({}, 403),
    ({"X-Invite-Code": "wrong"}, 403),
])
def test_invite_code_required(client, headers, status):
    assert client.post("/auth/anonymous", headers=headers).status_code == status


def test_registration_fails_closed_without_invite_env(client, monkeypatch):
    monkeypatch.delenv("INVITE_CODE")
    assert client.post("/auth/anonymous", headers=INVITE).status_code == 503


def test_each_registration_gets_distinct_user_and_token(client):
    a_id, a_h = register(client)
    b_id, b_h = register(client)
    assert a_id != b_id and a_h != b_h


def test_existing_endpoints_still_mounted():
    from main import app
    paths = {r.path for r in app.routes}
    assert {"/auth/anonymous", "/devices/register", "/checkin/action", "/tasks", "/me"} <= paths
