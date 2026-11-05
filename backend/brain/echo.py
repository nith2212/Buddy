# Echo: a weekly count of each user's week, for Buddy only (docs/PIVOTS.md "Echo, in steps").
#
# - E1 (facts): causes, ignored tasks, postpones, what got finished.
# - E2 (reactions): what they did with each move Buddy offered (took it, brought their own plan,
#   said no, went quiet) and whether progress followed within a day; check-in replies; days active.
# - E3 (adapt): four developer-approved rules (2026-11-05) that change Buddy's next move once something has
#   happened RULE_MIN+ times. See "E3" below.
#
# - Counted by code, no model call: nothing can be invented, and it spends no Groq quota.
# - For Buddy, never for the user: no push, no user-facing text. Buddy gets at most one line, and
#   that line tells it to be gentler. It never quotes these facts (developer decision 2026-11-04).
# - Runs for anyone with a task, including tasks they ignore (ignoring is data). No tasks: skipped.
# - Saved as memory rows echo.week.<week end date> (source "echo"), the last KEEP_WEEKS kept.
#   DELETE /me wipes them with the rest of memory.
#
# The week ends Sunday 23:00 India time. cron-job.org calls POST /cron/echo then (cron.py).

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from brain.state_detection import EMOTION_TO_STATE, as_utc
from models import EmotionLog, Event, Memory, Message, Subtask, Task

WEEK_TZ = ZoneInfo("Asia/Kolkata")
WEEK_END = time(23, 0)          # Sunday 23:00 in WEEK_TZ
IGNORE_WINDOW = timedelta(hours=12)  # a check-in with no tap or chat on that task within this is "ignored"
KEEP_WEEKS = 8
KEY_PREFIX = "echo.week."

# When Buddy gets the "be gentle" line (any one is enough)
AWAY_DAYS = 5                   # task untouched this many days
AWAY_IGNORED = 2                # check-ins ignored this week
ECHO_FRESH = timedelta(days=8)  # older facts are stale: no line


def week_window(now: datetime) -> tuple[datetime, datetime]:
    """(start, end) in UTC of the last week that has ended by `now`. Weeks end Sunday 23:00 India time."""
    local = as_utc(now).astimezone(WEEK_TZ)
    days_back = (local.weekday() - 6) % 7  # Monday=0 ... Sunday=6
    end = datetime.combine(local.date() - timedelta(days=days_back), WEEK_END, tzinfo=WEEK_TZ)
    if end > local:
        end -= timedelta(days=7)
    end = end.astimezone(timezone.utc)
    return end - timedelta(days=7), end


def week_id(end: datetime) -> str:
    return as_utc(end).astimezone(WEEK_TZ).date().isoformat()


