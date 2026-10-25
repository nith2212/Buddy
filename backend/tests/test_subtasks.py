import pytest

import models

INVITE = {"X-Invite-Code": "test-invite"}


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def make_task(api, headers, **extra):
    r = api.post("/tasks", json={"title": "task", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def users(api):
    a_id, a_h = register(api)
    b_id, b_h = register(api)
    return (a_id, a_h), (b_id, b_h)


# ── PATCH /tasks/{id} ────────────────────────────────────────────────────────

def test_patch_task_edits_title_and_due_date(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    r = api.patch(f"/tasks/{t}", json={"title": "renamed", "due_date": "2026-12-01T00:00:00Z"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "renamed" and body["due_date"].startswith("2026-12-01")


def test_patch_task_status_done_sets_completed_at_and_logs_event(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    r = api.patch(f"/tasks/{t}", json={"status": "done"}, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    task = db.get(models.Task, t)
    assert task.completed_at is not None
    events = db.query(models.Event).filter(models.Event.task_id == t).all()
    assert len(events) == 1 and events[0].type == "completed" and events[0].source == "user"


def test_patch_task_done_is_idempotent_no_duplicate_events(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    api.patch(f"/tasks/{t}", json={"status": "done"}, headers=h)
    api.patch(f"/tasks/{t}", json={"status": "done"}, headers=h)
    assert db.query(models.Event).filter(models.Event.task_id == t).count() == 1


def test_patch_task_reopen_clears_completed_at(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    api.patch(f"/tasks/{t}", json={"status": "done"}, headers=h)
    api.patch(f"/tasks/{t}", json={"status": "open"}, headers=h)
    task = db.get(models.Task, t)
    assert task.status == "open" and task.completed_at is None


def test_patch_task_cannot_touch_other_users_task(api, users):
    (_, a_h), (_, b_h) = users
    b_task = make_task(api, b_h)
    assert api.patch(f"/tasks/{b_task}", json={"title": "hijacked"}, headers=a_h).status_code == 404


def test_patch_task_requires_auth(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    assert api.patch(f"/tasks/{t}", json={"title": "x"}).status_code == 401


# ── Subtasks ─────────────────────────────────────────────────────────────────

def test_create_and_embed_subtasks_in_task_list(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    r = api.post(f"/tasks/{t}/subtasks", json={"title": "step 1"}, headers=h)
    assert r.status_code == 201
    sub = r.json()
    assert sub["title"] == "step 1" and sub["done"] is False and sub["position"] == 0

    listed = api.get("/tasks", headers=h).json()
    assert listed[0]["subtasks"] == [sub]


def test_subtask_position_increments(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    first = api.post(f"/tasks/{t}/subtasks", json={"title": "a"}, headers=h).json()
    second = api.post(f"/tasks/{t}/subtasks", json={"title": "b"}, headers=h).json()
    assert first["position"] == 0 and second["position"] == 1


def test_toggle_subtask_done(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    sub_id = api.post(f"/tasks/{t}/subtasks", json={"title": "step"}, headers=h).json()["id"]
    r = api.patch(f"/tasks/{t}/subtasks/{sub_id}", json={"done": True}, headers=h)
    assert r.status_code == 200 and r.json()["done"] is True


def test_edit_subtask_title(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    sub_id = api.post(f"/tasks/{t}/subtasks", json={"title": "step"}, headers=h).json()["id"]
    r = api.patch(f"/tasks/{t}/subtasks/{sub_id}", json={"title": "renamed step"}, headers=h)
    assert r.json()["title"] == "renamed step"


def test_delete_subtask(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    sub_id = api.post(f"/tasks/{t}/subtasks", json={"title": "step"}, headers=h).json()["id"]
    assert api.delete(f"/tasks/{t}/subtasks/{sub_id}", headers=h).status_code == 204
    assert db.get(models.Subtask, sub_id) is None


def test_cannot_create_subtask_on_other_users_task(api, users):
    (_, a_h), (_, b_h) = users
    b_task = make_task(api, b_h)
    r = api.post(f"/tasks/{b_task}/subtasks", json={"title": "sneaky"}, headers=a_h)
    assert r.status_code == 404


def test_cannot_modify_other_users_subtask(api, users):
    (_, a_h), (_, b_h) = users
    b_task = make_task(api, b_h)
    b_sub = api.post(f"/tasks/{b_task}/subtasks", json={"title": "b's step"}, headers=b_h).json()["id"]
    assert api.patch(f"/tasks/{b_task}/subtasks/{b_sub}", json={"done": True}, headers=a_h).status_code == 404
    assert api.delete(f"/tasks/{b_task}/subtasks/{b_sub}", headers=a_h).status_code == 404


def test_subtask_under_wrong_task_id_404s(api, users):
    """A subtask that exists, but not under *this* task_id, must still 404."""
    (_, h), _ = users
    t1 = make_task(api, h, title="task 1")
    t2 = make_task(api, h, title="task 2")
    sub_id = api.post(f"/tasks/{t1}/subtasks", json={"title": "step"}, headers=h).json()["id"]
    assert api.patch(f"/tasks/{t2}/subtasks/{sub_id}", json={"done": True}, headers=h).status_code == 404


def test_subtask_validation(api, users):
    (_, h), _ = users
    t = make_task(api, h)
    assert api.post(f"/tasks/{t}/subtasks", json={"title": ""}, headers=h).status_code == 422
    assert api.post(f"/tasks/{t}/subtasks", json={"title": "x" * 201}, headers=h).status_code == 422


def test_subtask_cap_enforced(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    for i in range(50):
        db.add(models.Subtask(user_id=db.get(models.Task, t).user_id, task_id=t, title=f"s{i}", position=i))
    db.commit()
    r = api.post(f"/tasks/{t}/subtasks", json={"title": "one too many"}, headers=h)
    assert r.status_code == 422


# ── check-in "done" tap flips status too ────────────────────────────────────

def test_checkin_task_state_done_also_marks_task_done(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    r = api.post("/checkin/action", json={"task_id": t, "stage": "task_state", "value": "done"}, headers=h)
    assert r.status_code == 200

    task = db.get(models.Task, t)
    assert task.status == "done" and task.completed_at is not None and task.task_state == "done"
    events = db.query(models.Event).filter(models.Event.task_id == t, models.Event.type == "completed").all()
    assert len(events) == 1


def test_checkin_task_state_in_progress_does_not_mark_done(api, users, db):
    (_, h), _ = users
    t = make_task(api, h)
    api.post("/checkin/action", json={"task_id": t, "stage": "task_state", "value": "in_progress"}, headers=h)
    task = db.get(models.Task, t)
    assert task.status == "open" and task.completed_at is None


# ── GET /tasks/{id} ──────────────────────────────────────────────────────────

def test_get_single_task_includes_subtasks(api, users):
    (_, h), _ = users
    t = make_task(api, h, due_date="2026-12-01T00:00:00Z")
    api.post(f"/tasks/{t}/subtasks", json={"title": "step 1"}, headers=h)

    r = api.get(f"/tasks/{t}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == t and body["due_date"].startswith("2026-12-01")
    assert [s["title"] for s in body["subtasks"]] == ["step 1"]


def test_get_single_task_is_scoped_and_authenticated(api, users):
    (_, a_h), (_, b_h) = users
    b_task = make_task(api, b_h)
    assert api.get(f"/tasks/{b_task}", headers=a_h).status_code == 404
    assert api.get(f"/tasks/{b_task}").status_code == 401
    assert api.get("/tasks/999999", headers=a_h).status_code == 404
