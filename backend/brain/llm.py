# The one place Buddy calls a model. GROQ_MODEL picks it (name kept from when Groq was the only
# provider): a "claude-..." model goes to Anthropic (official SDK, ANTHROPIC_API_KEY), anything else
# to Groq (OpenAI-compatible, over httpx, GROQ_API_KEY). Never blocks the event loop; retries
# rate limits / 5xx / network errors; raises LLMError so callers can fall back gracefully.

from __future__ import annotations

import asyncio
import logging
import os

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# llama-3.1-8b-instant (CLAUDE.md's original pick) has been retired on Groq.
# gpt-oss-20b is the fast/small replacement; override with GROQ_MODEL.
DEFAULT_MODEL = "openai/gpt-oss-20b"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Some models (qwen on Groq) refuse a request with no user message: "No user query found". Buddy's
# opening message has none, so it gets this stand-in turn (found by the eval, 2026-11-04).
OPENER_TURN = {"role": "user", "content": "(No message from them yet: you speak first.)"}


def with_user_turn(messages: list[dict]) -> list[dict]:
    return messages if any(m.get("role") == "user" for m in messages) else [*messages, OPENER_TURN]

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


async def complete(
    messages: list[dict],
    *,
    temperature: float = 0.5,
    max_tokens: int = 300,
    json_mode: bool = False,
    timeout: float = 15.0,
    retries: int = 2,
    max_wait: float = 20.0,
    json_schema: dict | None = None,
) -> str:
    """One completion. `json_schema` (with json_mode) makes Anthropic return exactly that shape;
    Groq's JSON mode ignores it. Temperature only reaches Groq: Claude Haiku 5.5 rejects it."""
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    if model.startswith("claude-"):
        return await _anthropic(model, messages, max_tokens=max_tokens, json_mode=json_mode,
                                json_schema=json_schema if json_mode else None, timeout=timeout, retries=retries)

    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY is not set")

    body = {
        "model": model,
        "messages": with_user_turn(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if "gpt-oss" in model:
        # Reasoning model: its hidden thinking counts against max_tokens. Keep it
        # minimal so short replies don't come back empty (and stay fast).
        body["reasoning_effort"] = "low"
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    delay = 1.0
    last_error: Exception | None = None
    attempts = 0
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(retries + 1):
            attempts += 1
            advised: float | None = None
            try:
                resp = await client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:
                last_error = e
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    _log_usage((data.get("usage") or {}).get("prompt_tokens"),
                               (data.get("usage") or {}).get("completion_tokens"))
                    return (data["choices"][0]["message"]["content"] or "").strip()
                if resp.status_code not in RETRYABLE_STATUS:
                    raise LLMError(f"Groq returned {resp.status_code}: {resp.text[:200]}")
                last_error = LLMError(f"Groq returned {resp.status_code}")
                advised = _advised_wait(resp)
            if attempt < retries:
                pause = advised if advised is not None else delay
                if pause > max_wait:
                    break  # Groq says to wait longer than this caller can; fail now and let it fall back
                logger.warning("Groq call failed (attempt %d), retrying in %.1fs: %s", attempt + 1, pause, last_error)
                await asyncio.sleep(pause)
                delay *= 2
    raise LLMError(f"Groq call failed after {attempts} attempt(s): {last_error}")


def _advised_wait(resp) -> float | None:
    """Groq's 429s say how long to wait (Retry-After, seconds) — far better than guessing."""
    try:
        return max(0.0, float(resp.headers.get("retry-after")))
    except (AttributeError, TypeError, ValueError):
        return None


def _log_usage(prompt_tokens, completion_tokens) -> None:
    """What each call costs (Groq's free tier caps tokens per minute; Anthropic bills per token).
    testing/evals/run.py counts these lines."""
    logger.info("llm usage: prompt=%s completion=%s", prompt_tokens, completion_tokens)


# ── Anthropic ───────────────────────────────────────────────────────────────────────

def anthropic_request(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI-style messages -> (system, messages) for the Messages API. The conversation must
    start and end with a user turn (Claude Haiku 5.5 rejects an assistant turn last: no prefill),
    and same-role neighbours are merged."""
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    turns: list[dict] = []
    for m in messages:
        if m.get("role") not in ("user", "assistant") or not m.get("content"):
            continue
        if turns and turns[-1]["role"] == m["role"]:
            turns[-1]["content"] += "\n\n" + m["content"]
        else:
            turns.append({"role": m["role"], "content": m["content"]})
    if not turns or turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": "(Start of the chat.)"} if turns else dict(OPENER_TURN))
    if turns[-1]["role"] != "user":
        turns.append({"role": "user", "content": "(No new message from them: write your next message.)"})
    return system, turns


async def _anthropic(model: str, messages: list[dict], *, max_tokens: int, json_mode: bool, json_schema: dict | None,
                     timeout: float, retries: int) -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY is not set")
    import anthropic  # only needed when a Claude model is picked

    system, turns = anthropic_request(messages)
    kwargs: dict = {}
    if system:
        kwargs["system"] = system
    if json_schema:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
    try:
        async with anthropic.AsyncAnthropic(timeout=timeout, max_retries=retries) as client:
            resp = await client.messages.create(
                model=model, max_tokens=max_tokens, messages=turns,
                # short replies: no thinking (speed, cost); accepted at the default effort
                thinking={"type": "disabled"}, **kwargs,
            )
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic returned {e.status_code}: {str(e)[:200]}") from e
    except anthropic.APIError as e:  # connection errors, timeouts
        raise LLMError(f"Anthropic call failed: {e}") from e
    _log_usage(resp.usage.input_tokens, resp.usage.output_tokens)
    if resp.stop_reason == "refusal":
        raise LLMError("Anthropic declined the request (refusal)")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise LLMError(f"Anthropic returned no text (stop_reason={resp.stop_reason})")
    if json_mode and not json_schema:
        text = _strip_fences(text)  # no schema: the prompt asks for JSON, which may come fenced
    return text


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