def _in(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    dt = as_utc(dt)
    return dt is not None and start <= dt < end


def _cause_totals(db: Session, user_id: str) -> dict[str, int]:
    totals = {}
    for row in db.execute(select(Memory).where(Memory.user_id == user_id,
                                               Memory.key.startswith("pattern.blocker."))).scalars():
        try:
            totals[row.key.removeprefix("pattern.blocker.")] = int(row.value)
        except (TypeError, ValueError):
            pass
    return totals


def _previous(db: Session, user_id: str, before: str) -> Optional[dict]:
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    older = sorted((r for r in rows if r.key.removeprefix(KEY_PREFIX) < before), key=lambda r: r.key)
    if not older:
        return None
    try:
        return json.loads(older[-1].value)
    except (TypeError, ValueError):
        return None


# ── E2: how they react to Buddy ────────────────────────────────────────────────────────
# Every framework reply stores its stage, and the next reply stores the reading of the user's answer
# (agent._flow_turn), so a reaction is just "the reading on the reply after the move".

# (state, stage) -> the move Buddy made there. "*" = any state.
MOVES = {
    ("overwhelm", "micro"): "tiny_move", ("ambiguity", "suggest"): "tiny_move", ("fatigue", "move"): "tiny_move",
    ("perfectionism", "reframe"): "rough_version",
    ("low_interest", "lighten"): "lighter",
    ("fatigue", "rest"): "rest",
    ("ambiguity", "first_step"): "asked_their_step", ("overwhelm", "open"): "asked_their_step",
    ("*", "offer"): "offer",   # "a tiny move from me, or do you already know what you'll do?"
}
REACTION_OF = {"accept": "took", "confirm": "took", "own_plan": "own_plan", "reject": "declined",
               "wants_move": "wanted_move", "new_cause": "switched", "ack": "ack", "idk": "idk"}
# At the offer, "sure"/"you say"/"idk" all mean "give me one".
OFFER_REACTION = {"accept": "wanted_move", "wants_move": "wanted_move", "idk": "wanted_move",
                  "own_plan": "own_plan", "reject": "declined"}
REPLY_WINDOW = timedelta(hours=12)   # an answer later than this is a new conversation, not a reaction
PROGRESS_WINDOW = timedelta(hours=24)
OUTCOMES = ("took", "own_plan", "wanted_move", "declined", "idk", "ack", "switched", "other", "no_reply")


def _flow(raw: Optional[str]) -> Optional[dict]:
    try:
        f = json.loads(raw or "").get("flow")
    except (TypeError, ValueError, AttributeError):
        return None
    return f if isinstance(f, dict) else None


CAUSE_OF_STATE = {state: cause for cause, state in EMOTION_TO_STATE.items()}


def _move(flow: dict) -> Optional[str]:
    """'<cause>.<move>' (e.g. 'afraid.rough_version'), or None if this reply wasn't a move."""
    state = flow.get("state")
    move = MOVES.get((state, flow.get("stage"))) or MOVES.get(("*", flow.get("stage")))
    return f"{CAUSE_OF_STATE[state]}.{move}" if move and state in CAUSE_OF_STATE else None


def reactions(db: Session, user_id: str, task_ids: list[int], start: datetime, end: datetime,
              progress: dict[int, list[datetime]]) -> dict[str, dict[str, int]]:
    """Per '<cause>.<move>' Buddy offered this week: how often, what they did next, how often progress
    (a step ticked or the task finished) followed within PROGRESS_WINDOW, and "helped": they took the move
    (or went with their own plan) and progress followed."""
    turns = db.execute(select(Message).where(Message.user_id == user_id, Message.task_id.in_(task_ids),
                                             Message.role == "assistant").order_by(Message.id)).scalars().all()
    by_task: dict[int, list[tuple[datetime, dict]]] = {}
    for m in turns:
        f = _flow(m.reasoning)
        if f:
            by_task.setdefault(m.task_id, []).append((as_utc(m.created_at), f))

    out: dict[str, dict[str, int]] = {}
    for task_id, seq in by_task.items():
        for i, (at, f) in enumerate(seq):
            move = _move(f)
            if not move or not _in(at, start, end):
                continue
            nxt = seq[i + 1] if i + 1 < len(seq) else None
            if nxt and (nxt[1].get("state"), nxt[1].get("stage")) == (f.get("state"), f.get("stage")) \
                    and nxt[0] - at <= REPLY_WINDOW:
                continue  # Buddy stayed on this move ("that's all?"): judge the last time it was made
            read = (nxt[1].get("read") or {}) if nxt and nxt[0] - at <= REPLY_WINDOW else {}
            kind = read.get("kind")
            if not kind:
                outcome = "no_reply"
            elif move.endswith(".offer"):
                outcome = OFFER_REACTION.get(kind, "other")
            else:
                outcome = REACTION_OF.get(kind, "other")
            row = out.setdefault(move, {"offered": 0, **{o: 0 for o in OUTCOMES}, "progress_after": 0,
                                        "helped": 0})
            row["offered"] += 1
            row[outcome] += 1
            if any(at < d <= at + PROGRESS_WINDOW for d in progress.get(task_id, [])):
                row["progress_after"] += 1
                row["helped"] += outcome in ("took", "own_plan")  # they went with it, and then made progress
    return out


def _progress(tasks: list[Task], steps_done: list[Subtask]) -> dict[int, list[datetime]]:
    """When each task moved forward: a step ticked or the task finished (not just opening it)."""
    progress: dict[int, list[datetime]] = {}
    for st in steps_done:
        progress.setdefault(st.task_id, []).append(as_utc(st.updated_at or st.created_at))
    for t in tasks:
        if t.completed_at:
            progress.setdefault(t.id, []).append(as_utc(t.completed_at))
    return progress


def _local_day(dt: datetime) -> str:
    return as_utc(dt).astimezone(WEEK_TZ).date().isoformat()


def _touches(db: Session, user_id: str, tasks: list[Task]) -> tuple[dict[int, list[datetime]], list[EmotionLog]]:
    """Every moment the user touched each task (their own actions only, never Buddy's or the scheduler's),
    and their reason taps."""
    ids = [t.id for t in tasks]
    touches: dict[int, list[datetime]] = {t.id: [as_utc(t.created_at)] for t in tasks}
    for t in tasks:
        if t.updated_at:
            touches[t.id].append(as_utc(t.updated_at))
    for st in db.execute(select(Subtask).where(Subtask.user_id == user_id, Subtask.task_id.in_(ids))).scalars():
        touches[st.task_id].append(as_utc(st.updated_at or st.created_at))
    for m in db.execute(select(Message).where(Message.user_id == user_id, Message.task_id.in_(ids),
                                              Message.role == "user")).scalars():
        touches[m.task_id].append(as_utc(m.created_at))
    taps = db.execute(select(EmotionLog).where(EmotionLog.user_id == user_id, EmotionLog.task_id.in_(ids))
                      ).scalars().all()
    for e in taps:
        touches[e.task_id].append(as_utc(e.created_at))
    return touches, list(taps)


def week_facts(db: Session, user_id: str, start: datetime, end: datetime) -> Optional[dict]:
    """Everything Echo counts for one user's week, or None when they have no tasks to count."""
    tasks = db.execute(select(Task).where(Task.user_id == user_id)).scalars().all()
    tasks = [t for t in tasks if as_utc(t.created_at) < end
             and (t.status == "open" or _in(t.completed_at, start, end))]
    if not tasks:
        return None
    ids = [t.id for t in tasks]
    touches, taps = _touches(db, user_id, tasks)

    events = db.execute(select(Event).where(Event.user_id == user_id, Event.task_id.in_(ids),
                                            or_(Event.type == "checkin_sent", Event.type == "postponed"))
                        ).scalars().all()

    per_task = []
    for t in tasks:
        if t.status != "open":
            continue
        seen = [d for d in touches[t.id] if d < end]
        sent = [as_utc(e.created_at) for e in events if e.task_id == t.id and e.type == "checkin_sent"
                and _in(e.created_at, start, end)]
        # judged only once the window has passed by the end of the week
        judged = [s for s in sent if s + IGNORE_WINDOW <= end]
        ignored = sum(1 for s in judged if not any(s <= d <= s + IGNORE_WINDOW for d in seen))
        per_task.append({
            "id": t.id,
            "days_untouched": (end - max(seen)).days if seen else None,
            "checkins_sent": len(sent),
            "checkins_ignored": ignored,
            "postponed": sum(1 for e in events if e.task_id == t.id and e.type == "postponed"
                             and _in(e.created_at, start, end)),
        })

    tapped: dict[str, int] = {}
    for e in taps:
        if e.emotion and _in(e.created_at, start, end):
            tapped[e.emotion] = tapped.get(e.emotion, 0) + 1

    totals = _cause_totals(db, user_id)
    prev = _previous(db, user_id, week_id(end))
    if prev is not None:
        before = prev.get("cause_totals", {})
        confirmed = {c: n - before.get(c, 0) for c, n in totals.items() if n - before.get(c, 0) > 0}
    else:
        # first Echo for this user: count the per-task causes confirmed during the week
        confirmed = {}
        for row in db.execute(select(Memory).where(Memory.user_id == user_id,
                                                   Memory.key.startswith("blocker.task."))).scalars():
            if _in(row.updated_at, start, end) and row.value:
                confirmed[row.value] = confirmed.get(row.value, 0) + 1

    steps_done = db.execute(select(Subtask).where(Subtask.user_id == user_id, Subtask.task_id.in_(ids),
                                                  Subtask.done.is_(True))).scalars().all()

    progress = _progress(tasks, steps_done)
    week_taps = [e for e in taps if _in(e.created_at, start, end)]
    started = sum(1 for e in week_taps
                  if any(as_utc(e.created_at) < d <= as_utc(e.created_at) + PROGRESS_WINDOW
                         for d in progress.get(e.task_id, [])))
    sent = sum(x["checkins_sent"] for x in per_task)
    return {
        "week": week_id(end),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "first_week": prev is None,
        "causes_confirmed": confirmed,
        "cause_totals": totals,
        "reasons_tapped": tapped,
        "tasks_finished": sum(1 for t in tasks if _in(t.completed_at, start, end)),
        "steps_done": sum(1 for s in steps_done if _in(s.updated_at, start, end)),
        "open_tasks": per_task,
        # E2
        "reactions": reactions(db, user_id, ids, start, end, progress),
        "started_after_tap": started,   # tapped "why I'm stuck", then made progress within a day
        "checkins": {
            "sent": sent,
            "ignored": sum(x["checkins_ignored"] for x in per_task),
            "chat_yes": sum(1 for e in week_taps if e.chat_opt_in is True),
            "chat_no": sum(1 for e in week_taps if e.chat_opt_in is False),
        },
        "days_active": sorted({_local_day(d) for ds in touches.values() for d in ds if _in(d, start, end)}),
    }


def run_echo(db: Session, user_id: str, now: datetime) -> str:
    """Count and save one user's last finished week. Returns 'saved', 'already_done' or 'no_tasks'."""
    start, end = week_window(now)
    key = KEY_PREFIX + week_id(end)
    if db.execute(select(Memory.id).where(Memory.user_id == user_id, Memory.key == key)).first():
        return "already_done"
    facts = week_facts(db, user_id, start, end)
    if facts is None:
        return "no_tasks"
    db.add(Memory(user_id=user_id, key=key, value=json.dumps(facts), confidence=1.0, source="echo"))
    db.flush()  # so the new week counts toward KEEP_WEEKS below
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    for old in sorted(rows, key=lambda r: r.key, reverse=True)[KEEP_WEEKS:]:
        db.delete(old)
    db.commit()
    return "saved"


def latest(db: Session, user_id: str, now: datetime) -> Optional[dict]:
    """The newest saved week, if it's fresh enough to use."""
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    if not rows:
        return None
    try:
        facts = json.loads(max(rows, key=lambda r: r.key).value)
        if as_utc(now) - datetime.fromisoformat(facts["end"]) > ECHO_FRESH:
            return None
        return facts
    except (TypeError, ValueError, KeyError):
        return None


def buddy_line(facts: Optional[dict], task_id: int) -> Optional[str]:
    """The one line Buddy may get from Echo: a cue to go gentle on a task they've been away from.
    Never a number, never the facts themselves: Buddy must not say them."""
    if not facts:
        return None
    task = next((t for t in facts.get("open_tasks", []) if t.get("id") == task_id), None)
    if not task:
        return None
    away = (task.get("days_untouched") or 0) >= AWAY_DAYS or task.get("checkins_ignored", 0) >= AWAY_IGNORED
    if not away:
        return None
    return ("Context, never mention it: they've been away from this task for a while. Be extra gentle and "
            "low-pressure, and glad they're here. Don't bring up time away, check-ins, or anything you know "
            "about their week.")


# ── The user's Echo page (GET /echo/week) ─────────────────────────────────────────────────
# Only kind, earned things: wins, the days they showed up, and what helped. Never ignored check-ins,
# untouched days, postpones, comparisons or percentages (docs/PIVOTS.md "Echo page"). All text is built
# here from templates, never by a model, so nothing can be invented. Wording: developer to review.

PATTERN_MIN = 3   # a cause must be confirmed this often before the page mentions it (same as chat)
HELPED_WEEKS = KEEP_WEEKS

CAUSE_TEXT = {
    "unclear": "Not knowing where to start",
    "too_much": "A task feeling too big",
    "afraid": "Worrying it won't be good enough",
    "bored": "A task feeling boring or pointless",
    "tired": "Being tired",
}
MOVE_TEXT = {
    "tiny_move": "a tiny first move",
    "rough_version": "a rough first version",
    "lighter": "making it lighter",
    "rest": "resting first",
    "asked_their_step": "picking your own first step",
    "offer": "going with your own plan",
}
QUIET_LINE = "Quiet week. That's okay, I'm here whenever you're ready."
QUIET_LAST_WEEK = "A quiet week. That's okay, rest counts too."


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def week_line(finished: int, steps: int, started: int, days: int, when: str = "this week") -> str:
    if finished:
        return f"You finished {_plural(finished, 'task')} {when}! That's real progress."
    if started:
        return f"You got going {_times(started)} {when}, even when it felt hard."
    if steps:
        return f"You ticked off {_plural(steps, 'step')} {when}. Every one counts."
    if days:
        return f"You showed up {_plural(days, 'day')} {when}. That counts."
    return QUIET_LINE if when == "this week" else QUIET_LAST_WEEK


def _helped(db: Session, user_id: str, this_week: dict) -> list[dict]:
    """What helped, per cause the user has confirmed PATTERN_MIN+ times, over the saved weeks plus this one."""
    totals = _cause_totals(db, user_id)
    sums: dict[str, int] = {}
    rows = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                      ).scalars().all()
    weeks = []
    for r in sorted(rows, key=lambda r: r.key, reverse=True)[:HELPED_WEEKS]:
        try:
            weeks.append(json.loads(r.value).get("reactions", {}))
        except (TypeError, ValueError, AttributeError):
            continue
    for reactions_ in [*weeks, this_week]:
        for key, row in reactions_.items():
            sums[key] = sums.get(key, 0) + int(row.get("helped", 0))
    out = []
    for key, n in sorted(sums.items(), key=lambda kv: -kv[1]):
        cause, _, move = key.partition(".")
        if n < 1 or totals.get(cause, 0) < PATTERN_MIN or move not in MOVE_TEXT:
            continue
        if any(h["cause"] == cause for h in out):
            continue  # the one thing that helped most, per cause
        what = MOVE_TEXT[move]
        out.append({"cause": cause, "move": move, "times": n,
                    "text": f"{CAUSE_TEXT[cause]} has come up a few times. {what[0].upper() + what[1:]} "
                            f"helped you get going {_times(n)}."})
    return out


