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


READ_MARK = "You read one message from a user"


class FakeLLM:
    """
    Records every call. Read calls (the framework's "read their message") return the next of
    `reads` (the last one repeats); other JSON calls return a decide choice; the rest is prose.
    """

    def __init__(self, choice="surface_smallest_step", reply="Let's find one tiny first step on your report.",
                 fail=False, reads=None):
        self.calls, self.choice, self.reply, self.fail = [], choice, reply, fail
        self.reads = list(reads or [{"kind": "answer"}])

    async def __call__(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        if self.fail:
            raise llm.LLMError("groq is down")
        if kw.get("json_mode"):
            if READ_MARK in messages[0]["content"]:
                return json.dumps(self.reads.pop(0) if len(self.reads) > 1 else self.reads[0])
            return json.dumps({"intervention": self.choice, "reason": "fits"})
        return self.reply

    @property
    def read_calls(self):
        return [c for c in self.calls if c.get("json_mode") and READ_MARK in c["messages"][0]["content"]]

    @property
    def decide_calls(self):
        return [c for c in self.calls if c.get("json_mode") and c not in self.read_calls]

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


def test_emotion_tap_runs_that_states_framework(api, fake_llm):
    fake_llm.reply = "A long day on your report, so rest is fine. I'm here when you're ready."
    _, h = register(api)
    t = make_task(api, h)
    tap_emotion(api, h, t, "tired")  # -> fatigue

    body = api.post("/chat", json={"task_id": t, "message": "ugh, long day"}, headers=h).json()
    assert body["state"] == "fatigue" and body["intervention"] == "fatigue:rest"
    assert fake_llm.decide_calls == []  # the framework picks the stage: no decide call
    assert len(fake_llm.read_calls) == 1 and len(fake_llm.write_calls) == 1


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


def test_chat_history_is_sent_back_to_the_model(api, monkeypatch):
    class Varying(FakeLLM):
        async def __call__(self, messages, **kw):
            out = await super().__call__(messages, **kw)
            if kw.get("json_mode"):
                return out
            return ["Let's start with the report outline.", "Pick the shortest section of the report to open.",
                    "What would the first line of the report say?"][len(self.write_calls) % 3 - 1]

    fake = Varying()
    monkeypatch.setattr(llm, "complete", fake)
    _, h = register(api)
    t = make_task(api, h)
    first = api.post("/chat", json={"task_id": t, "message": "first message"}, headers=h).json()["reply"]
    api.post("/chat", json={"task_id": t, "message": "second message"}, headers=h)
    sent = fake.write_calls[-1]["messages"]
    contents = [m["content"] for m in sent if m["role"] != "system"]
    assert contents == ["first message", first, "second message"]


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


def start(api, h, t, reason):
    """Tap a reason: Buddy speaks first, on the framework's opening stage."""
    return api.post("/chat", json={"task_id": t, "reason": reason}, headers=h).json()


def say(api, h, t, message):
    return api.post("/chat", json={"task_id": t, "message": message}, headers=h).json()


def flow_of(db, t):
    return reasoning_of(db, t)["flow"]


def causes_of(db, user_id):
    return {k: v for k, v in memory_of(db, user_id).items() if k.startswith(("blocker.", "pattern."))}


def test_reason_tap_opens_on_the_frameworks_first_stage(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)
    body = start(api, h, t, "afraid")
    assert body["state"] == "perfectionism" and body["intervention"] == "perfectionism:open"
    assert fake_llm.decide_calls == [] and fake_llm.read_calls == []  # nothing to read yet
    system = " ".join(system_of(fake_llm.write_calls[0]).split())
    assert "ask what feels risky about this task" in system and "sweet, peppy, kind friend" in system
    assert "First move by cause" not in system and "core_buddy_philosophy" not in system  # old docs not sent
    assert causes_of(db, user_id) == {}


def test_the_reading_moves_the_stage_and_notes_their_words(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "answer", "fact": "others will judge it"}])
    monkeypatch.setattr(llm, "complete", fake)
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    assert say(api, h, t, "people will think it's messy")["intervention"] == "perfectionism:confirm"
    assert flow_of(db, t)["notes"] == {"worry": "others will judge it"}
    assert "- worry: others will judge it" in system_of(fake.write_calls[-1])
    assert causes_of(db, user_id) == {}  # an answer is not a confirmation


