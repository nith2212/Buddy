import asyncio
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

import models
from brain import agent, llm

INVITE = {"X-Invite-Code": "test-invite"}


def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def make_task(api, h, **extra):
    return api.post("/tasks", json={"title": "write report", **extra}, headers=h).json()["id"]


class FakeLLM:
    """Records every call; returns a decide-JSON for json_mode calls, prose otherwise."""

    def __init__(self, choice="surface_smallest_step", reply="Let's find one tiny first step on your report.",
                 fail=False, judge=("not_yet", None)):
        self.calls, self.choice, self.reply, self.fail, self.judge = [], choice, reply, fail, judge

    async def __call__(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        if self.fail:
            raise llm.LLMError("groq is down")
        if kw.get("json_mode"):
            if "CONFIRMS a specific cause" in messages[0]["content"]:
                verdict, cause = self.judge
                return json.dumps({"confirmed": verdict, "cause": cause})
            return json.dumps({"intervention": self.choice, "reason": "fits"})
        return self.reply

    @property
    def judge_calls(self):
        return [c for c in self.calls if c.get("json_mode") and "CONFIRMS a specific cause" in c["messages"][0]["content"]]

    @property
    def decide_calls(self):
        return [c for c in self.calls if c.get("json_mode") and c not in self.judge_calls]

    @property
    def write_calls(self):
        return [c for c in self.calls if not c.get("json_mode")]


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "complete", fake)
    return fake


def tap_emotion(api, h, task_id, value):
    api.post("/checkin/action", json={"task_id": task_id, "stage": "emotion", "value": value}, headers=h)


# ── /chat ───────────────────────────────────────────────────────────────────

def test_chat_happy_path_saves_turns_and_memory(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)

    r = api.post("/chat", json={"task_id": t, "message": "I can't get started"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "Let's find one tiny first step on your report."
    assert body["intervention"] == "surface_smallest_step"

    msgs = db.query(models.Message).filter(models.Message.task_id == t).order_by(models.Message.id).all()
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "I can't get started"), ("assistant", "Let's find one tiny first step on your report."),
    ]
    memory = {m.key: m.value for m in db.query(models.Memory).filter(models.Memory.user_id == user_id)}
    assert memory["buddy.last_intervention"] == "surface_smallest_step"
    assert memory["buddy.recent_interventions"] == "surface_smallest_step"


def test_emotion_tap_drives_state_and_forces_finding_the_cause(api, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    tap_emotion(api, h, t, "tired")  # -> fatigue

    body = api.post("/chat", json={"task_id": t, "message": "ugh"}, headers=h).json()
    assert body["state"] == "fatigue"
    assert body["intervention"] == "find_the_cause"
    assert fake_llm.decide_calls == []  # diagnosing is forced, no wasted choice
    assert len(fake_llm.write_calls) == 1


def test_recently_used_interventions_are_excluded(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)
    db.add(models.Memory(user_id=user_id, key="buddy.recent_interventions",
                         value="name_the_pattern,surface_smallest_step"))
    db.commit()

    api.post("/chat", json={"task_id": t, "message": "hi"}, headers=h)
    decide_prompt = fake_llm.decide_calls[0]["messages"][-1]["content"]
    assert "id: surface_smallest_step" not in decide_prompt
    assert "id: name_the_pattern" not in decide_prompt
    assert "id: acknowledge_emotion" in decide_prompt


def test_invalid_decide_choice_falls_back_to_first_candidate(api, monkeypatch):
    _, h = register(api)
    t = make_task(api, h)
    monkeypatch.setattr(llm, "complete", FakeLLM(choice="made_up_intervention"))

    r = api.post("/chat", json={"task_id": t, "message": "hi"}, headers=h)
    assert r.status_code == 200
    assert r.json()["intervention"] in {"acknowledge_emotion", "celebrate_progress", "make_deadline_real",
                                        "name_the_pattern", "surface_smallest_step"}


def test_groq_failure_returns_fallback_and_still_saves(api, db, monkeypatch):
    user_id, h = register(api)
    t = make_task(api, h)
    monkeypatch.setattr(llm, "complete", FakeLLM(fail=True))

    r = api.post("/chat", json={"task_id": t, "message": "hello?"}, headers=h)
    assert r.status_code == 200
    assert r.json()["reply"] == agent.FALLBACK_REPLY["chat"]
    assert r.json()["intervention"] is None
    assert db.query(models.Message).filter(models.Message.task_id == t).count() == 2
    keys = {m.key for m in db.query(models.Memory).filter(models.Memory.user_id == user_id)}
    assert "buddy.last_intervention" not in keys  # a fallback isn't a real intervention


def test_missing_groq_key_falls_back_instead_of_500(api):
    # conftest blanks GROQ_API_KEY and nothing is patched here: the real client raises LLMError.
    _, h = register(api)
    t = make_task(api, h)
    r = api.post("/chat", json={"task_id": t, "message": "hi"}, headers=h)
    assert r.status_code == 200 and r.json()["reply"] == agent.FALLBACK_REPLY["chat"]


def test_chat_history_is_sent_back_to_the_model(api, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "message": "first message"}, headers=h)
    api.post("/chat", json={"task_id": t, "message": "second message"}, headers=h)
    sent = fake_llm.write_calls[-1]["messages"]
    contents = [m["content"] for m in sent if m["role"] != "system"]
    assert contents == ["first message", "Let's find one tiny first step on your report.", "second message"]


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_chat_message_validation(api, fake_llm, message):
    _, h = register(api)
    t = make_task(api, h)
    assert api.post("/chat", json={"task_id": t, "message": message}, headers=h).status_code == 422