def _week_days(start: datetime, active: set[str]) -> list[dict]:
    """Mon..Sun of the week that starts at `start` (Sunday 23:00 India time), active or not."""
    first_day = start.astimezone(WEEK_TZ).date() + timedelta(days=1)   # the week's Monday
    days = [(first_day + timedelta(days=i)).isoformat() for i in range(7)]
    # Sunday 23:00-24:00 belongs to the new week but has the old Sunday's date: show it on Monday.
    if (first_day - timedelta(days=1)).isoformat() in active:
        active = active | {days[0]}
    return [{"date": d, "active": d in active} for d in days]


def _last_week(db: Session, user_id: str, start: datetime) -> Optional[dict]:
    """The week that ended at `start`, from the row the Sunday cron saved (None if it saved none)."""
    row = db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key == KEY_PREFIX + week_id(start))
                     ).scalars().first()
    if row is None:
        return None
    try:
        facts = json.loads(row.value)
    except (TypeError, ValueError):
        return None
    days = _week_days(start - timedelta(days=7), set(facts.get("days_active", [])))
    finished = int(facts.get("tasks_finished", 0))
    steps = int(facts.get("steps_done", 0))
    started = int(facts.get("started_after_tap", 0))
    shown = sum(1 for d in days if d["active"])
    return {
        "days": days,
        "wins": {"tasks_finished": finished, "steps_done": steps, "started_when_hard": started},
        "line": week_line(finished, steps, started, shown, when="last week"),
    }


