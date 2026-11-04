# Echo E1 (brain/echo.py): the weekly count, for Buddy only.
import json
from datetime import datetime, timedelta, timezone

import pytest

import models
from brain import agent, echo

INVITE = {"X-Invite-Code": "test-invite"}
CRON = {"X-Cron-Secret": "test-cron-secret"}

UTC = timezone.utc
END = datetime(2026, 11, 8, 17, 30, tzinfo=UTC)    # Sunday 8 Nov, 23:00 India time
START = END - timedelta(days=7)
NOW = END + timedelta(minutes=30)                  # the cron fires just after


@pytest.fixture(autouse=True)
def cron_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def add_task(db, user_id, *, created, title="Client report", status="open", completed=None):
    t = models.Task(user_id=user_id, title=title, status=status, created_at=created, updated_at=created,
                    completed_at=completed)
    db.add(t)
    db.commit()
    return t


def checkin(db, task, at):
    db.add(models.Event(user_id=task.user_id, task_id=task.id, type="checkin_sent", source="system", created_at=at))
    db.commit()


def tap(db, task, at, emotion="too_much"):
    db.add(models.EmotionLog(user_id=task.user_id, task_id=task.id, emotion=emotion, created_at=at))
    db.commit()


# ── the week ──────────────────────────────────────────────────────────────────────

def test_week_ends_sunday_11pm_india_time():
    assert echo.week_window(NOW) == (START, END)
    assert echo.week_window(END) == (START, END)                       # exactly at the end counts
    assert echo.week_window(END - timedelta(minutes=1)) == (START - timedelta(days=7), START)
    assert echo.week_window(datetime(2026, 11, 11, 9, 0, tzinfo=UTC)) == (START, END)  # a Wednesday
    assert echo.week_id(END) == "2026-11-08"


# ── who gets an Echo ──────────────────────────────────────────────────────────────

def test_no_tasks_no_echo(api, db):
    uid, _ = register(api)
    assert echo.run_echo(db, uid, NOW) == "no_tasks"
    assert db.query(models.Memory).count() == 0


def test_an_ignored_task_still_gets_an_echo(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=START - timedelta(days=10))
    checkin(db, t, START + timedelta(days=1))
    checkin(db, t, START + timedelta(days=3))
    tap(db, t, START + timedelta(days=3, hours=2))      # answered this one
    checkin(db, t, START + timedelta(days=5))
    checkin(db, t, END - timedelta(hours=3))            # too recent to judge yet

    assert echo.run_echo(db, uid, NOW) == "saved"
    row = db.query(models.Memory).filter_by(user_id=uid, key="echo.week.2026-11-08").one()
    assert row.source == "echo"
    facts = json.loads(row.value)
    task = facts["open_tasks"][0]
    assert task["checkins_sent"] == 4
    assert task["checkins_ignored"] == 2
    assert task["days_untouched"] == 3                  # since the tap: 3 days 22 hours before the end
    assert facts["reasons_tapped"] == {"too_much": 1}


def test_progress_and_finished_tasks_are_counted(api, db):
    uid, _ = register(api)
    done = add_task(db, uid, created=START - timedelta(days=3), status="done", completed=START + timedelta(days=2))
    old = add_task(db, uid, created=START - timedelta(days=30), status="done", completed=START - timedelta(days=1))
    t = add_task(db, uid, created=START - timedelta(days=3))
    db.add(models.Subtask(user_id=uid, task_id=t.id, title="outline", done=True,
                          created_at=START, updated_at=START + timedelta(days=4)))
    db.commit()
    facts = echo.week_facts(db, uid, START, END)
    assert facts["tasks_finished"] == 1 and facts["steps_done"] == 1
    assert [x["id"] for x in facts["open_tasks"]] == [t.id]
    assert facts["open_tasks"][0]["days_untouched"] == 3   # the step was ticked 3 days before the end
    assert {done.id, old.id}.isdisjoint(x["id"] for x in facts["open_tasks"])


def test_causes_first_week_then_week_over_week(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=START - timedelta(days=3))
    db.add_all([
        models.Memory(user_id=uid, key=f"blocker.task.{t.id}", value="afraid", updated_at=START + timedelta(days=1)),
        models.Memory(user_id=uid, key="pattern.blocker.afraid", value="3"),
        models.Memory(user_id=uid, key="pattern.blocker.tired", value="1"),
    ])
    db.commit()
    echo.run_echo(db, uid, NOW)
    first = json.loads(db.query(models.Memory).filter_by(key="echo.week.2026-11-08").one().value)
    assert first["first_week"] and first["causes_confirmed"] == {"afraid": 1}

    db.query(models.Memory).filter_by(key="pattern.blocker.afraid").one().value = "5"
    db.commit()
    echo.run_echo(db, uid, NOW + timedelta(days=7))
    second = json.loads(db.query(models.Memory).filter_by(key="echo.week.2026-11-15").one().value)
    assert not second["first_week"] and second["causes_confirmed"] == {"afraid": 2}


def test_once_per_week_and_only_eight_weeks_kept(api, db):
    uid, _ = register(api)
    add_task(db, uid, created=START - timedelta(days=100))
    assert echo.run_echo(db, uid, NOW) == "saved"
    assert echo.run_echo(db, uid, NOW + timedelta(hours=1)) == "already_done"
    for week in range(1, 12):
        echo.run_echo(db, uid, NOW + timedelta(days=7 * week))
    keys = sorted(m.key for m in db.query(models.Memory).filter(models.Memory.key.startswith("echo.week.")))
    assert len(keys) == echo.KEEP_WEEKS and keys[-1] == "echo.week.2027-01-24"


