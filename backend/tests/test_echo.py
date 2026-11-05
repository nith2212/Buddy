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


# ── E2: how they react to Buddy's moves ───────────────────────────────────────────

def buddy(db, task, at, state, stage, read=None):
    """One Buddy framework reply, with the reading of the user message it answered."""
    flow = {"state": state, "stage": stage, "tries": 1, "read": None if read is None else {"kind": read}}
    db.add(models.Message(user_id=task.user_id, task_id=task.id, role="assistant", content="(reply)",
                          reasoning=json.dumps({"flow": flow}), created_at=at))
    db.commit()


def tick(db, task, at):
    db.add(models.Subtask(user_id=task.user_id, task_id=task.id, title="a step", done=True,
                          created_at=at, updated_at=at))
    db.commit()


def test_a_tiny_move_they_took_and_the_progress_after_it(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=START - timedelta(days=3))
    at = START + timedelta(days=2)
    buddy(db, t, at, "overwhelm", "open")
    buddy(db, t, at + timedelta(minutes=1), "overwhelm", "micro", read="idk")
    buddy(db, t, at + timedelta(minutes=2), "overwhelm", "micro", read="answer")   # "that's all?": same move
    buddy(db, t, at + timedelta(minutes=3), "overwhelm", "release", read="accept")
    tick(db, t, at + timedelta(hours=5))
    r = echo.week_facts(db, uid, START, END)["reactions"]
    assert r["too_much.tiny_move"]["offered"] == 1                      # counted once, judged on the last time
    assert r["too_much.tiny_move"]["took"] == 1 and r["too_much.tiny_move"]["progress_after"] == 1
    assert r["too_much.asked_their_step"]["idk"] == 1                   # "what's the smallest first move?" -> idk


def test_own_plans_offers_and_silence(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=START - timedelta(days=3))
    at = START + timedelta(days=1)
    buddy(db, t, at, "perfectionism", "offer")
    buddy(db, t, at + timedelta(minutes=1), "perfectionism", "release", read="own_plan")
    buddy(db, t, at + timedelta(days=1), "fatigue", "offer")
    buddy(db, t, at + timedelta(days=1, minutes=1), "fatigue", "move", read="idk")      # "you say"
    buddy(db, t, at + timedelta(days=3), "low_interest", "lighten")                      # never answered
    buddy(db, t, at + timedelta(days=4), "perfectionism", "reframe")
    buddy(db, t, at + timedelta(days=4, hours=13), "perfectionism", "release", read="accept")  # too late
    r = echo.week_facts(db, uid, START, END)["reactions"]
    assert (r["afraid.offer"]["own_plan"], r["tired.offer"]["wanted_move"]) == (1, 1)
    assert r["tired.tiny_move"]["no_reply"] == 1
    assert r["bored.lighter"]["no_reply"] == 1 and r["afraid.rough_version"]["no_reply"] == 1
    assert all(row["progress_after"] == 0 for row in r.values())


def test_moves_outside_the_week_and_other_users_are_not_counted(api, db):
    a, _ = register(api)
    b, _ = register(api)
    ta = add_task(db, a, created=START - timedelta(days=10))
    tb = add_task(db, b, created=START - timedelta(days=10))
    buddy(db, ta, START - timedelta(days=1), "overwhelm", "micro")   # last week
    buddy(db, tb, START + timedelta(days=1), "overwhelm", "micro")   # someone else
    assert echo.week_facts(db, a, START, END)["reactions"] == {}


def test_checkin_replies_and_days_active(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=START - timedelta(days=10))
    checkin(db, t, START + timedelta(days=1))
    db.add_all([models.EmotionLog(user_id=uid, task_id=t.id, emotion="tired", chat_opt_in=True,
                                  created_at=START + timedelta(days=1, hours=1)),
                models.EmotionLog(user_id=uid, task_id=t.id, emotion="unclear", chat_opt_in=False,
                                  created_at=START + timedelta(days=4))])
    db.commit()
    facts = echo.week_facts(db, uid, START, END)
    assert facts["checkins"] == {"sent": 1, "ignored": 0, "chat_yes": 1, "chat_no": 1}
    # India-time days (the check-in itself is not activity): Tue 3 Nov just after midnight, Thu 5 Nov
    assert facts["days_active"] == ["2026-11-03", "2026-11-05"]


