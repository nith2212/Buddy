# Async Groq chat-completions client over httpx (already a dependency — no SDK).
# Groq's API is OpenAI-compatible. Never blocks the event loop; retries 429/5xx/
# network errors with backoff; raises LLMError so callers can fall back gracefully.

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
) -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY is not set")

    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    body = {
        "model": model,
        "messages": messages,
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
                    _log_usage(data)
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


def _log_usage(data: dict) -> None:
    """Groq caps this key at a few thousand tokens per minute, so what each call costs matters."""
    usage = data.get("usage") or {}
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    logger.info("groq usage: prompt=%s completion=%s (reasoning=%s)",
                usage.get("prompt_tokens"), usage.get("completion_tokens"), reasoning)