def this_week(db: Session, user_id: str, now: datetime) -> dict:
    """The user's Echo page: this week so far (since Sunday 23:00 India time)."""
    _, start = week_window(now)
    now = as_utc(now)

    facts = week_facts(db, user_id, start, now)
    all_tasks = db.execute(select(Task).where(Task.user_id == user_id)).scalars().all()
    touches, _ = _touches(db, user_id, list(all_tasks)) if all_tasks else ({}, [])
    ever = {_local_day(d) for ds in touches.values() for d in ds}

    days = _week_days(start, set(facts["days_active"]) if facts else set())
    finished = facts["tasks_finished"] if facts else 0
    steps = facts["steps_done"] if facts else 0
    started = facts["started_after_tap"] if facts else 0
    shown = sum(1 for d in days if d["active"])
    saved = db.execute(select(Memory.id).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))).first()
    return {
        "week_start": start.isoformat(),
        "first_week": saved is None,   # no weekly Echo saved yet: the page says the first one comes Monday
        "days": days,
        "total_days": len(ever),   # only ever goes up
        "wins": {"tasks_finished": finished, "steps_done": steps, "started_when_hard": started},
        "line": week_line(finished, steps, started, shown),
        "helped": _helped(db, user_id, facts["reactions"] if facts else {}),
        # the week that just ended (saved Sunday 23:00), so Monday has a real report; None until then
        "last_week": _last_week(db, user_id, start),
    }


