import asyncio
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

    def __init__(self, choice="surface_smallest_step", reply="Let's find one tiny first step on your report.", fail=False):
        self.calls, self.choice, self.reply, self.fail = [], choice, reply, fail

    async def __call__(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        if self.fail:
            raise llm.LLMError("groq is down")
        if kw.get("json_mode"):
            return json.dumps({"intervention": self.choice, "reason": "fits"})
        return self.reply

    @property
    def decide_calls(self):
        return [c for c in self.calls if c.get("json_mode")]

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


def test_emotion_tap_drives_state_and_single_candidate_skips_decide_call(api, fake_llm):
    _, h = register(api)
    t = make_task(api, h)
    tap_emotion(api, h, t, "tired")  # -> fatigue, whose only intervention is acknowledge_emotion

    body = api.post("/chat", json={"task_id": t, "message": "ugh"}, headers=h).json()
    assert body["state"] == "fatigue"
    assert body["intervention"] == "acknowledge_emotion"
    assert fake_llm.decide_calls == []  # nothing to choose between — no wasted LLM call
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
