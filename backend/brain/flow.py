# The per-state conversation frameworks (state_frameworks.md) as a stage machine.
#
# Code decides the stage; the model only words it. Each user message is read once
# (`read_message`: cheap patterns first, one small JSON call for the rest), then
# `next_stage` moves the conversation by a fixed table. When the read is unsure or fails,
# the conversation stays on its stage instead of jumping ahead on a wrong guess, and the
# writer is told to respond to what was said and re-ask. After MAX_TRIES Buddy turns on
# one stage it offers the choice ("a tiny move, or do you know what you'll do?").
#
# Stage wording lives in buddy_docs/framework_*.md, not here.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from brain import llm

KINDS = ("idk", "answer", "confirm", "reject", "unsure", "own_plan", "accept", "wants_move", "ack", "new_cause",
         "bigger")
DONE_KINDS = ("ack", "own_plan", "accept")  # the user is set: wrap up
CAUSES = {
    "unclear": "not knowing where to start",
    "too_much": "the task feels too big",
    "afraid": "fear that it won't be good enough",
    "bored": "it feels boring or pointless",
    "tired": "being tired or drained",
}
STATE_OF = {"unclear": "ambiguity", "too_much": "overwhelm", "afraid": "perfectionism", "bored": "low_interest",
            "tired": "fatigue"}
CAUSE_OF = {v: k for k, v in STATE_OF.items()}
MAX_TRIES = 2  # Buddy turns on one stage before offering the choice

# Shared stages, available in every framework.
GENERIC = ("release", "step_back", "offer", "followup")


@dataclass(frozen=True)
class Framework:
    first: str                                  # Buddy's opening stage
    on: dict[tuple[str, str], str]              # (stage, kind) -> next stage
    switch_entry: str                           # where to start when the user switches INTO this state
    tiny: str                                   # the stage where Buddy offers its one tiny move
    save_on: frozenset[tuple[str, str]]         # (stage, kind) that confirm the cause; ("*", kind) = any stage
    flavors: dict[str, tuple[str, ...]] = field(default_factory=dict)   # stage -> flavors the read can return
    by_flavor: dict[tuple[str, str], str] = field(default_factory=dict)  # (stage, flavor) -> next stage
    notes: dict[str, str] = field(default_factory=dict)  # stage -> what the user's answer there is ("goal")
    move: Optional[str] = None                  # where "wants_move" goes (default: tiny)


FRAMEWORKS: dict[str, Framework] = {
    "ambiguity": Framework(
        first="open",
        on={("open", "answer"): "core", ("open", "confirm"): "core", ("open", "unsure"): "core",
            ("core", "answer"): "first_step", ("core", "confirm"): "first_step", ("core", "unsure"): "first_step",
            ("suggest", "answer"): "suggest",
            # naming a part after the offer ("maybe the swipe thing?") is their core: they still author the step
            ("offer", "answer"): "first_step"},
        switch_entry="open", tiny="suggest",
        save_on=frozenset({("*", "own_plan")}),
        notes={"open": "goal", "core": "core", "offer": "core", "first_step": "first step"},
    ),
    "perfectionism": Framework(
        first="open",
        on={("open", "idk"): "narrow", ("open", "answer"): "confirm", ("open", "unsure"): "narrow",
            ("open", "confirm"): "reframe",
            ("narrow", "confirm"): "reframe", ("narrow", "answer"): "confirm",
            ("confirm", "confirm"): "reframe", ("confirm", "reject"): "narrow", ("confirm", "unsure"): "narrow",
            ("reframe", "confirm"): "release", ("reframe", "reject"): "offer"},
        switch_entry="confirm", tiny="reframe",
        save_on=frozenset({("narrow", "confirm"), ("confirm", "confirm"), ("open", "confirm")}),
        notes={"open": "worry", "narrow": "worry", "confirm": "worry"},
    ),
    "fatigue": Framework(
        first="open",
        on={("open", "answer"): "rest", ("open", "confirm"): "rest", ("open", "idk"): "rest",
            ("open", "unsure"): "rest", ("rest", "answer"): "rest", ("offer", "idk"): "move",
            ("move", "answer"): "move"},
        switch_entry="rest", tiny="move", move="offer",
        save_on=frozenset({("open", "answer"), ("open", "confirm"), ("open", "idk"), ("open", "unsure"),
                           ("open", "wants_move")}),
        notes={"open": "their day"},
    ),
    "overwhelm": Framework(
        first="open",
        on={("open", "idk"): "micro", ("open", "answer"): "micro", ("open", "unsure"): "micro",
            ("open", "confirm"): "micro", ("micro", "confirm"): "release", ("micro", "answer"): "micro"},
        switch_entry="open", tiny="micro",
        save_on=frozenset({("*", "own_plan"), ("micro", "confirm")}),
        notes={"open": "what feels big"},
    ),
    "low_interest": Framework(
        first="open",
        on={("open", "answer"): "narrow", ("open", "idk"): "narrow", ("open", "unsure"): "narrow",
            ("open", "reject"): "narrow",       # "no, I HAVE to do it": it can't be dropped, so on to why it drags
            ("narrow", "confirm"): "lighten",   # "I just don't like it": boring, accept that and make it lighter
            ("purpose", "idk"): "lighten", ("purpose", "reject"): "lighten", ("own_reason", "answer"): "release", ("own_reason", "unsure"): "release",
            ("own_reason", "reject"): "release", ("lighten", "answer"): "lighten"},
        switch_entry="open", tiny="lighten",
        save_on=frozenset({("narrow", "confirm"), ("narrow", "answer"), ("*", "own_plan")}),
        flavors={"narrow": ("boring", "pointless"), "purpose": ("found", "none")},
        by_flavor={("narrow", "boring"): "lighten", ("narrow", "pointless"): "purpose",
                   ("purpose", "found"): "own_reason", ("purpose", "none"): "lighten"},
        notes={"open": "why it needs doing", "purpose": "what it could give them"},
    ),
}

