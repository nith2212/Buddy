import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import models
from brain import agent, llm, playbook
from brain.reply_check import check_reply, salient_words

INVITE = {"X-Invite-Code": "test-invite"}
ANCHORS = salient_words("Finish UI DESIGN in figma", "Learn figma basics")  # {design, figma, learn, basics, ...}


def check(reply, *, mode="chat", user_message=None, anchors=ANCHORS):
    return check_reply(
        reply, max_sentences=agent.MAX_SENTENCES[mode], max_questions=agent.MAX_QUESTIONS[mode],
        user_message=user_message, anchor_words=anchors,
        max_chars=agent.CLOSING_MAX_CHARS if mode == "closing" else None,
    )


# ── check_reply: hard violations ────────────────────────────────────────────

@pytest.mark.parametrize("reply", [
    "That sounds genuinely draining. Pick one small piece of figma.",
    "Okay. That sounds exhausting, so try the figma basics.",          # mid-reply sentence start
    "It's totally understandable. Open figma and look at one frame.",
    "It's okay to feel stuck. Start with the figma basics.",
    "I hear you. Try one figma tutorial.",
    "Hey there! How's the figma design going?",
])
def test_stock_sympathy_filler_is_a_hard_violation(reply):
    assert "stock_phrase" in check(reply).hard


@pytest.mark.parametrize("reply", [
    "It sounds like you're feeling a bit overwhelmed. Open figma and add one frame.",
    "Sounds like you're ready to dive in. Open the figma design.",
    "You're juggling a lot, and it sounds like the figma design is the heavy part.",
])
def test_the_whole_sounds_like_family_is_blocked_not_just_that_sounds(reply):
    assert "stock_phrase" in check(reply).hard


@pytest.mark.parametrize("reply", [
    "Do one small figma piece before 9pm.",
    "Finish the figma design by 9 p.m. tonight.",
    "Try the figma basics until 21:30.",
    "Let's check in at 4:30 on the figma design.",
])
def test_invented_clock_time_is_a_hard_violation(reply):
    assert "clock_time" in check(reply).hard


def test_a_clock_time_the_user_said_themselves_is_allowed():
    assert check("Okay, figma basics before 9 p.m. then.", user_message="I can do it before 9pm").hard == ()


def test_relative_wording_is_fine():
    assert check("The figma design is due in about 3 days, so one small piece tonight is plenty.").hard == ()


# ── check_reply: soft violations ────────────────────────────────────────────

def test_two_questions_is_soft():
    assert "too_many_questions" in check("What's blocking the figma design? Want to start with the basics?").soft


def test_closing_must_not_ask_a_question():
    assert "too_many_questions" in check("Want to look at the figma design later?", mode="closing").soft


def test_too_many_sentences_is_soft():
    reply = "Figma design time. Open it. Pick a frame. Draw a box. Done."
    assert "too_long" in check(reply).soft


def test_closing_over_the_character_limit_is_soft():
    assert "too_long" in check("Figma design. " + "x" * 220, mode="closing").soft


def test_invented_resources_are_soft_violations():
    assert "invented_resource" in check("Spend a few minutes watching a quick intro video on figma.").soft


def test_a_resource_the_user_mentioned_is_not_invented():
    v = check("Sure, watch the tutorial and then try one frame in figma.", user_message="I'll watch a tutorial")
    assert "invented_resource" not in v.soft


@pytest.mark.parametrize("reply", [
    "Clean my room: pick up one item.",
    "Finish UI DESIGN in figma: open a blank file.",
])
def test_task_name_used_as_a_label_is_soft(reply):
    assert "label_style" in check(reply, anchors=salient_words("Clean my room", "Finish UI DESIGN in figma")).soft


def test_a_colon_later_in_the_reply_is_fine():
    assert "label_style" not in check("Your figma design is due soon, so try this: one frame.").soft


def test_reply_that_ignores_the_task_is_soft():
    assert "no_task_reference" in check("Take one small step and see how it feels.").soft


def test_mentioning_an_open_step_counts_as_naming_the_task():
    assert check("Maybe start with the basics, just ten minutes.").soft == ()


