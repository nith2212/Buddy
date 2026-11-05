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
#
# Root cause first: when the user has tapped a reason, Buddy diagnoses before it advises.
# Phases (what the writer is told to do this turn):
#   ask         — reflect the tapped reason, ask ONE specific question, no advice
#   guess       — offer a read of the cause as a question, no advice
#   offer       — the user CONFIRMED a cause: name it, ask whether they want a tiny move or have a plan
#   first_move  — they want a move: one tiny first move that fits the cause
#   release     — an acknowledgment or their own plan ("okay thanks", "I'll work on X"): back it, nothing new
#   normal      — everything else (the decide call picks among the state's interventions)
# A cause is saved only when the user confirms it (judged by a small LLM call, not keywords).

from __future__ import annotations

import dataclasses
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from brain import echo, flow, llm, tools
from brain.flow import is_ack
from brain.playbook import (
    PlaybookDoc, drop_sections, framework_section, get_doc, get_intervention, get_state_doc, has_framework,
    intervention_text, interventions_for, state_stance,
)
from brain.reply_check import check_reply, salient_words, tidy
from brain.state_detection import EMOTION_TO_STATE, as_utc, detect_state
from models import EmotionLog, Message, Subtask, Task

logger = logging.getLogger(__name__)

Mode = Literal["chat", "initiate", "closing"]
Phase = Literal["normal", "release"]

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
    "afraid": "scared it won't be good enough",
    "bored": "finds it boring or pointless",
}

SITUATION = {
    "chat": "The user is chatting with you about this task. Reply to their latest message.",
    "initiate": "The user just tapped \"Yes, let's chat\" on a check-in notification. You speak first: "
                "open the conversation, and name the task in your first sentence.",
    "closing": "The user just finished a check-in and chose NOT to chat. Write one closing notification.",
}

MAX_SENTENCES = {"chat": 3, "initiate": 3, "closing": 2}
MAX_QUESTIONS = {"chat": 1, "initiate": 1, "closing": 0}
# (max sentences, max questions) for a release; "normal" uses the mode's limits above.
PHASE_LIMITS = {"release": (2, 0)}

PATTERN_MIN = 3               # a cause must be confirmed this many times before Buddy may mention a pattern

# What each tapped reason means, in the words the model should use.
CAUSE_WORDS = {
    "unclear": "not knowing where to start",
    "too_much": "the task feels too big",
    "afraid": "fear that it won't be good enough",
    "bored": "it feels boring or pointless",
    "tired": "being tired or drained",
}
# memory rows never shown to the writer as rows: causes come through the one pattern line, and Echo's
# weekly facts (echo.week.*) are for Buddy's judgment only, through _context_line
_CAUSE_KEYS = ("blocker.", "pattern.", "echo.")

# After these, a polite "okay" is more likely avoidance than agreement.
_NO_RELEASE_STATES = {"avoidance", "commitment_drift"}
CLOSING_MAX_CHARS = 200  # phone notification; the prompt asks for under 160


