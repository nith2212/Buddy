# Buddy's turn pipeline (CLAUDE.md "Per-turn pipeline"):
#   load capped context -> detect state -> playbook -> decide (LLM call 1)
#   -> write (LLM call 2) -> learn (messages + memory in ONE transaction).
#
# Three modes share it: "chat" (user sent a message), "initiate" (user opted into
# chat, Buddy speaks first), "closing" (user declined chat — one short tailored
# notification). Closing skips the decide call and uses a short timeout: it runs
# while the phone handles a notification tap in the background, so it must be fast.
#
# Any Groq failure degrades to a fixed fallback reply; the user always gets an answer.

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from brain import llm, tools
from brain.playbook import PlaybookDoc, get_doc, get_state_doc, interventions_for
from brain.state_detection import as_utc, detect_state
from models import EmotionLog, Subtask, Task

logger = logging.getLogger(__name__)

Mode = Literal["chat", "initiate", "closing"]

HISTORY_TURNS = 12
MAX_CHARS_PER_TURN = 600
MEMORY_ROWS = 10
MAX_SUBTASKS_SHOWN = 10
EXCLUDE_RECENT = 2           # don't reuse the last N interventions
RECENT_KEPT = 3
EMOTION_FRESHNESS = timedelta(hours=24)

FALLBACK_REPLY = {
    "chat": "I'm having trouble finding my words right now. Try me again in a moment?",
    "initiate": "Hey, I'm here. What feels hardest about this one right now?",
    "closing": "Okay, no pressure. I'll check in again later.",
}

EMOTION_WORDS = {
    "tired": "tired / drained",
    "too_much": "it feels like too much right now",
    "unclear": "doesn't know where to start",
}

SITUATION = {
    "chat": "The user is chatting with you about this task. Reply to their latest message.",
    "initiate": "The user just tapped \"Yes, let's chat\" on a check-in notification. You speak first: open the conversation.",
    "closing": "The user just finished a check-in and chose NOT to chat. Write one closing notification.",
}

LENGTH_RULE = {
    "chat": "1-3 short sentences. At most one question.",
    "initiate": "1-3 short sentences. At most one question.",
    "closing": "One or two short sentences, under 160 characters, for a phone notification. "
               "No question: they chose not to chat, so don't ask them for anything.",
}


async def run_turn(
    db: Session,
    user_id: str,
    task: Task,
    mode: Mode,
    user_message: Optional[str] = None,
) -> dict:
    """Run one Buddy turn for `task` (already ownership-checked by the caller)."""
    emotion = _fresh_emotion(db, user_id, task.id)
    hypotheses = detect_state(db, user_id, task.id, emotion_tap=emotion)
    top = hypotheses[0] if hypotheses else None
    top_state = top.state if top else None

    memory = tools.get_user_memory(db, user_id)[:MEMORY_ROWS]
    history = [] if mode == "closing" else tools.get_conversation_history(
        db, user_id, limit=HISTORY_TURNS, task_id=task.id
    )
    situation = _situation_text(db, task, emotion, top)

    recent = _recent_interventions(memory)
    candidates = interventions_for(top_state)
    available = [c for c in candidates if c.intervention not in recent[-EXCLUDE_RECENT:]] or candidates

    if mode == "closing" and top is None:
        # No confident state: neutral closing, no LLM call (CLAUDE.md state-detection spec).
        reply = FALLBACK_REPLY["closing"]
        reasoning = {"mode": mode, "hypotheses": [], "top_state": None, "intervention": None,
                     "reason": "no confident state; neutral closing", "fallback": False}
        _learn(db, user_id, task.id, None, reply, reasoning, None, None, recent)
        return {"reply": reply, "state": None, "intervention": None, "fallback": False}

    fallback = False
    try:
        if mode == "closing" or len(available) == 1:
            chosen, reason = available[0], "only/first available candidate"
        else:
            chosen, reason = await _decide(top_state, situation, history, user_message, available)
        reply = await _write(mode, chosen, top_state, situation, memory, history, user_message)
        if not reply:
            raise llm.LLMError("empty reply")
    except llm.LLMError as e:
        logger.warning("Buddy turn fell back (mode=%s task_id=%s): %s", mode, task.id, e)
        fallback, reply = True, FALLBACK_REPLY[mode]
        chosen, reason = available[0], "fallback"

    reasoning = {
        "mode": mode,
        "hypotheses": [{"state": h.state, "confidence": h.confidence} for h in hypotheses],
        "top_state": top_state,
        "intervention": None if fallback else chosen.intervention,
        "reason": reason,
        "fallback": fallback,
    }
    _learn(db, user_id, task.id, user_message, reply, reasoning, top_state,
           None if fallback else chosen.intervention, recent)

    return {
        "reply": reply,
        "state": top_state,
        "intervention": reasoning["intervention"],
        "fallback": fallback,
    }