def test_good_reply_has_no_violations():
    v = check("The figma design is due soon, so open it and rough out one frame. Which frame is the easiest?")
    assert not v.any


def test_no_anchor_words_skips_the_reference_check():
    assert check("Take one small step.", anchors=set()).soft == ()


def test_salient_words_drops_generic_and_short_words():
    assert salient_words("Finish the UI design in figma") == {"design", "figma"}


# ── the context Buddy is given ──────────────────────────────────────────────

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def make_task(**kw):
    return models.Task(id=1, user_id="u", title="Finish UI DESIGN in figma", status="open", **kw)


def make_step(title, done=False, position=0):
    return models.Subtask(id=position + 1, user_id="u", task_id=1, title=title, done=done, position=position)


@pytest.mark.parametrize("due,expected", [
    (None, "no due date"),
    (NOW + timedelta(hours=14), "due in about 14 hours"),
    (NOW + timedelta(days=3), "due in about 3 days"),
    (NOW + timedelta(minutes=20), "due in less than an hour"),
    (NOW - timedelta(days=2), "overdue by about 2 days"),
    (NOW - timedelta(hours=5), "overdue by about 5 hours"),
])
def test_due_phrase_is_relative_never_a_clock_time(due, expected):
    assert agent._due_phrase(due, NOW) == expected


def test_situation_has_real_progress_facts_and_no_clock_time():
    steps = [make_step("Learn figma basics", done=True, position=0), make_step("Make a rough sketch", position=1)]
    text = agent._situation_text(make_task(due_date=NOW + timedelta(days=3)), steps, "too_much", None, NOW)
    assert 'Task: "Finish UI DESIGN in figma"' in text
    assert "Timing: due in about 3 days" in text
    assert 'Step done: "Learn figma basics"' in text
    assert "Open steps: Make a rough sketch" in text
    assert "UTC" not in text and not re.search(r"\d:\d\d", text)


def test_situation_with_no_progress_says_none_so_the_model_has_nothing_to_praise():
    text = agent._situation_text(make_task(), [make_step("Learn figma basics")], None, None, NOW)
    assert "Progress facts (the only things you may praise): none" in text


def test_system_prompt_carries_every_rule_and_the_task():
    chosen = agent.interventions_for("overwhelm")[0]
    prompt = agent._system_prompt("chat", chosen, "Task: \"Finish UI DESIGN in figma\"", [])
    for needle in ["Finish UI DESIGN in figma", "Never use or open with", "Never state a clock time",
                   "Praise only something listed", "never suggest stopping", "do NOT push",
                   "Never invent tools"]:
        assert needle in prompt
    assert "At most 3 short sentences" in prompt


def test_initiate_must_name_the_task_in_the_first_sentence():
    assert "name the task in your first sentence" in agent.SITUATION["initiate"]


def test_no_playbook_doc_contains_a_clock_time():
    # The model copies the playbook's example lines; a literal "before 9pm" there became every reply's deadline.
    docs = Path(agent.__file__).parent / "buddy_docs"
    offenders = [f.name for f in docs.glob("*.md")
                 if re.search(r"\b\d{1,2}\s?(?:am|pm)\b|\b\d{1,2}:\d{2}\b", f.read_text(), re.IGNORECASE)]
    assert offenders == []


# ── the rewrite loop, end to end through /chat ──────────────────────────────

def register(api):
    body = api.post("/auth/anonymous", headers=INVITE).json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


class ScriptedLLM:
    """Returns replies from a script, in order; the decide call always picks the first candidate."""

    def __init__(self, *replies):
        self.replies, self.write_calls = list(replies), []

    async def __call__(self, messages, **kw):
        if kw.get("json_mode"):
            return '{"intervention": "surface_smallest_step", "reason": "x"}'
        self.write_calls.append(messages)
        return self.replies.pop(0)


def chat(api, monkeypatch, *replies, message="hello", title="Finish UI design in figma"):
    _, h = register(api)
    t = api.post("/tasks", json={"title": title}, headers=h).json()["id"]
    fake = ScriptedLLM(*replies)
    monkeypatch.setattr(llm, "complete", fake)
    r = api.post("/chat", json={"task_id": t, "message": message}, headers=h)
    return r.json(), fake