async def run_turn(
    db: Session,
    user_id: str,
    task: Task,
    mode: Mode,
    user_message: Optional[str] = None,
) -> dict:
    """Run one Buddy turn for `task` (already ownership-checked by the caller)."""
    task_id = task.id
    emotion_row = _fresh_emotion(db, user_id, task_id)
    emotion = emotion_row.emotion if emotion_row else None
    if mode != "closing" and emotion in EMOTION_TO_STATE and has_framework(EMOTION_TO_STATE[emotion]):
        # A reason was tapped this check-in cycle: the state's framework runs the conversation.
        return await _flow_turn(db, user_id, task, mode, user_message, emotion_row)

    hypotheses = detect_state(db, user_id, task_id, emotion_tap=emotion)
    top = hypotheses[0] if hypotheses else None
    top_state = top.state if top else None

    all_memory = tools.get_user_memory(db, user_id)
    memory = [m for m in all_memory if not m["key"].startswith(_CAUSE_KEYS)][:MEMORY_ROWS]
    history = [] if mode == "closing" else tools.get_conversation_history(
        db, user_id, limit=HISTORY_TURNS, task_id=task_id
    )
    steps = _load_steps(db, task)
    situation = _situation_text(task, steps, emotion, top, datetime.now(timezone.utc))
    anchors = salient_words(task.title, *(s.title for s in steps if not s.done))
    if any(h["role"] == "assistant" for h in history):
        anchors = set()  # the task is named in Buddy's first message; later replies needn't repeat it
        # Said once is enough: leaving the timing in is what makes every reply open "X is due in 3 days".
        situation = re.sub(r"^Timing: .*$", "Timing: already told them; do not mention it again", situation, flags=re.M)

    confirmed = tools.get_memory_entry(db, user_id, f"blocker.task.{task_id}")
    if confirmed and confirmed.value in CAUSE_WORDS:
        situation += f"\nThe cause they confirmed for this task: {CAUSE_WORDS[confirmed.value]}"
    pattern = _context_line(db, user_id, task_id, all_memory)
    if pattern:
        situation += f"\n{pattern}"

    recent = _recent_interventions(memory)
    candidates = interventions_for(top_state)
    available = [c for c in candidates if c.intervention not in recent[-EXCLUDE_RECENT:]] or candidates

    if mode == "closing" and top is None:
        # No confident state: neutral closing, no LLM call (CLAUDE.md state-detection spec).
        reply = FALLBACK_REPLY["closing"]
        reasoning = {"mode": mode, "hypotheses": [], "top_state": None, "intervention": None,
                     "reason": "no confident state; neutral closing", "fallback": False}
        _learn(db, user_id, task_id, None, reply, reasoning, None, None, recent)
        return {"reply": reply, "state": None, "intervention": None, "fallback": False}

    # Everything above was read-only. End that transaction so the connection goes back to the
    # pool instead of sitting idle while we wait on Groq. Nothing below may touch ORM objects.
    db.rollback()

    fallback = False
    checks: dict = {}
    phase: Phase = "normal"
    confirmed_cause: Optional[str] = None
    try:
        if mode == "closing":
            chosen, reason = available[0], "only/first available candidate"
        elif (user_message and is_ack(user_message) and top_state not in _NO_RELEASE_STATES
              and get_intervention("affirm_and_release")):
            chosen, phase, reason = get_intervention("affirm_and_release"), "release", "short acknowledgment"
        elif len(available) == 1:
            chosen, reason = available[0], "only/first available candidate"
        else:
            chosen, reason = await _decide(top_state, situation, history, user_message, available)
        reply, checks = await _write_checked(
            mode, chosen, top_state, situation, memory, history, user_message, anchors, phase,
            previous_reply=next((h["content"] for h in reversed(history) if h["role"] == "assistant"), None))
        if reply is None:
            raise llm.LLMError(f"reply rejected by checks: {checks['hard']}")
    except llm.LLMError as e:
        logger.warning("Buddy turn fell back (mode=%s task_id=%s): %s", mode, task_id, e)
        fallback, reply = True, FALLBACK_REPLY[mode]
        chosen, reason = available[0], "fallback"

    reasoning = {
        "mode": mode,
        "phase": phase,
        "hypotheses": [{"state": h.state, "confidence": h.confidence} for h in hypotheses],
        "top_state": top_state,
        "intervention": None if fallback else chosen.intervention,
        "reason": reason,
        "fallback": fallback,
        "checks": checks,
    }
    _learn(db, user_id, task_id, user_message, reply, reasoning, top_state,
           None if fallback else chosen.intervention, recent, confirmed_cause)

    return {
        "reply": reply,
        "state": top_state,
        "intervention": reasoning["intervention"],
        "fallback": fallback,
    }


# ── framework turns (a reason was tapped) ──────────────────────────────────

FLOW_HISTORY = 8          # messages of this session the writer sees
FLOW_OPEN_STEPS = 5
_GENERIC_HEADINGS = {"release": "Release", "step_back": "Step back", "offer": "Offer", "followup": "Followup"}
_MODIFIER_HEADINGS = {"idk": "If they said idk", "unsure": "If they were unsure", "reject": "If they said no",
                      "unclear": "If it was unclear", "stay": "If they answered but you stay here",
                      "accepted": "If they took your move"}
_FRAMEWORK_TITLES = {"ambiguity": "Don't know where to start", "perfectionism": "Scared it won't be good enough",
                     "fatigue": "Too tired", "overwhelm": "Feels too big", "low_interest": "Boring or pointless"}