# Stages whose reply must ask something, and stages whose reply must not.
ASKS = {"open", "core", "first_step", "suggest", "narrow", "confirm", "reframe", "micro", "lighten", "purpose",
        "offer"}
NO_QUESTION = {"release", "step_back", "rest", "own_reason"}


@dataclass(frozen=True)
class Reading:
    kind: str                     # one of KINDS, or "unclear" when the read failed
    cause: Optional[str] = None   # for confirm / new_cause
    flavor: Optional[str] = None  # e.g. boring / pointless
    fact: Optional[str] = None    # their key point, in their words
    source: str = "model"         # "pattern" when caught without a model call


@dataclass(frozen=True)
class Step:
    state: str
    stage: str
    modifier: Optional[str] = None  # idk / unsure / reject / unclear / stay: how to word a repeated stage
    save_cause: Optional[str] = None
    note: Optional[tuple[str, str]] = None


def next_stage(state: str, stage: str, reading: Reading, tries: int) -> Step:
    """Where the conversation goes after the user's message. `tries` = Buddy turns already on `stage`."""
    fw = FRAMEWORKS[state]
    kind = reading.kind
    note = _note(fw, stage, reading)

    if stage == "step_back" or kind == "bigger":
        return Step(state, "step_back")  # stays stepped back for the rest of this session
    if kind == "new_cause" and reading.cause and STATE_OF.get(reading.cause) not in (None, state):
        new_state = STATE_OF[reading.cause]
        return Step(new_state, FRAMEWORKS[new_state].switch_entry, save_cause=reading.cause, note=note)
    if kind == "new_cause":
        # "Revealed" the cause already being discussed: describing it unprompted is an answer;
        # naming it after Buddy offered options is a confirmation.
        kind = "answer" if stage == fw.first else "confirm"

    if stage in ("release", "followup"):
        return Step(state, "release" if kind in DONE_KINDS else "followup", note=note)
    if kind == "accept" and stage != "offer":  # "sure" to "a move from me, or yours?" means "give me one"
        # They took Buddy's move: it counts like their own plan for the cause, but the idea was Buddy's,
        # so the wrap-up must never credit them with it.
        return Step(state, "release", modifier="accepted", save_cause=_save(fw, stage, "own_plan"), note=note)
    if kind in ("ack", "own_plan"):
        return Step(state, "release", save_cause=_save(fw, stage, kind), note=_plan_note(reading) or note)
    if stage == "offer":
        if (stage, kind) in fw.on:
            return Step(state, fw.on[(stage, kind)], note=note)
        # Anything else but a no means "go on, give me one".
        if kind == "reject":
            return Step(state, "offer", modifier="reject", note=note)
        return Step(state, fw.tiny, note=note)
    if kind == "wants_move":
        return Step(state, fw.move or fw.tiny, save_cause=_save(fw, stage, kind), note=note)

    nxt = None
    if reading.flavor and (stage, reading.flavor) in fw.by_flavor:
        nxt = fw.by_flavor[(stage, reading.flavor)]
    elif (stage, kind) in fw.on:
        nxt = fw.on[(stage, kind)]
    if nxt and nxt != stage:
        return Step(state, nxt, save_cause=_save(fw, stage, kind), note=note)

    # Staying on this stage: say it differently, and after a few tries offer the choice instead.
    if tries >= MAX_TRIES:
        return Step(state, "offer", note=note)
    modifier = {"idk": "idk", "unsure": "unsure", "reject": "reject", "unclear": "unclear"}.get(kind, "stay")
    return Step(state, stage, modifier=modifier, save_cause=_save(fw, stage, kind), note=note)