GOOD = "Open the figma design and rough out one frame. Which one is easiest?"


def test_hard_violation_is_rewritten_once_and_the_rewrite_is_used(api, monkeypatch):
    body, fake = chat(api, monkeypatch, "That sounds draining. Do some figma design before 9pm.", GOOD)
    assert body["reply"] == GOOD
    assert len(fake.write_calls) == 2
    retry = fake.write_calls[1]
    assert retry[-2] == {"role": "assistant", "content": "That sounds draining. Do some figma design before 9pm."}
    assert "sympathy filler" in retry[-1]["content"] and "clock time" in retry[-1]["content"]


def test_a_reply_that_stays_bad_falls_back_to_the_safe_message(api, monkeypatch, db):
    bad = "It's totally understandable. Do the figma design before 9pm."
    body, fake = chat(api, monkeypatch, bad, bad)
    assert body["reply"] == agent.FALLBACK_REPLY["chat"]
    assert body["intervention"] is None
    saved = db.query(models.Message).filter(models.Message.role == "assistant").one()
    assert saved.content == agent.FALLBACK_REPLY["chat"]  # the rejected draft is never shown or stored


def test_soft_violation_that_the_rewrite_fixes_uses_the_rewrite(api, monkeypatch):
    body, fake = chat(api, monkeypatch, "Take one small step and see how it feels.", GOOD)
    assert body["reply"] == GOOD and len(fake.write_calls) == 2


def test_soft_violation_that_persists_is_still_shown(api, monkeypatch):
    still_soft = "Take one small step. What would feel doable?"
    body, fake = chat(api, monkeypatch, still_soft, still_soft)
    assert body["reply"] == still_soft  # no hard violation, so it's acceptable


def test_a_clean_first_draft_costs_exactly_one_call(api, monkeypatch):
    body, fake = chat(api, monkeypatch, GOOD)
    assert body["reply"] == GOOD and len(fake.write_calls) == 1


def test_closing_note_never_retries_and_swaps_a_bad_one_for_the_neutral_line(api, monkeypatch):
    _, h = register(api)
    t = api.post("/tasks", json={"title": "Finish UI design in figma"}, headers=h).json()["id"]
    api.post("/checkin/action", json={"task_id": t, "stage": "emotion", "value": "tired"}, headers=h)
    fake = ScriptedLLM("That sounds exhausting. Rest, then do the figma design tomorrow.")
    monkeypatch.setattr(llm, "complete", fake)

    r = api.post("/checkin/action", json={"task_id": t, "stage": "chat_opt_in", "value": "no"}, headers=h)
    assert r.json()["notification"]["body"] == agent.FALLBACK_REPLY["closing"]
    assert len(fake.write_calls) == 1


def test_the_rewrite_call_failing_keeps_a_usable_first_draft(api, monkeypatch):
    class Flaky(ScriptedLLM):
        async def __call__(self, messages, **kw):
            if not kw.get("json_mode") and self.write_calls:
                raise llm.LLMError("down")
            return await super().__call__(messages, **kw)

    _, h = register(api)
    t = api.post("/tasks", json={"title": "Finish UI design in figma"}, headers=h).json()["id"]
    monkeypatch.setattr(llm, "complete", Flaky("Take one small step. What would feel doable?"))
    r = api.post("/chat", json={"task_id": t, "message": "hi"}, headers=h)
    assert r.json()["reply"] == "Take one small step. What would feel doable?"


# ── tasks with no due date must stay dateless ───────────────────────────────

@pytest.mark.parametrize("payload", [{"title": "x", "due_date": None}, {"title": "x"}])
def test_task_created_without_a_date_has_no_due_date(api, payload):
    _, h = register(api)
    body = api.post("/tasks", json=payload, headers=h).json()
    assert body["due_date"] is None
    assert api.get("/tasks", headers=h).json()[0]["due_date"] is None