def test_confirming_saves_the_cause_once(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "answer"}, {"kind": "confirm", "cause": "afraid"}, {"kind": "confirm"}])
    monkeypatch.setattr(llm, "complete", fake)
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    say(api, h, t, "people will think it's messy")
    assert say(api, h, t, "yeah that's it")["intervention"] == "perfectionism:reframe"
    assert causes_of(db, user_id) == {f"blocker.task.{t}": "afraid", "pattern.blocker.afraid": "1"}
    assert say(api, h, t, "haha okay")["intervention"] == "perfectionism:release"
    assert causes_of(db, user_id)["pattern.blocker.afraid"] == "1"  # not counted twice


def test_their_own_plan_is_released_and_backed_as_said(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "own_plan", "fact": "polish the README first"}])
    monkeypatch.setattr(llm, "complete", fake)
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    assert say(api, h, t, "nah I'd rather polish the README first")["intervention"] == "perfectionism:release"
    system = " ".join(system_of(fake.write_calls[-1]).split())
    assert "never shrink, change or add to it" in system and "their plan: polish the README first" in system
    assert "no question" in system


def test_idk_is_caught_without_a_model_call_and_narrows(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "unclear")
    say(api, h, t, "idk honestly")
    assert fake_llm.read_calls == []
    assert flow_of(db, t)["stage"] == "open" and flow_of(db, t)["modifier"] == "idk"
    assert "Don't ask the same question again" in system_of(fake_llm.write_calls[-1])


def test_unsure_stays_on_the_stage_and_says_it_differently(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "unsure"}])
    monkeypatch.setattr(llm, "complete", fake)
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    say(api, h, t, "idk bro")  # -> narrow
    say(api, h, t, "yeah, maybe")
    assert flow_of(db, t)["stage"] == "narrow" and flow_of(db, t)["modifier"] == "unsure"
    assert "They half-agreed or hedged" in system_of(fake.write_calls[-1])


@pytest.mark.parametrize("bad", ["not json", json.dumps({"kind": "definitely"}), json.dumps(["yes"])])
def test_a_garbled_read_stays_on_the_stage_and_saves_nothing(api, db, monkeypatch, bad):
    class Garbled(FakeLLM):
        async def __call__(self, messages, **kw):
            out = await super().__call__(messages, **kw)
            return bad if kw.get("json_mode") else out

    monkeypatch.setattr(llm, "complete", Garbled())
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    r = api.post("/chat", json={"task_id": t, "message": "yes exactly"}, headers=h)
    assert r.status_code == 200 and r.json()["intervention"] == "perfectionism:open"
    assert flow_of(db, t)["modifier"] == "unclear" and causes_of(db, user_id) == {}


def test_a_failed_read_still_replies(api, db, monkeypatch):
    class ReadDown(FakeLLM):
        async def __call__(self, messages, **kw):
            if kw.get("json_mode"):
                raise llm.LLMError("rate limited")
            return await super().__call__(messages, **kw)

    monkeypatch.setattr(llm, "complete", ReadDown())
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    r = say(api, h, t, "yes exactly")
    assert r["reply"] != agent.FALLBACK_REPLY["chat"] and causes_of(db, user_id) == {}


def test_after_two_tries_on_a_stage_buddy_offers_the_choice(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "unclear")
    say(api, h, t, "dunno")
    assert flow_of(db, t)["stage"] == "open"
    say(api, h, t, "dunno")
    assert flow_of(db, t)["stage"] == "offer"


def test_offer_that_hands_out_a_step_is_replaced_by_the_fixed_offer(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "unclear")
    say(api, h, t, "dunno")
    body = say(api, h, t, "dunno")  # the fake writer hands out a step, not the choice
    assert body["reply"] == agent.OFFER_FALLBACK and reasoning_of(db, t)["checks"]["offer_template"] is True