def test_one_users_echo_never_counts_another_users_tasks(api, db):
    a, _ = register(api)
    b, _ = register(api)
    ta = add_task(db, a, created=START - timedelta(days=3))
    tb = add_task(db, b, created=START - timedelta(days=3), title="B's secret task")
    checkin(db, tb, START + timedelta(days=1))
    facts = echo.week_facts(db, a, START, END)
    assert [x["id"] for x in facts["open_tasks"]] == [ta.id]
    assert facts["open_tasks"][0]["checkins_sent"] == 0


# ── postpones ─────────────────────────────────────────────────────────────────────

def test_moving_a_due_date_later_logs_a_postpone(api, db):
    _, h = register(api)
    tid = api.post("/tasks", json={"title": "report", "due_date": "2026-11-10T10:00:00Z"}, headers=h).json()["id"]
    api.patch(f"/tasks/{tid}", json={"due_date": "2026-11-12T10:00:00Z"}, headers=h)   # later: a postpone
    api.patch(f"/tasks/{tid}", json={"due_date": "2026-11-11T10:00:00Z"}, headers=h)   # earlier: not one
    api.patch(f"/tasks/{tid}", json={"title": "client report"}, headers=h)            # no date change
    events = db.query(models.Event).filter_by(task_id=tid, type="postponed").all()
    assert len(events) == 1
    assert json.loads(events[0].payload)["to"].startswith("2026-11-12")


# ── the cron route ────────────────────────────────────────────────────────────────

def test_cron_echo_needs_the_secret(api):
    assert api.post("/cron/echo").status_code == 401
    assert api.post("/cron/echo", headers={"X-Cron-Secret": "wrong"}).status_code == 401


def test_cron_echo_runs_everyone_once(api, db):
    a, _ = register(api)
    register(api)                                       # no tasks: skipped
    add_task(db, a, created=datetime.now(UTC) - timedelta(days=30))
    body = api.post("/cron/echo", headers=CRON).json()
    assert (body["saved"], body["no_tasks"], body["failed"]) == (1, 1, 0)
    again = api.post("/cron/echo", headers=CRON).json()
    assert (again["saved"], again["already_done"]) == (0, 1)


def test_delete_me_wipes_echo(api, db):
    uid, h = register(api)
    add_task(db, uid, created=datetime.now(UTC) - timedelta(days=30))
    api.post("/cron/echo", headers=CRON)
    assert db.query(models.Memory).filter_by(user_id=uid).count() == 1
    assert api.delete("/me", headers=h).status_code == 204
    db.expire_all()
    assert db.query(models.Memory).filter_by(user_id=uid).count() == 0


# ── what Buddy gets ───────────────────────────────────────────────────────────────

def away_facts(**task):
    return {"end": END.isoformat(), "open_tasks": [{"id": 7, "days_untouched": 0, "checkins_ignored": 0, **task}]}


def test_buddy_gets_a_gentle_cue_never_the_facts():
    for facts in (away_facts(days_untouched=6), away_facts(checkins_ignored=2)):
        line = echo.buddy_line(facts, 7)
        assert line and "never mention" in line.lower()
        assert not any(ch.isdigit() for ch in line)
    assert echo.buddy_line(away_facts(days_untouched=2, checkins_ignored=1), 7) is None
    assert echo.buddy_line(away_facts(days_untouched=9), 8) is None    # a different task
    assert echo.buddy_line(None, 7) is None


def test_stale_echo_is_not_used(api, db):
    uid, _ = register(api)
    db.add(models.Memory(user_id=uid, key="echo.week.2026-11-08", value=json.dumps(away_facts(days_untouched=9)),
                         source="echo"))
    db.commit()
    assert echo.latest(db, uid, END + timedelta(days=3)) is not None
    assert echo.latest(db, uid, END + timedelta(days=9)) is None


def test_echo_reaches_the_writer_only_as_the_one_context_line(api, db):
    uid, _ = register(api)
    now = datetime.now(UTC)
    _, end = echo.week_window(now)
    db.add_all([
        models.Memory(user_id=uid, key=f"echo.week.{echo.week_id(end)}", source="echo",
                      value=json.dumps({**away_facts(checkins_ignored=3), "end": end.isoformat()})),
        models.Memory(user_id=uid, key="pattern.blocker.afraid", value="5"),
    ])
    db.commit()
    memory = [{"key": m.key, "value": m.value} for m in db.query(models.Memory).filter_by(user_id=uid)]
    # Echo's cue wins over the pattern line (one line only), and its rows are never listed raw
    assert agent._context_line(db, uid, 7, memory) == echo.buddy_line(echo.latest(db, uid, now), 7)
    assert agent._context_line(db, uid, 8, memory).startswith("Pattern:")
    assert all(m["key"].startswith(agent._CAUSE_KEYS) for m in memory)


def test_local_report_runs_on_the_demo_week(db):
    from testing import echo_report

    echo_report.seed_demo(db)
    text = echo_report.report(db, last_week=True)
    assert "Prepare client report" in text and "Buddy's line: Context, never mention it" in text
    assert db.query(models.Memory).filter(models.Memory.key.startswith("echo.")).count() == 0  # read-only
