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
from brain.playbook import (
    PlaybookDoc, drop_sections, get_doc, get_state_doc, intervention_text, interventions_for, state_stance,
)
from brain.reply_check import check_reply, salient_words
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
    "initiate": "The user just tapped \"Yes, let's chat\" on a check-in notification. You speak first: "
                "open the conversation, and name the task in your first sentence.",
    "closing": "The user just finished a check-in and chose NOT to chat. Write one closing notification.",
}

MAX_SENTENCES = {"chat": 3, "initiate": 3, "closing": 2}
MAX_QUESTIONS = {"chat": 1, "initiate": 1, "closing": 0}
CLOSING_MAX_CHARS = 200  # phone notification; the prompt asks for under 160


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
    steps = _load_steps(db, task)
    situation = _situation_text(task, steps, emotion, top, datetime.now(timezone.utc))
    anchors = salient_words(task.title, *(s.title for s in steps if not s.done))

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
    checks: dict = {}
    try:
        if mode == "closing" or len(available) == 1:
            chosen, reason = available[0], "only/first available candidate"
        else:
            chosen, reason = await _decide(top_state, situation, history, user_message, available)
        reply, checks = await _write_checked(mode, chosen, top_state, situation, memory, history, user_message, anchors)
        if reply is None:
            raise llm.LLMError(f"reply rejected by checks: {checks['hard']}")
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
        "checks": checks,
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


def _load_steps(db: Session, task: Task) -> list[Subtask]:
    return list(db.execute(
        select(Subtask).where(Subtask.task_id == task.id, Subtask.user_id == task.user_id)
        .order_by(Subtask.position)
    ).scalars().all())


def _due_phrase(due: Optional[datetime], now: datetime) -> str:
    """Relative wording only. Giving the model a clock time or a UTC date invites it to repeat one."""
    if due is None:
        return "no due date"
    hours = (as_utc(due) - now).total_seconds() / 3600
    amount = abs(hours)
    if amount < 1:
        span = "less than an hour"
    elif amount < 48:
        span = f"about {round(amount)} hours"
    else:
        span = f"about {round(amount / 24)} days"
    return f"due in {span}" if hours >= 0 else f"overdue by {span}"