def test_chat_on_other_users_task_404s_and_calls_no_llm(api, fake_llm):
    _, a_h = register(api)
    _, b_h = register(api)
    b_task = make_task(api, b_h)
    assert api.post("/chat", json={"task_id": b_task, "message": "hi"}, headers=a_h).status_code == 404
    assert api.post("/initiate", json={"task_id": b_task}, headers=a_h).status_code == 404
    assert api.get(f"/chat/history?task_id={b_task}", headers=a_h).status_code == 404
    assert fake_llm.calls == []


@pytest.mark.parametrize("method,path,body", [
    ("post", "/chat", {"task_id": 1, "message": "hi"}),
    ("post", "/initiate", {"task_id": 1}),
    ("get", "/chat/history?task_id=1", None),
])
def test_chat_endpoints_require_auth(api, method, path, body):
    r = getattr(api, method)(path, **({"json": body} if body else {}))
    assert r.status_code == 401


# ── /initiate and history ───────────────────────────────────────────────────

def test_initiate_saves_only_buddys_turn(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    r = api.post("/initiate", json={"task_id": t}, headers=h)
    assert r.status_code == 200
    msgs = db.query(models.Message).filter(models.Message.task_id == t).all()
    assert [m.role for m in msgs] == ["assistant"]
    system_prompt = fake_llm.write_calls[0]["messages"][0]["content"]
    assert "You speak first" in system_prompt


def test_history_is_scoped_to_the_task(api, fake_llm):
    _, h = register(api)
    t1, t2 = make_task(api, h), make_task(api, h)
    api.post("/chat", json={"task_id": t1, "message": "about t1"}, headers=h)
    api.post("/chat", json={"task_id": t2, "message": "about t2"}, headers=h)
    history = api.get(f"/chat/history?task_id={t1}", headers=h).json()
    assert [turn["content"] for turn in history] == ["about t1", "Let's find one tiny first step on your report."]


# ── declined chat -> tailored closing notification ──────────────────────────

def test_declined_chat_gets_tailored_closing_in_one_llm_call(api, monkeypatch):
    _, h = register(api)
    t = make_task(api, h)
    fake = FakeLLM(reply="Rest counts too. I'll check in tomorrow.")
    monkeypatch.setattr(llm, "complete", fake)

    tap_emotion(api, h, t, "too_much")  # -> overwhelm, two candidate interventions
    r = api.post("/checkin/action", json={"task_id": t, "stage": "chat_opt_in", "value": "no"}, headers=h)

    assert r.json()["next_stage"] == "done"
    assert r.json()["notification"]["body"] == "Rest counts too. I'll check in tomorrow."
    assert fake.decide_calls == [] and len(fake.write_calls) == 1  # fast path: one call only
    assert fake.write_calls[0]["timeout"] <= 10


def test_declined_chat_with_no_state_makes_no_llm_call(api, monkeypatch):
    _, h = register(api)
    t = make_task(api, h)
    fake = FakeLLM()
    monkeypatch.setattr(llm, "complete", fake)

    r = api.post("/checkin/action", json={"task_id": t, "stage": "chat_opt_in", "value": "no"}, headers=h)
    assert r.json()["notification"]["body"] == agent.FALLBACK_REPLY["closing"]
    assert fake.calls == []


# ── llm.complete: retries, errors ───────────────────────────────────────────

class _Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload or {}, json.dumps(payload or {})

    def json(self):
        return self._payload


def _patch_post(monkeypatch, responses):
    calls = []

    async def fake_post(self, url, **kw):
        calls.append(kw)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    async def no_sleep(_):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    return calls


OK = _Resp(200, {"choices": [{"message": {"content": "  hello  "}}]})


def test_llm_retries_rate_limit_then_succeeds(monkeypatch):
    calls = _patch_post(monkeypatch, [_Resp(429), httpx.ConnectError("boom"), OK])
    assert asyncio.run(llm.complete([{"role": "user", "content": "hi"}])) == "hello"
    assert len(calls) == 3
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"


def test_llm_does_not_retry_client_errors(monkeypatch):
    calls = _patch_post(monkeypatch, [_Resp(400), OK])
    with pytest.raises(llm.LLMError):
        asyncio.run(llm.complete([{"role": "user", "content": "hi"}]))
    assert len(calls) == 1


def test_llm_gives_up_after_retries(monkeypatch):
    _patch_post(monkeypatch, [_Resp(503), _Resp(503), _Resp(503)])
    with pytest.raises(llm.LLMError):
        asyncio.run(llm.complete([{"role": "user", "content": "hi"}], retries=2))


def test_llm_json_mode_sets_response_format(monkeypatch):
    calls = _patch_post(monkeypatch, [OK])
    asyncio.run(llm.complete([{"role": "user", "content": "json please"}], json_mode=True))
    assert calls[0]["json"]["response_format"] == {"type": "json_object"}


# ── Step B: tapped reasons on /chat ─────────────────────────────────────────

@pytest.mark.parametrize("reason,state", [
    ("tired", "fatigue"), ("too_much", "overwhelm"), ("unclear", "ambiguity"),
    ("afraid", "perfectionism"), ("bored", "low_interest"),
])
def test_bare_reason_tap_makes_buddy_speak_first_in_that_state(api, db, fake_llm, reason, state):
    user_id, h = register(api)
    t = make_task(api, h)

    r = api.post("/chat", json={"task_id": t, "reason": reason}, headers=h)
    assert r.status_code == 200 and r.json()["state"] == state

    roles = [m["role"] for m in api.get(f"/chat/history?task_id={t}", headers=h).json()]
    assert roles == ["assistant"]  # the tap is not saved as something the user typed
    log = db.query(models.EmotionLog).filter_by(user_id=user_id, task_id=t).one()
    assert log.emotion == reason


def test_reason_with_message_runs_a_normal_chat_turn(api, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    body = api.post("/chat", json={"task_id": t, "reason": "afraid", "message": "what if it's bad"}, headers=h).json()
    assert body["state"] == "perfectionism"
    roles = [m["role"] for m in api.get(f"/chat/history?task_id={t}", headers=h).json()]
    assert roles == ["user", "assistant"]


@pytest.mark.parametrize("body", [{}, {"reason": "furious"}, {"message": "   "}])
def test_chat_rejects_missing_or_unknown_reason(api, fake_llm, body):
    _, h = register(api)
    t = make_task(api, h)
    assert api.post("/chat", json={"task_id": t, **body}, headers=h).status_code == 422


def test_reason_tap_cannot_touch_another_users_task(api, db, fake_llm):
    _, a = register(api)
    b_id, b = register(api)
    t = make_task(api, a)
    assert api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=b).status_code == 404
    assert db.query(models.EmotionLog).filter_by(user_id=b_id).count() == 0


# ── Step C: root cause first ────────────────────────────────────────────────

def system_of(call):
    return call["messages"][0]["content"]


def reasoning_of(db, task_id):
    last = (db.query(models.Message).filter_by(task_id=task_id, role="assistant")
            .order_by(models.Message.id.desc()).first())
    return json.loads(last.reasoning)


def memory_of(db, user_id):
    return {m.key: m.value for m in db.query(models.Memory).filter_by(user_id=user_id)}


def test_reason_tap_opens_with_one_question_and_no_advice(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)

    body = api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h).json()
    assert body["intervention"] == "find_the_cause" and body["state"] == "perfectionism"
    assert reasoning_of(db, t)["phase"] == "ask"
    assert fake_llm.decide_calls == [] and fake_llm.judge_calls == []  # nothing to judge yet
    assert "do NOT suggest any step" in " ".join(system_of(fake_llm.write_calls[0]).split())
    assert not any(k.startswith(("blocker.", "pattern.")) for k in memory_of(db, user_id))


