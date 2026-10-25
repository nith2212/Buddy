# Mechanical checks on Buddy's drafted reply. Prompt rules alone aren't reliable on a
# small model, and these failures are detectable without another LLM call.
#
# "hard" violations must never reach the user: stock sympathy filler (the generic
# therapy-speak Buddy exists to avoid) and clock times the user never mentioned
# (the model copying or inventing a deadline). "soft" violations (too long, too many
# questions, ignores the task) are worth one rewrite but are acceptable if the
# rewrite doesn't fix them.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Banning "That sounds…" alone just moves the model to "It sounds like…" / "Sounds like you're…",
# so the whole family is covered.
_STOCK = re.compile(
    r"(?:(?:^|[.!?]\s+)(?:that sounds|it sounds|sounds|i hear you|i understand|hey there)\b"
    r"|\bsounds like\b"
    r"|\bit'?s (?:totally |completely |perfectly )?(?:okay|ok) to feel\b"
    r"|\b(?:totally|completely) understandable\b"
    r"|\bit'?s understandable\b)",
    re.IGNORECASE,
)

# Resources the model likes to invent ("watch a quick intro video"); fine if the user or the task said it first.
_RESOURCES = re.compile(r"\b(?:videos?|tutorials?|youtube|courses?|podcasts?|articles?|blog posts?)\b", re.IGNORECASE)

# "Clean my room: …" — the task name used as a label instead of woven into a sentence.
_LABEL_START = re.compile(r"^\s*(?:\S+\s+){0,5}\S+:\s")

# "9pm", "9 p.m.", "9:30 pm" and 24-hour "21:30".
_CLOCK = re.compile(
    r"\b(?:(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*[ap]\.?\s?m\.?|(?:[01]?\d|2[0-3]):[0-5]\d)(?!\w)",
    re.IGNORECASE,
)

_SENTENCE_END = re.compile(r"[.!?]+(?:\s+|$)")

_STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "this", "that", "your", "task", "step",
    "make", "write", "finish", "start", "about", "have", "done", "what", "when", "then",
}

_MESSAGES = {
    "stock_phrase": 'Do not use sympathy filler. Never open with or use "That sounds…", '
                    '"It\'s okay to feel…", "It\'s totally understandable", "I hear you", "I understand" or "Hey there".',
    "clock_time": "Do not mention any clock time or date. Say things like \"today\" or \"tonight\" instead.",
    "too_many_questions": "Ask at most one question (none in a closing notification).",
    "too_long": "Make it shorter.",
    "invented_resource": "Do not suggest videos, tutorials, courses or other resources the user didn't mention.",
    "label_style": "Mention the task naturally inside a sentence. Never start with a label followed by a colon.",
    "no_task_reference": "Name the task or one of its open steps (unless you are stepping back because "
                         "the user's message is about something bigger than this task).",
}


@dataclass(frozen=True)
class Violations:
    hard: tuple[str, ...] = ()
    soft: tuple[str, ...] = ()

    @property
    def any(self) -> bool:
        return bool(self.hard or self.soft)

    def describe(self) -> str:
        return "\n".join(f"- {_MESSAGES[code]}" for code in (*self.hard, *self.soft))


def salient_words(*texts: str | None) -> set[str]:
    """Distinctive words from a task/step title, used to check a reply actually mentions them."""
    words: set[str] = set()
    for text in texts:
        for w in re.findall(r"[a-z]+", (text or "").lower()):
            if len(w) >= 3 and w not in _STOPWORDS:
                words.add(w)
    return words


def _normalize_clock(text: str) -> str:
    return re.sub(r"[\s.]", "", text.lower())


def check_reply(
    reply: str,
    *,
    max_sentences: int,
    max_questions: int,
    user_message: str | None,
    anchor_words: Iterable[str],
    max_chars: int | None = None,
) -> Violations:
    hard: list[str] = []
    soft: list[str] = []

    if _STOCK.search(reply):
        hard.append("stock_phrase")

    said_by_user = {_normalize_clock(m.group(0)) for m in _CLOCK.finditer(user_message or "")}
    if any(_normalize_clock(m.group(0)) not in said_by_user for m in _CLOCK.finditer(reply)):
        hard.append("clock_time")

    if reply.count("?") > max_questions:
        soft.append("too_many_questions")

    sentences = [s for s in _SENTENCE_END.split(reply.strip()) if s.strip()]
    if len(sentences) > max_sentences or (max_chars is not None and len(reply) > max_chars):
        soft.append("too_long")

    context_words = f"{user_message or ''} {' '.join(anchor_words)}".lower()
    if any(m.group(0).lower().rstrip("s") not in context_words for m in _RESOURCES.finditer(reply)):
        soft.append("invented_resource")

    if _LABEL_START.match(reply):
        soft.append("label_style")

    anchors = set(anchor_words)
    if anchors and not any(re.search(rf"\b{re.escape(w)}", reply, re.IGNORECASE) for w in anchors):
        soft.append("no_task_reference")

    return Violations(tuple(hard), tuple(soft))