# ── the user's Echo page: GET /echo/week ─────────────────────────────────────────

PAGE_NOW = END + timedelta(days=3)   # Wednesday of the week after END
PAGE_START = END


def test_page_shows_wins_days_and_a_kind_line(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=PAGE_START - timedelta(days=10))
    tap(db, t, PAGE_START + timedelta(days=1), "too_much")
    tick(db, t, PAGE_START + timedelta(days=1, hours=2))           # got going after the tap
    page = echo.this_week(db, uid, PAGE_NOW)
    assert page["wins"] == {"tasks_finished": 0, "steps_done": 1, "started_when_hard": 1}
    assert page["line"] == "You got going once this week, even when it felt hard."
    assert [d["date"] for d in page["days"]][0] == "2026-11-09" and len(page["days"]) == 7   # Mon..Sun
    # the tap is Monday 23:00 India time, the tick 2 hours later is Tuesday
    assert [d["active"] for d in page["days"]] == [True, True, False, False, False, False, False]
    assert page["total_days"] == 3                     # plus the day the task was made


def test_page_never_shows_ignores_untouched_days_or_postpones(api, db):
    uid, h = register(api)
    t = add_task(db, uid, created=PAGE_START - timedelta(days=30))
    for d in (1, 2):
        checkin(db, t, PAGE_START + timedelta(days=d))
    db.add(models.Event(user_id=uid, task_id=t.id, type="postponed", created_at=PAGE_START + timedelta(days=1)))
    db.commit()
    page = echo.this_week(db, uid, PAGE_NOW)
    text = json.dumps(page).lower()
    assert not any(w in text for w in ("ignor", "untouched", "postpone", "checkin", "check-in", "%"))
    assert page["line"] == echo.QUIET_LINE
    assert api.get("/echo/week", headers=h).status_code == 200


def test_page_says_what_helped_only_for_causes_confirmed_three_times(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=PAGE_START - timedelta(days=10))
    at = PAGE_START + timedelta(days=1)
    buddy(db, t, at, "perfectionism", "reframe")
    buddy(db, t, at + timedelta(minutes=1), "perfectionism", "release", read="accept")
    tick(db, t, at + timedelta(hours=3))
    db.add(models.Memory(user_id=uid, key="pattern.blocker.afraid", value="2"))
    db.commit()
    assert echo.this_week(db, uid, PAGE_NOW)["helped"] == []        # not earned yet
    db.query(models.Memory).filter_by(key="pattern.blocker.afraid").one().value = "3"
    db.commit()
    helped = echo.this_week(db, uid, PAGE_NOW)["helped"]
    assert helped == [{"cause": "afraid", "move": "rough_version", "times": 1,
                       "text": "Worrying it won't be good enough has come up a few times. "
                               "A rough first version helped you get going once."}]


def test_declined_moves_never_count_as_helped(api, db):
    uid, _ = register(api)
    t = add_task(db, uid, created=PAGE_START - timedelta(days=10))
    at = PAGE_START + timedelta(days=1)
    buddy(db, t, at, "low_interest", "lighten")
    buddy(db, t, at + timedelta(minutes=1), "low_interest", "offer", read="reject")
    tick(db, t, at + timedelta(hours=3))
    db.add(models.Memory(user_id=uid, key="pattern.blocker.bored", value="5"))
    db.commit()
    assert echo.this_week(db, uid, PAGE_NOW)["helped"] == []