OFFER_FALLBACK = "Want a tiny first move from me, or do you already know what you'll do?"


async def _flow_turn(
    db: Session, user_id: str, task: Task, mode: Mode, user_message: Optional[str], emotion_row: EmotionLog,
) -> dict:
    """
    One turn of a state framework (state_frameworks.md). A session starts at the reason tap: the
    stage, tries and "known so far" notes ride along in each Buddy turn's saved reasoning. Code
    picks the stage from a reading of the user's message; the model only words the reply.
    """
    task_id = task.id
    tapped, since = emotion_row.emotion, emotion_row.created_at  # read now: rollback below expires ORM rows
    session = _session_messages(db, user_id, task_id, since)
    last_flow = next((m["flow"] for m in reversed(session) if m["flow"]), None)
    tapped_state = EMOTION_TO_STATE[tapped]
    state = last_flow["state"] if last_flow else tapped_state
    stage = last_flow["stage"] if last_flow else None
    tries = int(last_flow.get("tries", 1)) if last_flow else 0
    notes = dict(last_flow.get("notes") or {}) if last_flow else {}
    buddy_said = next((m["content"] for m in reversed(session) if m["role"] == "assistant"), None)
    history = [{"role": m["role"], "content": m["content"]} for m in session][-FLOW_HISTORY:]
    last_time = _last_session_notes(db, user_id, task_id, since)

    saved = tools.get_memory_entry(db, user_id, f"blocker.task.{task_id}")
    already_saved = bool(saved and as_utc(saved.updated_at) > as_utc(since))
    pattern = _context_line(db, user_id, task_id, tools.get_user_memory(db, user_id))
    known = echo.profile(db, user_id, datetime.now(timezone.utc))  # E3: how they've reacted before
    steps = _load_steps(db, task)
    open_steps = [s.title for s in steps if not s.done][:FLOW_OPEN_STEPS]
    done_steps = [s.title for s in steps if s.done][:FLOW_OPEN_STEPS]
    now = datetime.now(timezone.utc)
    timing = "completed" if task.status == "done" else _due_phrase(task.due_date, now)
    first_turn = buddy_said is None
    anchors = salient_words(task.title, *open_steps) if first_turn else set()
    title = task.title or "untitled"

    # Everything above was read-only: give the connection back before waiting on Groq.
    db.rollback()

    reading: Optional[flow.Reading] = None
    if stage is None:
        step = flow.Step(state, flow.FRAMEWORKS[state].first)
        if user_message:  # a reason and a message together: read it as the answer to the opener
            reading = await flow.read_message(state, step.stage, None, user_message)
            step = flow.next_stage(state, step.stage, reading, tries=1)
    elif user_message:
        reading = await flow.read_message(state, stage, buddy_said, user_message)
        step = flow.next_stage(state, stage, reading, tries)
    else:
        step = flow.Step(state, stage, modifier="stay")  # reopened without a new message
    # E3: an developer-approved rule may reroute a fresh offer, or add one hint line (it then wins over the
    # other context line: it's about the move Buddy is making right now).
    reroute, hint, rule = (echo.adapt(known, step.state, step.stage, flow.FRAMEWORKS[step.state].tiny)
                           if step.modifier is None else (None, None, None))
    if reroute and (step.state, reroute) == (state, stage):
        reroute, hint, rule = None, None, None  # they just turned that move down: ask, don't repeat it
    if reroute:
        step = dataclasses.replace(step, stage=reroute)
    pattern = hint or pattern
    new_tries = tries + 1 if (step.state, step.stage) == (state, stage) else 1
    if step.note:
        notes[step.note[0]] = step.note[1]
    save_cause = step.save_cause if not already_saved else None

    system = _flow_prompt(step, title=title, timing=timing, first_turn=first_turn, open_steps=open_steps,
                          done_steps=done_steps, tapped=tapped, notes=notes, last_time=last_time,
                          pattern=pattern)
    limits = (3, 0) if step.stage in flow.NO_QUESTION else (3, 1)
    check_phase = "offer" if step.stage == "offer" else (
        "guess" if step.stage == "narrow" or step.modifier == "idk" else step.stage)

    fallback, checks = False, {}
    try:
        reply, checks = await _write_checked(
            mode, None, step.state, "", [], history, user_message, anchors, check_phase,
            previous_reply=buddy_said, system=system, limits=limits,
            require_question=step.stage in flow.ASKS)
        if reply is None:
            raise llm.LLMError(f"reply rejected by checks: {checks['hard']}")
        if step.stage == "offer" and "offer_shape" in checks["soft"]:
            # The small model tends to hand out a step here; the choice is too important to leave to it.
            reply, checks["offer_template"] = OFFER_FALLBACK, True
    except llm.LLMError as e:
        logger.warning("Buddy flow turn fell back (task_id=%s): %s", task_id, e)
        fallback, reply, save_cause, rule = True, FALLBACK_REPLY[mode], None, None
        step, new_tries = flow.Step(state, stage or flow.FRAMEWORKS[state].first), tries  # don't advance on a failure

    reasoning = {
        "mode": mode,
        "phase": step.stage,
        "top_state": step.state,
        "intervention": None,
        "flow": {
            "state": step.state, "stage": step.stage, "tries": new_tries, "modifier": step.modifier,
            "notes": notes,
            "adapt": rule,
            "read": None if reading is None else {"kind": reading.kind, "cause": reading.cause,
                                                  "flavor": reading.flavor, "source": reading.source},
        },
        "reason": "framework",
        "fallback": fallback,
        "checks": checks,
    }
    _learn(db, user_id, task_id, user_message, reply, reasoning, step.state, None, [], save_cause)
    return {"reply": reply, "state": step.state, "intervention": f"{step.state}:{step.stage}",
            "fallback": fallback}