# ── E3: Buddy adapts (developer-approved rules, 2026-11-05) ──────────────────────────────────────
# Each rule switches on only after Echo has seen the pattern RULE_MIN+ times (saved weeks plus this
# week so far). A rule either reroutes the stage or gives the writer ONE hint line. Buddy never says
# a count. The four rules:
#   own_plan_first  they usually bring their own plan -> at the offer, ask what they'll do first, a tiny
#                   move from Buddy only as the backup. If they then ask Buddy, Buddy suggests as usual.
#   move_first      at the offer they always ask for Buddy's move, never their own -> skip the either/or
#                   and go straight to one tiny "what about...?" move
#   lean_on_helped  a move helped them get going RULE_MIN+ times for this cause -> offer it first, and
#                   Buddy may say softly that it helped before (developer: "softly say it")
#   avoid_declined  they said no to a move RULE_MIN+ times for this cause and never took it -> offer
#                   something different

RULE_MIN = 3

ADAPT_HINTS = {
    "own_plan_first": "What you know about them: they usually have their own plan. Ask what they'll do first, "
                      "and offer a tiny move from you only as the backup, all in one question.",
    "lean_on_helped": "What you know about them: {move} has helped them get going with this before. Offer that "
                      "first. You may say softly that it helped before, never how often or when.",
    "avoid_declined": "What you know about them: they usually say no to {move}. Don't offer it; offer a "
                      "different kind of small move, or ask what they'd like to do.",
}