def test_a_different_cause_switches_the_framework_and_is_saved(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "new_cause", "cause": "tired"}])
    monkeypatch.setattr(llm, "complete", fake)
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "unclear")
    body = say(api, h, t, "honestly I'm just exhausted today")
    assert body["state"] == "fatigue" and body["intervention"] == "fatigue:rest"
    assert causes_of(db, user_id)[f"blocker.task.{t}"] == "tired"
    assert "They since said what's really in the way: being tired" in system_of(fake.write_calls[-1])


def test_something_bigger_than_work_steps_back_and_stays_back(api, db, fake_llm):
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")
    assert say(api, h, t, "it's not the task, I can't stop crying lately")["intervention"] == "perfectionism:step_back"
    assert fake_llm.read_calls == []  # caught by pattern, no waiting on a model
    assert "you're a task companion and not the right support" in system_of(fake_llm.write_calls[-1])
    assert say(api, h, t, "yeah")["intervention"] == "perfectionism:step_back"
    assert causes_of(db, user_id) == {}


def test_a_flavor_picks_the_branch(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "answer"}, {"kind": "confirm", "cause": "bored", "flavor": "pointless"}])
    monkeypatch.setattr(llm, "complete", fake)
    user_id, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "bored")
    assert say(api, h, t, "client requirements")["intervention"] == "low_interest:narrow"
    assert say(api, h, t, "pointless")["intervention"] == "low_interest:purpose"
    assert causes_of(db, user_id)[f"blocker.task.{t}"] == "bored"


def test_still_talking_after_the_release_gets_a_followup(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "own_plan"}, {"kind": "answer"}])
    monkeypatch.setattr(llm, "complete", fake)
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "too_much")
    say(api, h, t, "I'll open the repo")
    assert say(api, h, t, "but I still don't know how")["intervention"] == "overwhelm:followup"
    assert say(api, h, t, "thanks bye")["intervention"] == "overwhelm:release"


def test_a_bare_okay_to_a_question_is_read_not_released(api, db, fake_llm):
    fake_llm.reply = "What feels risky about the report?"
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "afraid")  # Buddy asked a question
    say(api, h, t, "okay")
    assert len(fake_llm.read_calls) == 1 and flow_of(db, t)["stage"] != "release"


def test_due_time_and_task_name_only_on_the_first_buddy_turn(api, db, fake_llm):
    _, h = register(api)
    t = make_task(api, h, due_date=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat())
    start(api, h, t, "afraid")
    say(api, h, t, "people will see it")
    first, last = system_of(fake_llm.write_calls[0]), system_of(fake_llm.write_calls[-1])
    assert "due in about 3 days" in first and "name the task naturally" in first
    assert "due in" not in last and "Don't restate the task's name" in last
    assert "no_task_reference" not in reasoning_of(db, t)["checks"]["soft"]


def test_a_new_tap_starts_a_new_session_that_remembers_last_time(api, db, monkeypatch):
    fake = FakeLLM(reads=[{"kind": "answer", "fact": "a gallery app"}])
    monkeypatch.setattr(llm, "complete", fake)
    _, h = register(api)
    t = make_task(api, h)
    start(api, h, t, "unclear")
    say(api, h, t, "a gallery app")
    start(api, h, t, "unclear")  # new tap = new session, back to the opener
    assert flow_of(db, t)["stage"] == "open" and flow_of(db, t)["notes"] == {}
    assert "Last time on this task: goal: a gallery app" in system_of(fake.write_calls[-1])
    sent = [m["content"] for m in fake.write_calls[-1]["messages"][1:]]
    assert "a gallery app" not in sent  # the old session's messages are not replayed