def _flow_prompt(
    step: "flow.Step", *, title: str, timing: str, first_turn: bool, open_steps: list[str], done_steps: list[str],
    tapped: str, notes: dict, last_time: Optional[dict], pattern: Optional[str],
) -> str:
    """The writer's whole prompt for one framework turn: voice, this stage, the facts, this stage's rules."""
    generic = step.stage in flow.GENERIC
    card = (framework_section("shared", _GENERIC_HEADINGS[step.stage]) if generic
            else framework_section(step.state, step.stage)) or ""
    modifier = framework_section("shared", _MODIFIER_HEADINGS[step.modifier]) if step.modifier else None
    never = framework_section(step.state, "Never")
    asks = step.stage not in flow.NO_QUESTION

    facts = [f'Task: "{title}"']
    if first_turn:
        facts.append(f"Timing: {timing}. This is your first message: name the task naturally in your first sentence.")
    else:
        facts.append("Timing: already mentioned, don't bring it up again. Don't restate the task's name; respond to "
                     "what they just said.")
    facts.append(f"Open steps: {'; '.join(open_steps) or 'none'}")
    facts.append(f"Done so far (the only progress you may praise): {'; '.join(done_steps) or 'nothing yet'}")
    facts.append(f"The reason they tapped: {EMOTION_WORDS.get(tapped, tapped)}")
    if step.state != EMOTION_TO_STATE.get(tapped):
        facts.append(f"They since said what's really in the way: {flow.CAUSES[flow.CAUSE_OF[step.state]]}")
    if notes:
        facts.append("Known so far (their words):\n" + "\n".join(f"- {k}: {v}" for k, v in notes.items()))
    if last_time:
        facts.append("Last time on this task: " + "; ".join(f"{k}: {v}" for k, v in last_time.items()))
    if pattern:
        facts.append(pattern)

    what = f"{card}\n{modifier}" if modifier else card
    return (
        f"{framework_section('shared', 'Voice')}\n\n"
        + "\n".join(facts)
        + f"\n\nWhat to do now ({_FRAMEWORK_TITLES.get(step.state, step.state)}, stage: {step.stage}):\n{what}\n"
        + (f"Never: {never}\n" if never and step.stage != "step_back" else "")
        + "\nRules:\n"
        + ("- At most 3 short sentences and exactly ONE question.\n" if asks
           else "- At most 3 short sentences and no question.\n")
        + "- Plain text, no lists or markdown.\n"
          "- Never state a clock time or a date; use only the timing above.\n"
          "- If they mention something bigger than work (health, safety, grief, crisis), step back: say it sounds "
          "bigger than this task, that you're a task companion and not the right support for it, and encourage "
          "someone they trust or a local helpline.\n"
          "- Use only what's above and what they said. Never invent facts, tools, buttons or features."
    )


