from datetime import datetime, timedelta, timezone

import pytest

import models
from brain.state_detection import Hypothesis, classify, detect_state

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def sent(*days_ago: int) -> list[datetime]:
    return [NOW - d * DAY for d in days_ago]


# ── pure classify() — table-driven ──────────────────────────────────────────

def test_done_task_is_recovery_regardless_of_everything_else():
    assert classify(
        task_status="done", due_date=None, emotion_tap="tired",
        checkin_sent_at=sent(5, 4, 3, 2, 1), activity_at=[], now=NOW,
    ) == [Hypothesis("recovery", 0.9)]


@pytest.mark.parametrize("tap,expected_state", [
    ("tired", "fatigue"),
    ("too_much", "overwhelm"),
    ("unclear", "ambiguity"),
])
def test_emotion_tap_maps_directly_to_its_state(tap, expected_state):
    assert classify(
        task_status="open", due_date=None, emotion_tap=tap,
        checkin_sent_at=[], activity_at=[], now=NOW,
    ) == [Hypothesis(expected_state, 0.8)]


def test_emotion_tap_wins_even_with_an_ignored_history():
    # A direct self-report this cycle outranks whatever silence came before it.
    assert classify(
        task_status="open", due_date=NOW, emotion_tap="tired",
        checkin_sent_at=sent(3, 2, 1), activity_at=[], now=NOW,
    ) == [Hypothesis("fatigue", 0.8)]


def test_ignored_twice_with_due_date_is_commitment_drift():
    assert classify(
        task_status="open", due_date=NOW + DAY, emotion_tap=None,
        checkin_sent_at=sent(2, 1), activity_at=[], now=NOW,
    ) == [Hypothesis("commitment_drift", 0.5)]


def test_ignored_twice_with_no_due_date_is_avoidance():
    assert classify(
        task_status="open", due_date=None, emotion_tap=None,
        checkin_sent_at=sent(2, 1), activity_at=[], now=NOW,
    ) == [Hypothesis("avoidance", 0.5)]


def test_ignored_once_is_not_enough_to_claim_anything():
    assert classify(
        task_status="open", due_date=None, emotion_tap=None,
        checkin_sent_at=sent(1), activity_at=[], now=NOW,
    ) == []


def test_ignored_twice_but_a_subtask_was_ticked_in_between_breaks_the_streak():
    # Activity between the two check-ins means the first one was actually answered —
    # this is the "ignored != no tap" fix: any task activity counts, not just a tap.
    sent_at = sent(2, 1)
    activity = [NOW - timedelta(days=1, hours=12)]  # between the two sends
    assert classify(
        task_status="open", due_date=None, emotion_tap=None,
        checkin_sent_at=sent_at, activity_at=activity, now=NOW,
    ) == []


def test_activity_only_before_the_most_recent_checkin_does_not_count():
    # Activity has to fall strictly after a check-in was sent to count as answering it.
    sent_at = sent(2, 1)
    activity = [NOW - timedelta(days=3)]  # before either check-in was even sent
    assert classify(
        task_status="open", due_date=None, emotion_tap=None,
        checkin_sent_at=sent_at, activity_at=activity, now=NOW,
    ) == [Hypothesis("avoidance", 0.5)]


def test_three_ignored_in_a_row_still_just_reports_the_streak_state():
    assert classify(
        task_status="open", due_date=NOW, emotion_tap=None,
        checkin_sent_at=sent(3, 2, 1), activity_at=[], now=NOW,
    ) == [Hypothesis("commitment_drift", 0.5)]


def test_streak_breaks_on_most_recent_activity_even_with_older_ignores():
    # Ignored the first two, but responded to the most recent one — streak is 0, not 2.
    sent_at = sent(3, 2, 1)
    activity = [NOW - timedelta(hours=12)]  # after the most recent send
    assert classify(
        task_status="open", due_date=None, emotion_tap=None,
        checkin_sent_at=sent_at, activity_at=activity, now=NOW,
    ) == []


# ── detect_state() — DB-backed wrapper ──────────────────────────────────────

INVITE = {"X-Invite-Code": "test-invite"}


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def test_detect_state_done_task(api, db):
    user_id, h = register(api)
    t = api.post("/tasks", json={"title": "x"}, headers=h).json()["id"]
    api.patch(f"/tasks/{t}", json={"status": "done"}, headers=h)

    assert detect_state(db, user_id, t) == [Hypothesis("recovery", 0.9)]


def test_detect_state_ignored_twice_no_due_date(api, db):
    user_id, h = register(api)
    t = api.post("/tasks", json={"title": "x"}, headers=h).json()["id"]

    # A check-in can only be sent about a task that already exists — backdate the
    # task itself so the fabricated history below is a realistic timeline, not one
    # where "created just now" looks like a response to a check-in from 2 days ago.
    task = db.get(models.Task, t)
    task.created_at = task.updated_at = datetime.now(timezone.utc) - timedelta(days=3)

    old = datetime.now(timezone.utc) - timedelta(days=2)
    db.add_all([
        models.Event(user_id=user_id, task_id=t, type="checkin_sent", created_at=old),
        models.Event(user_id=user_id, task_id=t, type="checkin_sent", created_at=old + timedelta(days=1)),
    ])
    db.commit()

    assert detect_state(db, user_id, t) == [Hypothesis("avoidance", 0.5)]


def test_detect_state_unknown_task_returns_empty(db):
    assert detect_state(db, "nobody", 999999) == []


def test_detect_state_passes_through_explicit_emotion_tap(api, db):
    user_id, h = register(api)
    t = api.post("/tasks", json={"title": "x"}, headers=h).json()["id"]
    assert detect_state(db, user_id, t, emotion_tap="too_much") == [Hypothesis("overwhelm", 0.8)]