def test_answer_gets_judged_and_unconfirmed_cause_is_not_saved(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)

    body = api.post("/chat", json={"task_id": t, "message": "my manager will read it"}, headers=h).json()
    assert len(fake_llm.judge_calls) == 1
    assert body["intervention"] == "find_the_cause" and reasoning_of(db, t)["phase"] == "guess"
    assert not any(k.startswith(("blocker.", "pattern.")) for k in memory_of(db, user_id))


def test_confirmed_cause_gets_first_move_and_is_saved_once(api, db, monkeypatch):
    user_id, h = register(api)
    t = make_task(api, h)
    fake = FakeLLM(judge=("yes", "afraid"))
    monkeypatch.setattr(llm, "complete", fake)
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)

    body = api.post("/chat", json={"task_id": t, "message": "yes, exactly that"}, headers=h).json()
    assert body["intervention"] == "surface_smallest_step"
    assert reasoning_of(db, t)["phase"] == "first_move"
    system = " ".join(system_of(fake.write_calls[-1]).split())
    assert "First move by cause" in system and "just confirmed what is in the way: fear that it won't" in system
    mem = memory_of(db, user_id)
    assert mem[f"blocker.task.{t}"] == "afraid" and mem["pattern.blocker.afraid"] == "1"

    # the cause is settled for this check-in: the next message is a normal turn and doesn't recount it
    api.post("/chat", json={"task_id": t, "message": "ok what next?"}, headers=h)
    assert memory_of(db, user_id)["pattern.blocker.afraid"] == "1"
    assert reasoning_of(db, t)["phase"] == "normal"