@pytest.mark.parametrize("message", ["Okie, thanks", "ok thanks!", "got it", "will do 👍", "Thank you so much"])
def test_short_acknowledgment_gets_affirm_and_release(api, db, fake_llm, message):
    _, h = register(api)
    t = make_task(api, h)
    body = api.post("/chat", json={"task_id": t, "message": message}, headers=h).json()
    assert body["intervention"] == "affirm_and_release"
    assert fake_llm.decide_calls == [] and fake_llm.read_calls == []  # no extra Groq calls
    assert reasoning_of(db, t)["phase"] == "release"
    assert "no step, no tip, no question" in " ".join(system_of(fake_llm.write_calls[0]).split())


@pytest.mark.parametrize("message", ["ok but how do I start?", "thanks, but I'm still stuck on the intro",
                                     "okay, I'll do it after dinner"])
def test_real_messages_are_not_mistaken_for_acknowledgments(api, db, fake_llm, message):
    _, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "message": message}, headers=h)
    assert reasoning_of(db, t)["phase"] != "release"


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
    monkeypatch.setattr(llm, "complete", FakeLLM(reads=[{"kind": "own_plan"}]))
    start(api, h, t, "unclear")
    say(api, h, t, "I'll set up expo")
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


# ── a reply must not repeat the one before it ───────────────────────────────

def test_check_reply_flags_a_repeat_of_the_previous_reply():
    from brain.reply_check import check_reply
    prev = "Finishing echo is due in about 27 hours. Is it more that you're not sure which feature to tackle first?"
    same = check_reply(prev, max_sentences=3, max_questions=1, user_message=None, anchor_words={"echo"},
                       previous_reply=prev)
    assert "repeats_previous" in same.soft
    fresh = check_reply("Which of those features would you ship first if you had to pick one?", max_sentences=3,
                        max_questions=1, user_message=None, anchor_words=set(), previous_reply=prev)
    assert "repeats_previous" not in fresh.soft


def test_a_repeated_draft_gets_one_rewrite_with_the_reason(api, monkeypatch):
    class Repeats(FakeLLM):
        async def __call__(self, messages, **kw):
            out = await super().__call__(messages, **kw)
            if kw.get("json_mode") or any("already said this" in m["content"] for m in messages):
                return out if kw.get("json_mode") else "Which part of the report would you start with if you had to pick?"
            return "Writing the report is due soon. Which part feels biggest?"

    fake = Repeats()
    monkeypatch.setattr(llm, "complete", fake)
    _, h = register(api)
    t = make_task(api, h)
    api.post("/chat", json={"task_id": t, "message": "hi"}, headers=h)
    r = api.post("/chat", json={"task_id": t, "message": "not sure"}, headers=h).json()
    assert r["reply"] == "Which part of the report would you start with if you had to pick?"


def test_glued_sentences_get_a_space(api, monkeypatch):
    monkeypatch.setattr(llm, "complete", FakeLLM(reply="Open the report and write one line.Got it. Shout if you hit a snag."))
    _, h = register(api)
    t = make_task(api, h)
    reply = api.post("/chat", json={"task_id": t, "message": "ok so what now"}, headers=h).json()["reply"]
    assert "line. Got it." in reply


def test_reply_opening_the_same_way_is_flagged():
    from brain.reply_check import check_reply
    kw = dict(max_sentences=3, max_questions=1, user_message=None, anchor_words=set())
    prev = "You're working on finishing Buddy, and you're worried about tests."
    assert "repeats_opening" in check_reply("You're working on finishing Buddy, so open the doc.", previous_reply=prev, **kw).soft
    assert "repeats_opening" not in check_reply("Open the doc for Buddy and jot one line.", previous_reply=prev, **kw).soft


def test_offer_and_guess_shape_checks():
    from brain.reply_check import check_reply
    kw = dict(max_sentences=3, max_questions=1, user_message=None, anchor_words=set())
    assert "offer_shape" in check_reply("Open a blank file and write one line.", phase="offer", **kw).soft
    assert "offer_shape" not in check_reply(
        "You said it feels risky. Want a tiny first move, or do you already know what you'll do?", phase="offer", **kw).soft
    assert "guess_shape" in check_reply("What part feels most unclear to you?", phase="guess", **kw).soft
    assert "guess_shape" not in check_reply("Is it more that the layout feels huge?", phase="guess", **kw).soft