# ── context ─────────────────────────────────────────────────────────────────

def _fresh_emotion(db: Session, user_id: str, task_id: int) -> Optional[str]:
    """The latest emotion tap for this task, if it's from the current check-in cycle."""
    row = db.execute(
        select(EmotionLog)
        .where(EmotionLog.user_id == user_id, EmotionLog.task_id == task_id)
        .order_by(EmotionLog.created_at.desc(), EmotionLog.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None or row.emotion is None:
        return None
    if datetime.now(timezone.utc) - as_utc(row.created_at) > EMOTION_FRESHNESS:
        return None
    return row.emotion


def _situation_text(db: Session, task: Task, emotion: Optional[str], top) -> str:
    due = as_utc(task.due_date)
    lines = [
        f'Task: "{task.title or "untitled"}"',
        f"Due: {due.strftime('%Y-%m-%d %H:%M UTC') if due else 'no due date'}",
        f"Status: {task.status}; last check-in answer: {task.task_state or 'none yet'}",
    ]
    subtasks = db.execute(
        select(Subtask).where(Subtask.task_id == task.id, Subtask.user_id == task.user_id)
        .order_by(Subtask.position)
    ).scalars().all()
    if subtasks:
        done = sum(1 for s in subtasks if s.done)
        remaining = [s.title for s in subtasks if not s.done][:MAX_SUBTASKS_SHOWN]
        lines.append(f"Subtasks: {done}/{len(subtasks)} done. Remaining: {'; '.join(remaining) or 'none'}")
    if emotion:
        lines.append(f"In this check-in they said they feel: {EMOTION_WORDS.get(emotion, emotion)}")
    if top:
        lines.append(f"Detected work state: {top.state} (confidence {top.confidence:.1f})")
    else:
        lines.append("Detected work state: none (not enough signal; don't assume a state)")
    return "\n".join(lines)


def _recent_interventions(memory: list[dict]) -> list[str]:
    raw = next((m["value"] for m in memory if m["key"] == "buddy.recent_interventions"), "") or ""
    return [r.strip() for r in raw.split(",") if r.strip()]


def _history_messages(history: list[dict]) -> list[dict]:
    return [{"role": h["role"], "content": h["content"][:MAX_CHARS_PER_TURN]} for h in history]


def _history_text(history: list[dict]) -> str:
    if not history:
        return "(no conversation yet)"
    return "\n".join(f"{h['role']}: {h['content'][:MAX_CHARS_PER_TURN]}" for h in history[-6:])


# ── LLM call 1: decide ──────────────────────────────────────────────────────

async def _decide(
    top_state: Optional[str],
    situation: str,
    history: list[dict],
    user_message: Optional[str],
    available: list[PlaybookDoc],
) -> tuple[PlaybookDoc, str]:
    ids = [c.intervention for c in available]
    candidates_text = "\n\n".join(f"### id: {c.intervention}\n{c.body}" for c in available)
    prompt = (
        f"Selection principles:\n{get_doc('core_intervention_selection')}\n\n"
        f"State definition:\n{get_state_doc(top_state) or '(no confident state)'}\n\n"
        f"Situation:\n{situation}\n\n"
        f"Recent conversation:\n{_history_text(history)}\n\n"
        f"User's latest message: {user_message or '(none, Buddy speaks first)'}\n\n"
        f"Candidate interventions:\n{candidates_text}\n\n"
        f"Pick exactly one id from: {', '.join(ids)}."
    )
    raw = await llm.complete(
        [
            {"role": "system", "content": (
                "You choose how Buddy, a work accountability companion, should respond next. "
                'Reply with JSON only: {"intervention": "<one candidate id>", "reason": "<one sentence>"}'
            )},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2, max_tokens=400, json_mode=True, timeout=10.0,
    )
    try:
        parsed = json.loads(raw)
        chosen = next(c for c in available if c.intervention == parsed.get("intervention"))
        return chosen, str(parsed.get("reason", ""))[:300]
    except (ValueError, StopIteration, AttributeError):
        logger.warning("Decide call returned an unusable choice: %r", raw[:200])
        return available[0], "decide call returned an invalid choice; used first candidate"


# ── LLM call 2: write ───────────────────────────────────────────────────────

async def _write(
    mode: Mode,
    chosen: PlaybookDoc,
    top_state: Optional[str],
    situation: str,
    memory: list[dict],
    history: list[dict],
    user_message: Optional[str],
) -> str:
    memory_text = "\n".join(
        f"- {m['key']}: {m['value']} (confidence {m['confidence']:.2f}, source {m['source']})" for m in memory
    ) or "(nothing yet)"
    system = (
        "You are Buddy, a calm, warm accountability companion. Steady and kind like Baymax: "
        "never judgmental, never preachy, never generic.\n\n"
        f"{get_doc('core_buddy_philosophy')}\n\n"
        f"How to respond this time (intervention: {chosen.intervention}):\n{chosen.body}\n\n"
        "Rules:\n"
        "- You help with WORK states only: starting, continuing, finishing tasks. Never diagnose, "
        "and never state the user's feelings as fact.\n"
        "- If the user signals distress beyond work (health, safety, grief, crisis), step back honestly: "
        "say it sounds bigger than this task, that you're a task companion and not the right support for it, "
        "and encourage them to reach out to someone they trust or a local helpline. No task coaching in that reply.\n"
        "- Use only the context below. Never invent facts about the user or the task.\n"
        f"- Plain text, no markdown, no lists. {LENGTH_RULE[mode]}\n\n"
        f"Situation: {SITUATION[mode]}\n\n"
        f"Context (for you only, don't recite it):\n{situation}\n\n"
        f"What you remember about this user (trust 'echo' most, 'onboarding' least):\n{memory_text}"
    )
    messages = [{"role": "system", "content": system}, *_history_messages(history)]
    if user_message:
        messages.append({"role": "user", "content": user_message[:MAX_CHARS_PER_TURN * 2]})

    # max_tokens includes a reasoning model's hidden thinking — the length rule in the
    # prompt is what keeps replies short; these are just headroom so they don't truncate.
    if mode == "closing":
        return await llm.complete(messages, temperature=0.6, max_tokens=300, timeout=8.0, retries=0)
    return await llm.complete(messages, temperature=0.7, max_tokens=600)


# ── learn: one transaction ──────────────────────────────────────────────────

def _learn(
    db: Session,
    user_id: str,
    task_id: int,
    user_message: Optional[str],
    reply: str,
    reasoning: dict,
    top_state: Optional[str],
    intervention: Optional[str],
    recent: list[str],
) -> None:
    try:
        if user_message:
            tools.save_conversation_turn(db, user_id, "user", user_message, task_id=task_id, commit=False)
        tools.save_conversation_turn(db, user_id, "assistant", reply, task_id=task_id,
                                     reasoning=reasoning, commit=False)
        if top_state:
            tools.update_memory(db, user_id, "buddy.last_detected_state", top_state, commit=False)
        if intervention:
            tools.update_memory(db, user_id, "buddy.last_intervention", intervention, commit=False)
            tools.update_memory(db, user_id, "buddy.recent_interventions",
                                ",".join((recent + [intervention])[-RECENT_KEPT:]), commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
