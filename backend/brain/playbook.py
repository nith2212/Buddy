# Deterministic playbook retrieval — no embeddings, no vector search.
#
# By the time a doc is looked up, the state has already been classified
# (a fixed label like "avoidance"), so "retrieval" is just: open the matching
# state doc, pull in the intervention docs tagged for that state, and always
# include the core philosophy docs. A similarity search would be solving a
# problem we don't have: the corpus is a couple of dozen hand-labeled files and
# the query is a label, not free text.
#
# Two kinds of docs: framework_*.md drive tapped-reason chats (brain/flow.py);
# core_*, state_* and intervention_*.md drive the generic path in agent.py
# (closing notifications and chats with no recent reason tap).

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache

DOCS_DIR = os.path.join(os.path.dirname(__file__), "buddy_docs")


@dataclass(frozen=True)
class PlaybookDoc:
    doc_id: str
    category: str
    body: str
    designed_for_states: tuple[str, ...] = ()
    state: str | None = None
    intervention: str | None = None


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a doc into (frontmatter dict, body). Values are strings or lists of strings."""
    if not text.startswith("---"):
        return {}, text
    _, fm_block, body = text.split("---", 2)
    meta: dict = {}
    for line in fm_block.strip().splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    return meta, body.strip()


@lru_cache(maxsize=1)
def _load_docs() -> tuple[PlaybookDoc, ...]:
    """Load and parse every doc once per process; buddy_docs/ is static, deployed read-only content."""
    docs = []
    for filename in sorted(os.listdir(DOCS_DIR)):
        if not filename.endswith(".md"):
            continue
        with open(os.path.join(DOCS_DIR, filename), encoding="utf-8") as f:
            meta, body = _parse_frontmatter(f.read())
        docs.append(PlaybookDoc(
            doc_id=meta.get("doc_id", filename),
            category=meta.get("category", "unknown"),
            body=body,
            designed_for_states=tuple(meta.get("designed_for_states", [])),
            state=meta.get("state"),
            intervention=meta.get("intervention"),
        ))
    return tuple(docs)


_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)

# Parts of an intervention doc the model should not see when writing: quoted example lines get
# cloned almost word for word (a literal "before 9pm" became every reply's deadline), and the
# academic grounding theory is tokens spent on nothing the writer can use.
_NOT_FOR_WRITER = ("What this looks like", "Grounding theory")
# What a state doc tells Buddy about how to *be* with someone in that state.
_STANCE = ("What this is", "What it is NOT", "Buddy's internal")


def _sections(body: str) -> list[tuple[str, str]]:
    parts = _HEADING.split(body)  # [preamble, heading, text, heading, text, ...]
    return [("", parts[0])] + [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]


def _join(sections: list[tuple[str, str]]) -> str:
    return "".join(f"## {h}{t}" if h else t for h, t in sections).strip()


def drop_sections(body: str, prefixes: tuple[str, ...]) -> str:
    return _join([(h, t) for h, t in _sections(body) if not h.startswith(prefixes)])


def keep_sections(body: str, prefixes: tuple[str, ...]) -> str:
    return _join([(h, t) for h, t in _sections(body) if h == "" or h.startswith(prefixes)])


def intervention_text(doc: PlaybookDoc) -> str:
    """An intervention doc as the model should read it: purpose and do's/don'ts, no examples or theory."""
    return drop_sections(doc.body, _NOT_FOR_WRITER)


def state_stance(state: str | None) -> str | None:
    body = get_state_doc(state)
    return keep_sections(body, _STANCE) if body else None


def get_doc(doc_id: str) -> str | None:
    """Body of a single doc by doc_id (e.g. "core_buddy_philosophy"), or None."""
    return next((d.body for d in _load_docs() if d.doc_id == doc_id), None)


def get_intervention(name: str) -> PlaybookDoc | None:
    """One intervention doc by its id (e.g. "find_the_cause"), or None."""
    return next((d for d in _load_docs() if d.category == "intervention" and d.intervention == name), None)


def get_state_doc(state: str | None) -> str | None:
    return next((d.body for d in _load_docs() if d.category == "state_definition" and d.state == state), None)


def interventions_for(state: str | None) -> list[PlaybookDoc]:
    """Intervention docs tagged for `state`; every intervention if the state is unknown/None."""
    all_interventions = [d for d in _load_docs() if d.category == "intervention"]
    tagged = [d for d in all_interventions if state in d.designed_for_states]
    return tagged or all_interventions


def framework_section(state: str, heading: str) -> str | None:
    """One stage's (or shared part's) text from a framework doc (buddy_docs/framework_<state>.md)."""
    doc = next((d for d in _load_docs() if d.category == "framework" and d.state == state), None)
    if doc is None:
        return None
    text = next((t for h, t in _sections(doc.body) if h.strip() == heading), None)
    return text.strip() if text else None


def has_framework(state: str | None) -> bool:
    return any(d.category == "framework" and d.state == state for d in _load_docs())