def test_yes_without_a_named_cause_uses_the_tapped_reason(api, db, monkeypatch):
    user_id, h = register(api)
    t = make_task(api, h)
    monkeypatch.setattr(llm, "complete", FakeLLM(judge=("yes", None)))
    api.post("/chat", json={"task_id": t, "reason": "bored"}, headers=h)
    api.post("/chat", json={"task_id": t, "message": "yeah it's just dull"}, headers=h)
    assert memory_of(db, user_id)[f"blocker.task.{t}"] == "bored"


def test_rejected_read_is_not_counted_and_next_read_must_differ(api, db, monkeypatch):
    user_id, h = register(api)
    t = make_task(api, h)
    fake = FakeLLM(judge=("no", None))
    monkeypatch.setattr(llm, "complete", fake)
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)
    api.post("/chat", json={"task_id": t, "message": "no, not really"}, headers=h)
    assert "was not right" in system_of(fake.write_calls[-1])
    assert not any(k.startswith(("blocker.", "pattern.")) for k in memory_of(db, user_id))


@pytest.mark.parametrize("bad", ["not json", json.dumps({"confirmed": "definitely"}), json.dumps(["yes"])])
def test_garbled_judge_output_never_saves_a_cause(api, db, monkeypatch, bad):
    user_id, h = register(api)
    t = make_task(api, h)

    class Garbled(FakeLLM):
        async def __call__(self, messages, **kw):
            out = await super().__call__(messages, **kw)
            return bad if kw.get("json_mode") else out

    monkeypatch.setattr(llm, "complete", Garbled())
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)
    r = api.post("/chat", json={"task_id": t, "message": "yes"}, headers=h)
    assert r.status_code == 200 and r.json()["intervention"] == "find_the_cause"
    assert not any(k.startswith("blocker.") for k in memory_of(db, user_id))


def test_judge_failure_does_not_save_and_still_replies(api, db, monkeypatch):
    user_id, h = register(api)
    t = make_task(api, h)

    class JudgeDown(FakeLLM):
        async def __call__(self, messages, **kw):
            if kw.get("json_mode"):
                raise llm.LLMError("rate limited")
            return await super().__call__(messages, **kw)

    monkeypatch.setattr(llm, "complete", JudgeDown())
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)
    r = api.post("/chat", json={"task_id": t, "message": "yes"}, headers=h)
    assert r.status_code == 200 and not r.json()["reply"] == agent.FALLBACK_REPLY["chat"]
    assert not any(k.startswith("blocker.") for k in memory_of(db, user_id))


def test_probing_stops_after_a_few_unconfirmed_turns(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "reason": "unclear"}, headers=h)
    for _ in range(agent.DIAGNOSE_MAX_BUDDY_TURNS):
        api.post("/chat", json={"task_id": t, "message": "dunno"}, headers=h)
    r = api.post("/chat", json={"task_id": t, "message": "still dunno"}, headers=h)
    assert r.status_code == 200
    assert reasoning_of(db, t)["phase"] == "normal"
    assert "Do not ask why again" in system_of(fake_llm.write_calls[-1])