def _save(fw: Framework, stage: str, kind: str) -> Optional[str]:
    if (stage, kind) in fw.save_on or ("*", kind) in fw.save_on:
        return next(c for c, s in STATE_OF.items() if FRAMEWORKS.get(s) is fw)
    return None


def _note(fw: Framework, stage: str, reading: Reading) -> Optional[tuple[str, str]]:
    if reading.fact and stage in fw.notes and reading.kind in ("answer", "confirm", "unsure", "new_cause"):
        return fw.notes[stage], reading.fact
    return None


def _plan_note(reading: Reading) -> Optional[tuple[str, str]]:
    return ("their plan", reading.fact) if reading.kind == "own_plan" and reading.fact else None


# ── reading the user's message ───────────────────────────────────────────────

_ACK_WORDS = {
    "ok", "okay", "okie", "k", "kk", "thanks", "thank", "thx", "ty", "you", "got", "it", "cool", "sure",
    "alright", "will", "do", "noted", "great", "perfect", "awesome", "nice", "good", "sounds", "appreciate",
    "that", "helps", "helpful", "yep", "yup", "so", "much", "very", "bye", "byee", "cya", "see", "ya", "later",
}
_IDK = re.compile(
    r"^\W*(?:u+m+|hm+|idk+|i\s*(?:really\s*)?d(?:o|u)n'?t\s*know+|no\s*idea|not\s*sure|dunno|no\s*clue|"
    r"idk\s*(?:bro|tbh|honestly)|honestly\s*idk|not\s*sure\s*tbh|i\s*have\s*no\s*idea)\W*(?:bro|tbh|honestly)?\W*$",
    re.IGNORECASE)
# Clear signs of distress beyond work: step back without waiting on a model (a false positive
# costs a gentle check-in; a miss costs much more).
_DISTRESS = re.compile(
    r"\b(?:kill myself|suicid\w*|self[- ]harm|want to die|end it all|can'?t stop crying|hospital|"
    r"failure at everything|hopeless|feel(?:ing)? numb|point of anything|panic attacks?)\b",
    re.IGNORECASE)


def is_ack(message: str) -> bool:
    if "?" in message:
        return False
    words = re.findall(r"[a-z']+", message.lower())
    return 0 < len(words) <= 6 and all(w in _ACK_WORDS for w in words)


# Clear tiredness: switch to the tired framework without waiting on a model (pushing a tired person
# is the worst miss). Only from other states; in the tired framework it's just an answer.
_TIRED = re.compile(
    r"\b(?:exhausted|drained|wiped out|worn out|burn(?:ed|t) out|no energy|so tired|too tired|really tired|"
    r"dead tired|knackered)\b", re.IGNORECASE)
_SIGN_OFF = re.compile(r"\b(?:thanks?|thx|ty|bye+|cya|later|appreciate)\b", re.IGNORECASE)