def _session_messages(db: Session, user_id: str, task_id: int, since: datetime) -> list[dict]:
    """This session's messages (since the reason tap), oldest first, with each Buddy turn's flow state."""
    rows = db.execute(
        select(Message.role, Message.content, Message.reasoning).where(
            Message.user_id == user_id, Message.task_id == task_id, Message.created_at >= since)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).all()
    return [{"role": r.role, "content": r.content[:MAX_CHARS_PER_TURN],
             "flow": _flow_of(r.reasoning) if r.role == "assistant" else None} for r in rows]


def _last_session_notes(db: Session, user_id: str, task_id: int, before: datetime) -> Optional[dict]:
    """What the user told Buddy in the previous session on this task, if anything was noted."""
    rows = db.execute(
        select(Message.reasoning).where(
            Message.user_id == user_id, Message.task_id == task_id, Message.role == "assistant",
            Message.created_at < before)
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(5)
    ).scalars().all()
    for raw in rows:
        f = _flow_of(raw)
        if f and f.get("notes"):
            return f["notes"]
    return None


def _flow_of(raw: Optional[str]) -> Optional[dict]:
    try:
        f = json.loads(raw).get("flow") if raw else None
    except (ValueError, AttributeError):
        return None
    return f if isinstance(f, dict) and f.get("state") in flow.FRAMEWORKS and f.get("stage") else None


# ── context ─────────────────────────────────────────────────────────────────

def _fresh_emotion(db: Session, user_id: str, task_id: int) -> Optional[EmotionLog]:
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
    return row


def _context_line(db: Session, user_id: str, task_id: int, memory: list[dict]) -> Optional[str]:
    """At most one line of what Buddy knows about this person (CLAUDE.md: one capped line). Echo's
    'go gentle, they've been away' cue wins: it changes how to talk right now. Else the cause pattern."""
    return (echo.buddy_line(echo.latest(db, user_id, datetime.now(timezone.utc)), task_id)
            or _pattern_line(memory))


def _pattern_line(memory: list[dict]) -> Optional[str]:
    """One line about the cause confirmed most often, only once it has been confirmed PATTERN_MIN+ times."""
    counts = {}
    for m in memory:
        cause = m["key"].removeprefix("pattern.blocker.")
        if cause != m["key"] and cause in CAUSE_WORDS:
            try:
                counts[cause] = int(m["value"])
            except (TypeError, ValueError):
                pass
    if not counts:
        return None
    cause, n = max(counts.items(), key=lambda kv: kv[1])
    if n < PATTERN_MIN:
        return None
    return (f"Pattern: {CAUSE_WORDS[cause]} has come up for them a few times before. You may mention it once, "
            "softly, only if it fits. Never give a number.")


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
        logger.warning("Decide call returned an unusable choice (%d chars)", len(raw))
        return available[0], "decide call returned an invalid choice; used first candidate"


# ── LLM call 2: write ───────────────────────────────────────────────────────

def _limits(mode: Mode, phase: Phase = "normal") -> tuple[int, int]:
    """(max sentences, max questions) for a reply."""
    return PHASE_LIMITS.get(phase, (MAX_SENTENCES[mode], MAX_QUESTIONS[mode]))


_NO_INVENTING = "Never invent tools, videos, tutorials, buttons or menu names."
_RULE_1 = {
    "normal": (
        "1. Sound like a friend texting, not a manual. Mention the task naturally inside a sentence (never as a "
        "label followed by a colon). Build on what they just said where it helps, and never open two replies the "
        "same way. Then, unless rule 6 or 7 says otherwise, give ONE concrete next move taken from the task's open "
        "steps, small enough to start in a few minutes. If you speak first, begin with the task and one real fact "
        f"from the context (its timing or an open step). {_NO_INVENTING}\n"
    ),
    "release": (
        "1. Sound like a friend texting. They just acknowledged you, so only receive it. Do not mention or quote their "
        "thanks. Say, briefly, that they're taking on the step you last suggested (or what they just decided), end on "
        "a full stop, and add nothing new: no step, no tip, no question. You may say you're around if they get "
        "stuck. If they named their own plan, back it exactly as they said it: never shrink, change or add to it. "
        f"{_NO_INVENTING}\n"
    ),
}