def profile(db: Session, user_id: str, now: datetime) -> dict[str, dict[str, int]]:
    """E2's reactions summed over the saved weeks and this week so far: '<cause>.<move>' -> counts."""
    sums: dict[str, dict[str, int]] = {}

    def add(reactions_: dict) -> None:
        for key, row in (reactions_ or {}).items():
            acc = sums.setdefault(key, {})
            for k, v in row.items():
                if isinstance(v, int):
                    acc[k] = acc.get(k, 0) + v

    for r in db.execute(select(Memory).where(Memory.user_id == user_id, Memory.key.startswith(KEY_PREFIX))
                        ).scalars():
        try:
            add(json.loads(r.value).get("reactions"))
        except (TypeError, ValueError, AttributeError):
            continue
    _, since = week_window(now)  # the saved weeks end here; count the rest live
    tasks = db.execute(select(Task).where(Task.user_id == user_id)).scalars().all()
    if tasks:
        ids = [t.id for t in tasks]
        steps = db.execute(select(Subtask).where(Subtask.user_id == user_id, Subtask.task_id.in_(ids),
                                                 Subtask.done.is_(True))).scalars().all()
        add(reactions(db, user_id, ids, since, as_utc(now) + timedelta(seconds=1), _progress(list(tasks), steps)))
    return sums


def _count(prof: dict, suffixes: tuple[str, ...], field: str) -> int:
    return sum(row.get(field, 0) for key, row in prof.items() if key.endswith(suffixes))


def adapt(prof: dict, state: str, stage: str, tiny: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(reroute to this stage or None, hint line or None, rule name or None) for the stage Buddy is about
    to speak on. `tiny` is the framework's tiny-move stage."""
    cause = CAUSE_OF_STATE.get(state)
    if not prof or not cause:
        return None, None, None
    if stage == "offer":
        own = _count(prof, (".offer", ".asked_their_step"), "own_plan")
        wanted = _count(prof, (".offer",), "wanted_move")
        if own >= RULE_MIN and own > wanted:
            return None, ADAPT_HINTS["own_plan_first"], "own_plan_first"
        if wanted >= RULE_MIN and _count(prof, (".offer",), "own_plan") == 0:
            _, hint, rule = adapt(prof, state, tiny, tiny)
            return tiny, hint, f"move_first+{rule}" if rule else "move_first"
        return None, None, None
    move = MOVES.get((state, stage))
    if move not in MOVE_TEXT or move in ("offer", "asked_their_step"):
        return None, None, None
    row = prof.get(f"{cause}.{move}", {})
    if row.get("helped", 0) >= RULE_MIN:
        return None, ADAPT_HINTS["lean_on_helped"].format(move=MOVE_TEXT[move]), "lean_on_helped"
    if row.get("declined", 0) >= RULE_MIN and not row.get("took") and not row.get("helped"):
        return None, ADAPT_HINTS["avoid_declined"].format(move=MOVE_TEXT[move]), "avoid_declined"
    return None, None, None
