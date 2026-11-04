# Make a grading packet: everything a grader (Claude, Copilot, a person) needs to grade one run's
# replies by hand, plus a blank grades file to fill in. See testing/GRADING.md.
#
# From the repo root (buddy/):
#   backend/venv/bin/python -m testing.grading.export testing/results/<run>.json
#   backend/venv/bin/python -m testing.grading.export testing/results/<run>.json --states perfectionism,fatigue
#   backend/venv/bin/python -m testing.grading.export testing/results/<run>.json --only ambiguity_main
#
# Writes testing/grading/packets/<run>[_<states>].md and a blank testing/grading/grades/<run>[_<states>].todo.json.
# Fill in the .todo.json (see GRADING.md), rename it to .json, then run testing.grading.merge.

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testing.evals.run import CRITERIA
from testing.evals.scenarios import SCENARIOS

HERE = Path(__file__).resolve().parent
TESTING = HERE.parent
DOCS = TESTING.parent / "backend" / "brain" / "buddy_docs"
FALLBACK_MARK = "I'm having trouble finding my words"
TASKS = {sc["id"]: sc["task"] for sc in SCENARIOS}


def framework_text(state: str) -> str:
    path = DOCS / f"framework_{state}.md"
    text = path.read_text() if path.exists() else f"(no framework doc for {state})"
    return text.split("---", 2)[-1].strip() if text.startswith("---") else text


def pick(results: list[dict], states: set[str] | None, only: set[str] | None) -> list[dict]:
    out = []
    for r in results:
        if states and r["state"] not in states:
            continue
        if only and r["id"] not in only:
            continue
        out.append(r)
    return out


def packet(run_path: Path, results: list[dict], meta: dict) -> str:
    states = list(dict.fromkeys(r["state"] for r in results))
    out = [f"# Grading packet: {run_path.name}", "",
           f"- Writer model: `{meta.get('model')}` · code: {meta.get('commit')}",
           f"- {len(results)} conversations, {sum(len(r['turns']) for r in results)} Buddy replies to grade",
           "- Rules: testing/GRADING.md (read it first). Grade every reply `B[n]` on all 7 criteria.", "",
           "## Criteria (order of the 7 letters)", ""]
    out += [f"{i}. **{key}**: {text}" for i, (key, text) in enumerate(CRITERIA.items(), 1)]
    out += ["", "## Shared framework", "", framework_text("shared"), ""]
    for s in states:
        out += [f"## Framework: {s}", "", framework_text(s), ""]
    out += ["## Conversations", ""]
    for r in results:
        task = TASKS.get(r["id"], {})
        out.append(f"### {r['id']}  (state: {r['state']}; cause expected `{r.get('expect_cause')}`, "
                   f"saved `{r.get('saved_cause')}`)")
        if task:
            out.append(f"Task: \"{task.get('title')}\", due in {task.get('due_in_days')} days (real timing)")
        out.append("")
        for i, t in enumerate(r["turns"]):
            out.append(f"- U[{i}]: {t['user'] if t['user'] else '(Buddy speaks first)'}")
            extra = []
            if t.get("state"):
                extra.append(f"code's stage: {t['state']}")
            if t.get("fallback") or FALLBACK_MARK in (t.get("reply") or ""):
                extra.append("CANNED FALLBACK")
            if t.get("flags"):
                extra.append("flags: " + ", ".join(t["flags"]))
            out.append(f"- **B[{i}]**: {t['reply']}" + (f"  _({'; '.join(extra)})_" if extra else ""))
        out.append("")
    return "\n".join(out)


def blank(run_path: Path, results: list[dict]) -> dict:
    return {"grader": "<who graded: claude / copilot / your name>",
            "order": list(CRITERIA),
            "files": {run_path.name: {r["id"]: [["???????", "<why, for every n>"] for _ in r["turns"]]
                                      for r in results}}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", help="results .json from testing/results/")
    ap.add_argument("--states", help="comma-separated states to include (default: all)")
    ap.add_argument("--only", help="comma-separated scenario ids")
    args = ap.parse_args()
    run_path = Path(args.run)
    data = json.loads(run_path.read_text())
    states = set(args.states.split(",")) if args.states else None
    only = set(args.only.split(",")) if args.only else None
    results = pick(data["results"], states, only)
    if not results:
        raise SystemExit("no conversations match")
    suffix = f"_{'-'.join(sorted(states))}" if states else (f"_{'-'.join(sorted(only))}" if only else "")
    (HERE / "packets").mkdir(exist_ok=True)
    (HERE / "grades").mkdir(exist_ok=True)
    pkt = HERE / "packets" / f"{run_path.stem}{suffix}.md"
    todo = HERE / "grades" / f"{run_path.stem}{suffix}.todo.json"
    pkt.write_text(packet(run_path, results, data.get("meta", {})))
    if not todo.exists():
        todo.write_text(json.dumps(blank(run_path, results), indent=1))
    print(f"Packet: {pkt}\nBlank grades: {todo}")


if __name__ == "__main__":
    main()