@pytest.mark.parametrize("message", ["Okie, thanks", "ok thanks!", "got it", "will do 👍", "Thank you so much"])
def test_short_acknowledgment_gets_affirm_and_release(api, db, fake_llm, message):
    _, h = register(api)
    t = make_task(api, h)
    body = api.post("/chat", json={"task_id": t, "message": message}, headers=h).json()
    assert body["intervention"] == "affirm_and_release"
    assert fake_llm.decide_calls == [] and fake_llm.judge_calls == []  # no extra Groq calls
    assert reasoning_of(db, t)["phase"] == "release"
    assert "no step, no tip, no question" in " ".join(system_of(fake_llm.write_calls[0]).split())


@pytest.mark.parametrize("message", ["ok but how do I start?", "thanks, but I'm still stuck on the intro",
                                     "okay, I'll do it after dinner"])
def test_real_messages_are_not_mistaken_for_acknowledgments(api, db, fake_llm, message):
    _, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "message": message}, headers=h)
    assert reasoning_of(db, t)["phase"] != "release"


def test_okay_in_the_middle_of_diagnosing_is_judged_not_released(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)
    api.post("/chat", json={"task_id": t, "message": "okay"}, headers=h)
    assert len(fake_llm.judge_calls) == 1 and reasoning_of(db, t)["phase"] == "guess"


def test_polite_okay_after_ignored_checkins_is_not_released(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)
    db.query(models.Task).filter_by(id=t).update({"updated_at": datetime.now(timezone.utc) - timedelta(days=4)})
    for days in (3, 2):
        db.add(models.Event(user_id=user_id, task_id=t, type="checkin_sent", payload=None, source="system",
                            created_at=datetime.now(timezone.utc) - timedelta(days=days)))
    db.commit()
    body = api.post("/chat", json={"task_id": t, "message": "okay"}, headers=h).json()
    assert body["state"] == "avoidance" and body["intervention"] != "affirm_and_release"


def test_pattern_is_mentioned_only_after_three_confirmations(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)
    db.add(models.Memory(user_id=user_id, key="pattern.blocker.afraid", value="2", source="buddy"))
    db.commit()
    api.post("/chat", json={"task_id": t, "message": "hi"}, headers=h)
    assert "Pattern:" not in system_of(fake_llm.write_calls[-1])

    row = db.query(models.Memory).filter_by(user_id=user_id, key="pattern.blocker.afraid").one()
    row.value = "3"
    db.commit()
    api.post("/chat", json={"task_id": t, "message": "hi again"}, headers=h)
    system = system_of(fake_llm.write_calls[-1])
    assert "Pattern: fear that it won't be good enough has come up" in system
    assert "pattern.blocker.afraid" not in system and "blocker.task" not in system  # raw rows never shown


def test_one_users_pattern_never_reaches_another_users_prompt(api, db, fake_llm):
    a_id, a = register(api)
    _, b = register(api)
    db.add(models.Memory(user_id=a_id, key="pattern.blocker.afraid", value="9", source="buddy"))
    db.commit()
    t = make_task(api, b)
    api.post("/chat", json={"task_id": t, "message": "hi"}, headers=b)
    assert "Pattern:" not in system_of(fake_llm.write_calls[-1])


def test_confirmed_causes_are_wiped_by_delete_me(api, db, monkeypatch):
    user_id, h = register(api)
    t = make_task(api, h)
    monkeypatch.setattr(llm, "complete", FakeLLM(judge=("yes", "unclear")))
    api.post("/chat", json={"task_id": t, "reason": "unclear"}, headers=h)
    api.post("/chat", json={"task_id": t, "message": "yes that's it"}, headers=h)
    assert any(k.startswith("blocker.") for k in memory_of(db, user_id))

    assert api.delete("/me", headers=h).status_code == 204
    db.expire_all()
    assert memory_of(db, user_id) == {}


def test_no_database_connection_is_held_while_waiting_on_groq(api, monkeypatch):
    from db import engine
    _, h = register(api)
    t = make_task(api, h)
    held = []

    class Watcher(FakeLLM):
        async def __call__(self, messages, **kw):
            held.append(engine.pool.checkedout())
            return await super().__call__(messages, **kw)

    monkeypatch.setattr(llm, "complete", Watcher())
    api.post("/chat", json={"task_id": t, "reason": "afraid"}, headers=h)
    assert held and all(n == 0 for n in held)


def test_chat_text_is_never_logged(api, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    _, h = register(api)
    t = make_task(api, h)
    secret = "my-very-private-sentence-xyz"
    monkeypatch.setattr(llm, "complete", FakeLLM(fail=True))  # the fallback path logs too
    api.post("/chat", json={"task_id": t, "message": secret}, headers=h)
    monkeypatch.setattr(llm, "complete", FakeLLM(choice="nonsense"))  # unusable decide choice logs too
    api.post("/chat", json={"task_id": t, "message": secret}, headers=h)
    assert secret not in caplog.text