def pattern_read(message: str, buddy_said: Optional[str] = None, state: Optional[str] = None) -> Optional[Reading]:
    """The easy cases, no model call."""
    if _DISTRESS.search(message):
        return Reading("bigger", source="pattern")
    if state and state != "fatigue" and _TIRED.search(message):
        return Reading("new_cause", "tired", source="pattern")
    # A bare "okay" to a question isn't a sign-off ("sure" to "want a tiny move?" means yes): let the model read it.
    if is_ack(message) and ("?" not in (buddy_said or "") or _SIGN_OFF.search(message)):
        return Reading("ack", source="pattern")
    if _IDK.match(message.strip()):
        return Reading("idk", source="pattern")
    return None


_READ_SYSTEM = (
    "You read one message from a user chatting with Buddy, a companion that helps people start a task by finding "
    "out why they're stuck. Classify the message as a reply to what Buddy just said.\n"
    "kind, pick exactly one:\n"
    "- idk: they don't know / have no answer\n"
    "- answer: answers Buddy's question with content, without agreeing to a cause Buddy offered. Naming a part "
    "or area of the task without saying what they'll do (\"maybe the swipe thing?\") is answer, not own_plan\n"
    "- confirm: clearly agrees with the cause or option Buddy offered, or clearly names that cause themselves "
    "(picking one side of Buddy's either/or question counts)\n"
    "- reject: says Buddy's read is wrong, or declines Buddy's idea without giving their own\n"
    "- unsure: half-agrees, hedges (\"maybe\", \"kinda\"), or picks both sides\n"
    "- own_plan: names a specific action THEY came up with, different from any step Buddy offered (deciding to "
    "drop or postpone the task counts)\n"
    "- accept: agrees to the step or move Buddy just offered (\"okay I can do that\", \"haha sounds fun\")\n"
    "- wants_move: asks Buddy for a step or for help choosing, or wants to do something without saying what "
    "(\"I need to get something done\")\n"
    "- ack: only thanks or a sign-off\n"
    "- new_cause: reveals a DIFFERENT reason they're stuck than the one being discussed\n"
    "- bigger: distress beyond work (health, safety, grief, crisis, feeling worthless)\n"
    "cause (only for confirm or new_cause, else null): one of " + ", ".join(f"{k} ({v})" for k, v in CAUSES.items())
    + "\nflavor: only when the options below list some, else null. boring = dull, tedious, they dislike doing "
    "it; pointless = they see no use or point in it.\n"
    "fact: their key point in at most 12 words, in their own words, or null.\n"
    'Reply with JSON only: {"kind": "...", "cause": null, "flavor": null, "fact": null}'
)


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


# The reader's answer shape, owned here (models with structured outputs return exactly this).
READ_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "cause": _nullable({"type": "string", "enum": list(CAUSES)}),
        "flavor": _nullable({"type": "string"}),
        "fact": _nullable({"type": "string"}),
    },
    "required": ["kind", "cause", "flavor", "fact"],
    "additionalProperties": False,
}


async def read_message(state: str, stage: str, buddy_said: Optional[str], message: str) -> Reading:
    """One reading of the user's message. Any failure is 'unclear' (the caller stays on the stage)."""
    caught = pattern_read(message, buddy_said, state)
    if caught:
        return caught
    flavors = FRAMEWORKS[state].flavors.get(stage, ())
    prompt = (
        f"What Buddy is helping with: {CAUSES[CAUSE_OF[state]]}\n"
        f"Buddy just said: {buddy_said or '(nothing yet)'}\n"
        f"User replied: {message[:600]}\n"
        + (f"flavor options: {', '.join(flavors)}" if flavors else "flavor options: none")
    )
    try:
        raw = await llm.complete(
            [{"role": "system", "content": _READ_SYSTEM}, {"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=400, json_mode=True, json_schema=READ_SCHEMA, timeout=10.0, retries=1,
        )
        parsed = json.loads(raw)
        kind = parsed.get("kind")
    except (llm.LLMError, ValueError, AttributeError):
        return Reading("unclear")
    if kind not in KINDS:
        return Reading("unclear")
    cause = parsed.get("cause") if kind in ("confirm", "new_cause") and parsed.get("cause") in CAUSES else None
    if kind == "new_cause" and cause is None:
        kind = "answer"
    flavor = parsed.get("flavor") if parsed.get("flavor") in flavors else None
    fact = parsed.get("fact")
    fact = fact.strip()[:120] if isinstance(fact, str) and fact.strip() else None
    return Reading(kind, cause, flavor, fact)