def test_page_is_only_the_callers_and_works_with_no_tasks(api, db):
    a, ha = register(api)
    b, hb = register(api)
    t = add_task(db, b, created=datetime.now(UTC) - timedelta(days=1), status="done", completed=datetime.now(UTC))
    assert api.get("/echo/week").status_code == 401
    mine = api.get("/echo/week", headers=ha).json()
    assert mine["wins"] == {"tasks_finished": 0, "steps_done": 0, "started_when_hard": 0}
    assert mine["total_days"] == 0 and mine["line"] == echo.QUIET_LINE and mine["helped"] == []
    assert api.get("/echo/week", headers=hb).json()["wins"]["tasks_finished"] == 1


# ── E3: Buddy adapts (owner-approved rules) ───────────────────────────────────────

@pytest.mark.parametrize("prof,state,stage,tiny,want", [
    # brings their own plan (offers + "what's your step?" both count)
    ({"afraid.offer": {"own_plan": 2}, "unclear.asked_their_step": {"own_plan": 1}},
     "perfectionism", "offer", "reframe", (None, "own_plan_first")),
    ({"afraid.offer": {"own_plan": 2}}, "perfectionism", "offer", "reframe", (None, None)),       # only twice
    ({"afraid.offer": {"own_plan": 3, "wanted_move": 4}}, "perfectionism", "offer", "reframe", (None, None)),
    # always asks for Buddy's move, never their own: straight to the tiny move
    ({"tired.offer": {"wanted_move": 3}}, "fatigue", "offer", "move", ("move", "move_first")),
    ({"tired.offer": {"wanted_move": 3, "own_plan": 1}}, "fatigue", "offer", "move", (None, None)),
    ({"tired.offer": {"wanted_move": 3}, "tired.tiny_move": {"helped": 3}}, "fatigue", "offer", "move",
     ("move", "move_first+lean_on_helped")),
    # what helped, per cause
    ({"afraid.rough_version": {"helped": 3}}, "perfectionism", "reframe", "reframe", (None, "lean_on_helped")),
    ({"afraid.rough_version": {"helped": 3}}, "overwhelm", "micro", "micro", (None, None)),       # other cause
    # what they turn down
    ({"bored.lighter": {"declined": 3}}, "low_interest", "lighten", "lighten", (None, "avoid_declined")),
    ({"bored.lighter": {"declined": 3, "took": 1}}, "low_interest", "lighten", "lighten", (None, None)),
    ({}, "overwhelm", "micro", "micro", (None, None)),
])
def test_adapt_rules_switch_on_only_at_three(prof, state, stage, tiny, want):
    reroute, hint, rule = echo.adapt(prof, state, stage, tiny)
    assert (reroute, rule) == want
    assert (hint is None) == (rule in (None, "move_first"))
    assert hint is None or not any(ch.isdigit() for ch in hint)    # never a count


def test_lean_hint_names_the_move_and_may_say_it_softly():
    _, hint, _ = echo.adapt({"afraid.rough_version": {"helped": 4}}, "perfectionism", "reframe", "reframe")
    assert "a rough first version" in hint and "softly" in hint


def test_profile_sums_saved_weeks_and_this_week_so_far(api, db):
    uid, _ = register(api)
    now = datetime.now(UTC)
    db.add(models.Memory(user_id=uid, key="echo.week.2026-10-25", source="echo",
                         value=json.dumps({"reactions": {"afraid.offer": {"offered": 2, "own_plan": 2}}})))
    db.commit()
    t = add_task(db, uid, created=now - timedelta(days=30))
    buddy(db, t, now - timedelta(minutes=5), "perfectionism", "offer")
    buddy(db, t, now - timedelta(minutes=4), "perfectionism", "release", read="own_plan")
    prof = echo.profile(db, uid, now)
    assert prof["afraid.offer"]["own_plan"] == 3
    assert echo.adapt(prof, "perfectionism", "offer", "reframe")[2] == "own_plan_first"
    other, _ = register(api)
    assert echo.profile(db, other, now) == {}