def _situation_text(task: Task, steps: list[Subtask], emotion: Optional[str], top, now: datetime) -> str:
    timing = "completed" if task.status == "done" else _due_phrase(task.due_date, now)
    lines = [
        f'Task: "{task.title or "untitled"}"',
        f"Timing: {timing}",
        f"Status: {task.status}; their last check-in answer: {task.task_state or 'none yet'}",
    ]
    facts = [f'Step done: "{s.title}"' for s in steps if s.done][:MAX_SUBTASKS_SHOWN]
    if task.status == "done":
        facts.append("Task marked done")
    if steps:
        open_steps = [s.title for s in steps if not s.done][:MAX_SUBTASKS_SHOWN]
        lines.append(f"Steps: {sum(1 for s in steps if s.done)} of {len(steps)} done. "
                     f"Open steps: {'; '.join(open_steps) or 'none'}")
    lines.append(f"Progress facts (the only things you may praise): {'; '.join(facts) or 'none'}")
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
    candidates_text = "\n\n".join(f"### id: {c.intervention}\n{intervention_text(c)}" for c in available)
    state_text = drop_sections(get_state_doc(top_state), ("Grounding theory",)) if get_state_doc(top_state) else None
    prompt = (
        f"Selection principles:\n{get_doc('core_intervention_selection')}\n\n"
        f"State definition:\n{state_text or '(no confident state)'}\n\n"
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

def _rules(mode: Mode) -> str:
    if mode == "closing":
        shape = ("One or two short sentences (under 160 characters) for a phone notification, and no question: "
                 "they chose not to chat, so ask nothing of them.")
    else:
        shape = (f"At most {MAX_SENTENCES[mode]} short sentences and at most one question, only if it moves them "
                 "forward. Plain text, no markdown or lists.")
    return (
        "RULES. Follow every one:\n"
        "1. Sound like a friend texting, not a manual. Mention the task naturally inside a sentence (never as a "
        "label followed by a colon). Build on what they just said where it helps, and never open two replies the "
        "same way. Then, unless rule 6 or 7 says otherwise, give ONE concrete next move taken from the task's open "
        "steps, small enough to start in a few minutes. If you speak first, begin with the task and one real fact "
        "from the context (its timing or an open step). Never invent tools, videos, tutorials, buttons or menu "
        "names.\n"
        f"2. {shape}\n"
        '3. No sympathy filler. Never use or open with: "That sounds…", "It\'s okay to feel…", '
        '"It\'s totally understandable", "I hear you", "I understand", "Hey there". Start with the substance.\n'
        "4. Never state a clock time or a date. Use only the due wording in the context "
        '(for example "due in about 14 hours") or words like "today" and "tonight". Never invent a deadline.\n'
        '5. Praise only something listed under "Progress facts", and name it. If there are none, give no praise '
        'at all: not "good move", not "you\'re taking the first step".\n'
        "6. Respect what the user just told you. If they say they want or need to keep going, help with the "
        "smallest next piece and never suggest stopping. If they say they're tired or drained, do NOT push: take "
        "the pressure off, say rest is fine, say you'll check in again later, and give no task move. If they just "
        "acknowledge you (\"ok\", \"thanks\"), give no new instruction: send them off in one short line and say "
        "you're around if they get stuck.\n"
        "7. You help with WORK states only. Never diagnose, never state the user's feelings as fact, and never ask "
        "them to name or label what they feel; if you mention how they feel, attribute it (\"you said it's a lot\"). If they signal "
        "distress beyond work (health, safety, grief, crisis), step back honestly: say it sounds bigger than this "
        "task, that you're a task companion and not the right support for it, and encourage them to reach out to "
        "someone they trust or a local helpline. No task coaching in that reply.\n"
        "8. Use only the context above. Never invent facts about the user or the task."
    )


def _system_prompt(
    mode: Mode, chosen: PlaybookDoc, situation: str, memory: list[dict], top_state: Optional[str] = None,
) -> str:
    memory_text = "\n".join(
        f"- {m['key']}: {m['value']} (confidence {m['confidence']:.2f}, source {m['source']})" for m in memory
    ) or "(nothing yet)"
    return (
        "You are Buddy, a calm, warm accountability companion for work and tasks. Steady and kind like Baymax: "
        "never judgmental, never preachy, never generic.\n\n"
        f"{get_doc('core_buddy_philosophy')}\n\n"
        + (f"How to be with someone in this state ({top_state}):\n{state_stance(top_state)}\n\n"
           if state_stance(top_state) else "")
        + f"How to respond this time (intervention: {chosen.intervention}):\n{intervention_text(chosen)}\n\n"
        f"Situation: {SITUATION[mode]}\n\n"
        f"Context (for you only, don't recite it):\n{situation}\n\n"
        f"What you remember about this user (trust 'echo' most, 'onboarding' least):\n{memory_text}\n\n"
        f"{_rules(mode)}"
    )


async def _write(
    mode: Mode,
    chosen: PlaybookDoc,
    top_state: Optional[str],
    situation: str,
    memory: list[dict],
    history: list[dict],
    user_message: Optional[str],
    rewrite: Optional[tuple[str, str]] = None,
) -> str:
    """One generation. `rewrite` is (rejected draft, what was wrong with it) for the retry."""
    messages = [{"role": "system", "content": _system_prompt(mode, chosen, situation, memory, top_state)},
                *_history_messages(history)]
    if user_message:
        messages.append({"role": "user", "content": user_message[:MAX_CHARS_PER_TURN * 2]})
    if rewrite:
        draft, problems = rewrite
        messages += [
            {"role": "assistant", "content": draft},
            {"role": "user", "content": f"That draft broke these rules:\n{problems}\n"
                                        "Rewrite it fixing them. Reply with only the rewritten message."},
        ]

    # max_tokens includes a reasoning model's hidden thinking — the rules in the prompt are what
    # keep replies short; these are just headroom so they don't truncate.
    if mode == "closing":
        return await llm.complete(messages, temperature=0.6, max_tokens=300, timeout=8.0, retries=0, max_wait=0)
    return await llm.complete(messages, temperature=0.7, max_tokens=600)


async def _write_checked(
    mode: Mode,
    chosen: PlaybookDoc,
    top_state: Optional[str],
    situation: str,
    memory: list[dict],
    history: list[dict],
    user_message: Optional[str],
    anchors: set[str],
) -> tuple[Optional[str], dict]:
    """
    Generate, check, and rewrite once if the draft breaks a rule. Returns (reply, checks); reply is
    None when every draft contains a hard violation (the caller then sends the safe fallback).
    The closing note is a single attempt: it runs during a background notification tap.
    """
    def check(text: str):
        return check_reply(
            text, max_sentences=MAX_SENTENCES[mode], max_questions=MAX_QUESTIONS[mode],
            user_message=user_message, anchor_words=anchors,
            max_chars=CLOSING_MAX_CHARS if mode == "closing" else None,
        )

    first = await _write(mode, chosen, top_state, situation, memory, history, user_message)
    drafts = [(first, check(first))]
    if drafts[0][1].any and mode != "closing":
        try:
            second = await _write(mode, chosen, top_state, situation, memory, history, user_message,
                                  rewrite=(first, drafts[0][1].describe()))
            drafts.append((second, check(second)))
        except llm.LLMError:
            pass  # keep the first draft if it's usable

    usable = [(text, v) for text, v in drafts if text and not v.hard]
    shown = min(usable, key=lambda d: len(d[1].soft)) if usable else drafts[-1]
    checks = {"hard": list(shown[1].hard), "soft": list(shown[1].soft), "rewritten": len(drafts) > 1}
    return (shown[0] if usable else None), checks


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
