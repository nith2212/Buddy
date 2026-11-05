# The Anthropic branch of brain/llm.py (a "claude-..." GROQ_MODEL). No network: the SDK client is faked.
import asyncio
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from brain import flow, llm

MODEL = "claude-haiku-5-5"


def reply(text="Ooh, love that!", stop="end_turn"):
    return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5), stop_reason=stop,
                           content=[SimpleNamespace(type="text", text=text)] if text else [])


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls, self.init = response or reply(), error, [], None
        self.messages = self

    def __call__(self, **kw):  # stands in for anthropic.AsyncAnthropic(...)
        self.init = kw
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", MODEL)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def use(**kw):
        fake = FakeClient(**kw)
        monkeypatch.setattr(anthropic, "AsyncAnthropic", fake)
        return fake
    return use


def run(coro):
    return asyncio.run(coro)


def test_claude_model_goes_to_anthropic_without_temperature(claude):
    fake = claude()
    msgs = [{"role": "system", "content": "be Buddy"}, {"role": "user", "content": "idk"}]
    assert run(llm.complete(msgs, temperature=0.7, max_tokens=300, timeout=8.0, retries=0)) == "Ooh, love that!"
    call = fake.calls[0]
    assert call["model"] == MODEL and call["system"] == "be Buddy" and call["max_tokens"] == 300
    assert call["messages"] == [{"role": "user", "content": "idk"}]
    assert "temperature" not in call                      # Claude Haiku 5.5 rejects sampling params
    assert call["thinking"] == {"type": "disabled"}
    assert fake.init == {"timeout": 8.0, "max_retries": 0}


def test_reader_gets_its_schema_as_structured_output(claude):
    fake = claude(response=reply(json.dumps({"kind": "idk", "cause": None, "flavor": None, "fact": None})))
    reading = run(flow.read_message("ambiguity", "open", "What would done look like?", "hmm no clue honestly"))
    assert reading.kind == "idk"
    assert fake.calls[0]["output_config"] == {"format": {"type": "json_schema", "schema": flow.READ_SCHEMA}}


def test_json_without_a_schema_is_unfenced(claude):
    claude(response=reply('```json\n{"a": 1}\n```'))
    assert json.loads(run(llm.complete([{"role": "user", "content": "x"}], json_mode=True))) == {"a": 1}


@pytest.mark.parametrize("fake_kw", [
    {"response": reply(stop="refusal")},
    {"response": reply(text="")},
    {"error": anthropic.APIStatusError("overloaded", response=httpx2.Response(
        529, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")), body=None)},
    {"error": anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))},
])
def test_failures_become_llm_errors_so_buddy_falls_back(claude, fake_kw):
    claude(**fake_kw)
    with pytest.raises(llm.LLMError):
        run(llm.complete([{"role": "user", "content": "hi"}]))


def test_missing_anthropic_key_is_an_llm_error(claude, monkeypatch):
    claude()
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(llm.LLMError):
        run(llm.complete([{"role": "user", "content": "hi"}]))


def test_messages_are_shaped_for_the_messages_api():
    system, turns = llm.anthropic_request([{"role": "system", "content": "a"}, {"role": "system", "content": "b"}])
    assert system == "a\n\nb" and turns == [llm.OPENER_TURN]          # Buddy speaks first
    _, turns = llm.anthropic_request([
        {"role": "system", "content": "s"},
        {"role": "assistant", "content": "Hey! What would done look like?"},   # history starts with Buddy
        {"role": "user", "content": "a cat app"}, {"role": "user", "content": "with points"},
        {"role": "assistant", "content": "Love it."},                          # ends with Buddy: no prefill
    ])
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant", "user"]
    assert turns[2]["content"] == "a cat app\n\nwith points"


def test_read_schema_follows_the_structured_output_rules():
    schema = flow.READ_SCHEMA
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["kind"]["enum"] == list(flow.KINDS)
