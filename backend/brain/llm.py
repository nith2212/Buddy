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
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(retries + 1):
            try:
                resp = await client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {key}"})
            except httpx.HTTPError as e:
                last_error = e
            else:
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    return (content or "").strip()
                if resp.status_code not in RETRYABLE_STATUS:
                    raise LLMError(f"Groq returned {resp.status_code}: {resp.text[:200]}")
                last_error = LLMError(f"Groq returned {resp.status_code}")
            if attempt < retries:
                logger.warning("Groq call failed (attempt %d), retrying in %.1fs: %s", attempt + 1, delay, last_error)
                await asyncio.sleep(delay)
                delay *= 2
    raise LLMError(f"Groq call failed after {retries + 1} attempts: {last_error}")
