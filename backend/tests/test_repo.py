import pytest

import models
from brain import tools

INVITE = {"X-Invite-Code": "test-invite"}


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def make_task(api, headers, title="task"):
    return api.post("/tasks", json={"title": title}, headers=headers).json()["id"]


# ── get_task_history ────────────────────────────────────────────────────────

def test_get_task_history_scoped_to_user(api, db):
    a_id, a_h = register(api)
    b_id, _ = register(api)
    task_id = make_task(api, a_h)

    tools.log_event(db, a_id, "postponed", task_id=task_id)

    history = tools.get_task_history(db, a_id, task_id)
    assert history["task"]["id"] == task_id
    assert len(history["events"]) == 1 and history["events"][0]["type"] == "postponed"

    # B cannot read A's task through this function either.
    assert tools.get_task_history(db, b_id, task_id)["task"] is None


def test_log_event_rejects_unknown_type(db):
    with pytest.raises(ValueError):
        tools.log_event(db, "whoever", "bogus_type")


# ── memory ───────────────────────────────────────────────────────────────────

def test_update_memory_upserts(api, db):
    u1, _ = register(api)
    tools.update_memory(db, u1, "buddy.last_detected_state", "avoidance", confidence=0.5, source="buddy")
    tools.update_memory(db, u1, "buddy.last_detected_state", "fatigue", confidence=0.6, source="buddy")

    rows = tools.get_user_memory(db, u1)
    assert len(rows) == 1
    assert rows[0] == {"key": "buddy.last_detected_state", "value": "fatigue", "confidence": 0.6, "source": "buddy"}


def test_get_user_memory_orders_by_confidence_desc(api, db):
    u1, _ = register(api)
    tools.update_memory(db, u1, "a", "1", confidence=0.2)
    tools.update_memory(db, u1, "b", "2", confidence=0.9)
    rows = tools.get_user_memory(db, u1)
    assert [r["key"] for r in rows] == ["b", "a"]


def test_memory_scoped_to_user(api, db):
    u1, _ = register(api)
    u2, _ = register(api)
    tools.update_memory(db, u1, "k", "v1")
    tools.update_memory(db, u2, "k", "v2")
    assert tools.get_user_memory(db, u1) == [{"key": "k", "value": "v1", "confidence": 0.5, "source": "buddy"}]


# ── emotion pick ─────────────────────────────────────────────────────────────

def test_log_emotion_pick_rejects_invalid_emotion(db):
    with pytest.raises(ValueError):
        tools.log_emotion_pick(db, "u1", "furious")


def test_log_emotion_pick_sources_as_user(api, db):
    u1, _ = register(api)
    event_id = tools.log_emotion_pick(db, u1, "tired", task_id=None)
    event = db.get(models.Event, event_id)
    assert event.source == "user" and event.type == "emotion_picked" and event.payload == "tired"


# ── conversation history (via Message table) ────────────────────────────────

def test_conversation_round_trip(api, db):
    u1, _ = register(api)
    tools.save_conversation_turn(db, u1, "user", "hello")
    tools.save_conversation_turn(db, u1, "assistant", "hi there", reasoning={"top_state": "avoidance"})

    history = tools.get_conversation_history(db, u1)
    assert history == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi there"}]

    reasoning = tools.get_reasoning_history(db, u1)
    assert len(reasoning) == 1 and reasoning[0]["top_state"] == "avoidance"


def test_conversation_history_respects_limit_and_order(api, db):
    u1, _ = register(api)
    for i in range(5):
        tools.save_conversation_turn(db, u1, "user", f"msg{i}")
    history = tools.get_conversation_history(db, u1, limit=2)
    assert [h["content"] for h in history] == ["msg3", "msg4"]


def test_conversation_scoped_to_user(api, db):
    u1, _ = register(api)
    u2, _ = register(api)
    tools.save_conversation_turn(db, u1, "user", "a's message")
    tools.save_conversation_turn(db, u2, "user", "b's message")
    assert tools.get_conversation_history(db, u1) == [{"role": "user", "content": "a's message"}]


# ── complete_task ────────────────────────────────────────────────────────────

def test_complete_task_sets_status_and_logs_event(api, db):
    user_id, h = register(api)
    task_id = make_task(api, h)

    tools.complete_task(db, user_id, task_id)

    task = db.get(models.Task, task_id)
    assert task.status == "done" and task.completed_at is not None
    events = db.query(models.Event).filter(models.Event.task_id == task_id).all()
    assert len(events) == 1 and events[0].type == "completed" and events[0].source == "user"


def test_complete_task_is_noop_for_wrong_user(api, db):
    user_id, h = register(api)
    task_id = make_task(api, h)

    tools.complete_task(db, "someone-else", task_id)

    task = db.get(models.Task, task_id)
    assert task.status == "open"
    assert db.query(models.Event).filter(models.Event.task_id == task_id).count() == 0