def test_due_date_can_be_cleared_with_null_and_is_kept_when_omitted(api):
    _, h = register(api)
    t = api.post("/tasks", json={"title": "x", "due_date": "2026-12-01T00:00:00Z"}, headers=h).json()["id"]
    assert api.patch(f"/tasks/{t}", json={"title": "renamed"}, headers=h).json()["due_date"].startswith("2026-12-01")
    assert api.patch(f"/tasks/{t}", json={"due_date": None}, headers=h).json()["due_date"] is None


# ── what the writer is (and isn't) shown ────────────────────────────────────

def _example_snippets():
    """A distinctive chunk of every quoted example line in the intervention docs."""
    out = []
    for doc in playbook._load_docs():
        if doc.category != "intervention":
            continue
        examples = playbook.keep_sections(doc.body, ("What this looks like",))
        for line in re.findall(r'"([^"]{30,})"', examples.replace("\n", " ")):
            out.append((doc.intervention, " ".join(line.split())[:40]))
    return out


def test_examples_exist_to_guard_against():
    assert len(_example_snippets()) >= 5


@pytest.mark.parametrize("name,snippet", _example_snippets())
def test_example_sentences_never_reach_the_writer(name, snippet):
    doc = next(d for d in playbook._load_docs() if d.intervention == name)
    prompt = " ".join(agent._system_prompt("chat", doc, "ctx", [], "overwhelm").split())
    assert snippet not in prompt, f"{name}: an example line leaked into the prompt"


def test_intervention_text_keeps_the_rules_and_drops_examples_and_theory():
    doc = next(d for d in playbook._load_docs() if d.intervention == "acknowledge_emotion")
    text = playbook.intervention_text(doc)
    assert "## Explicit don'ts" in text and "## Purpose" in text
    assert "What this looks like" not in text and "Grounding theory" not in text


def test_writer_gets_the_states_stance_not_its_theory():
    stance = playbook.state_stance("fatigue")
    assert "Rest is valid. Do not push." in stance
    assert "Grounding theory" not in stance and "BJ Fogg" not in stance
    assert playbook.state_stance("no_such_state") is None and playbook.state_stance(None) is None


def test_fatigue_prompt_tells_the_writer_not_to_push():
    doc = playbook.interventions_for("fatigue")[0]
    assert "Rest is valid. Do not push." in agent._system_prompt("chat", doc, "ctx", [], "fatigue")
    assert "How to be with someone in this state" not in agent._system_prompt("chat", doc, "ctx", [], None)


# ── Groq rate limits ────────────────────────────────────────────────────────

import asyncio  # noqa: E402
import httpx  # noqa: E402


class _Resp:
    def __init__(self, status, headers=None, payload=None):
        self.status_code, self.headers, self._payload, self.text = status, headers or {}, payload or {}, ""

    def json(self):
        return self._payload


OK = _Resp(200, payload={"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 5}})


def _run_complete(monkeypatch, responses, **kw):
    sleeps = []

    async def fake_post(self, url, **_):
        return responses.pop(0)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    try:
        result = asyncio.run(llm.complete([{"role": "user", "content": "x"}], **kw))
    except llm.LLMError as e:
        result = e
    return result, sleeps


def test_a_429_waits_exactly_as_long_as_groq_says(monkeypatch):
    result, sleeps = _run_complete(monkeypatch, [_Resp(429, {"retry-after": "7"}), OK])
    assert result == "hi" and sleeps == [7.0]


def test_a_429_asking_for_more_than_we_will_wait_fails_fast(monkeypatch):
    result, sleeps = _run_complete(monkeypatch, [_Resp(429, {"retry-after": "45"}), OK], max_wait=20)
    assert isinstance(result, llm.LLMError) and sleeps == []


def test_closing_style_calls_do_not_wait_at_all(monkeypatch):
    result, sleeps = _run_complete(monkeypatch, [_Resp(429, {"retry-after": "1"}), OK], max_wait=0)
    assert isinstance(result, llm.LLMError) and sleeps == []


def test_without_retry_after_it_falls_back_to_exponential_backoff(monkeypatch):
    result, sleeps = _run_complete(monkeypatch, [_Resp(503), _Resp(503), OK])
    assert result == "hi" and sleeps == [1.0, 2.0]