def _rules(mode: Mode, phase: Phase = "normal") -> str:
    max_sentences, max_questions = _limits(mode, phase)
    if mode == "closing":
        shape = ("One or two short sentences (under 160 characters) for a phone notification, and no question: "
                 "they chose not to chat, so ask nothing of them.")
    elif max_questions == 0:
        shape = f"At most {max_sentences} short sentences and no question. Plain text, no markdown or lists."
    else:
        shape = (f"At most {max_sentences} short sentences and at most one question, only if it moves them "
                 "forward. Plain text, no markdown or lists.")
    return (
        "RULES. Follow every one:\n"
        f"{_RULE_1[phase]}"
        f"2. {shape}\n"
        '3. No therapy phrases: never "It\'s okay to feel…", "It\'s totally understandable", "I hear you". '
        'No promises ("trust me"), no pressure ("relax", "buckle up"). A short warm reaction to what they said '
        'is welcome.\n'
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
    phase: Phase = "normal",
) -> str:
    memory_text = "\n".join(
        f"- {m['key']}: {m['value']} (confidence {m['confidence']:.2f}, source {m['source']})" for m in memory
    ) or "(nothing yet)"
    return (
        f"{framework_section('shared', 'Voice')}\n\n"
        f"{get_doc('core_buddy_philosophy')}\n\n"
        + (f"How to be with someone in this state ({top_state}):\n{state_stance(top_state)}\n\n"
           if state_stance(top_state) else "")
        + f"How to respond this time (intervention: {chosen.intervention}):\n{intervention_text(chosen)}\n\n"
        f"Situation: {SITUATION[mode]}\n\n"
        f"Context (for you only, don't recite it):\n{situation}\n\n"
        f"What you remember about this user (trust 'echo' most, 'onboarding' least):\n{memory_text}\n\n"
        f"{_rules(mode, phase)}"
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
    phase: Phase = "normal",
    system: Optional[str] = None,
) -> str:
    """One generation. `rewrite` is (rejected draft, what was wrong with it) for the retry."""
    system = system or _system_prompt(mode, chosen, situation, memory, top_state, phase)
    messages = [{"role": "system", "content": system}, *_history_messages(history)]
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
        return tidy(await llm.complete(messages, temperature=0.6, max_tokens=300, timeout=8.0, retries=0, max_wait=0))
    return tidy(await llm.complete(messages, temperature=0.7, max_tokens=600))


async def _write_checked(
    mode: Mode,
    chosen: PlaybookDoc,
    top_state: Optional[str],
    situation: str,
    memory: list[dict],
    history: list[dict],
    user_message: Optional[str],
    anchors: set[str],
    phase: str = "normal",
    previous_reply: Optional[str] = None,
    system: Optional[str] = None,
    limits: Optional[tuple[int, int]] = None,
    require_question: bool = False,
) -> tuple[Optional[str], dict]:
    """
    Generate, check, and rewrite once if the draft breaks a rule. Returns (reply, checks); reply is
    None when every draft contains a hard violation (the caller then sends the safe fallback).
    The closing note is a single attempt: it runs during a background notification tap.
    """
    max_sentences, max_questions = limits or _limits(mode, phase)

    def check(text: str):
        return check_reply(
            text, max_sentences=max_sentences, max_questions=max_questions,
            user_message=user_message, anchor_words=set() if phase == "release" else anchors,
            max_chars=CLOSING_MAX_CHARS if mode == "closing" else None, previous_reply=previous_reply,
            phase=phase, require_question=require_question,
        )

    write_phase = phase if phase in ("normal", "release") else "normal"
    first = await _write(mode, chosen, top_state, situation, memory, history, user_message, phase=write_phase,
                         system=system)
    drafts = [(first, check(first))]
    if drafts[0][1].any and mode != "closing":
        try:
            second = await _write(mode, chosen, top_state, situation, memory, history, user_message,
                                  rewrite=(first, drafts[0][1].describe()), phase=write_phase, system=system)
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
    confirmed_cause: Optional[str] = None,
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
        if confirmed_cause:
            tools.record_confirmed_cause(db, user_id, task_id, confirmed_cause, commit=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
