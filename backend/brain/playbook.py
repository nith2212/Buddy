# Deterministic playbook retrieval — no embeddings, no vector search.
#
# By the time get_playbook() is called, the state has already been classified
# (a fixed label like "avoidance"), so "retrieval" is just: open the matching
# state doc, pull in the intervention docs tagged for that state, and always
# include the core philosophy docs. A real similarity search would be solving
# a problem we don't have — the corpus is 12 files and the query is a label,
# not free text. See CLAUDE.md for the Qdrant/embedding fallback kept behind
# USE_QDRANT for when the corpus grows past "a dozen hand-labeled docs".

from __future__ import annotations

import os
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
        ))
    return tuple(docs)


def get_playbook(state: str) -> str:
    """
    Return the playbook text for a detected work state: core principles +
    the state's definition doc (if any) + every intervention doc tagged for
    that state. Joined as one text blob, ready for direct LLM prompt injection.
    """
    docs = _load_docs()
    core = [d for d in docs if d.category == "core_principle"]
    state_doc = [d for d in docs if d.category == "state_definition" and d.state == state]
    interventions = [d for d in docs if d.category == "intervention" and state in d.designed_for_states]

    if not state_doc:
        # Unknown/unmapped state — still return core principles so the LLM has
        # something grounded, rather than an empty playbook.
        selected = core
    else:
        selected = core + state_doc + interventions

    return "\n\n---\n\n".join(d.body for d in selected)
