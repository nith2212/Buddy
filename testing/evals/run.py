# Eval run (docs/PIVOTS.md build plan, step 1): scripted conversations through Buddy's real pipeline
# (the FastAPI app on a throwaway SQLite DB) against real Groq, scored three ways:
#   1. mechanical checks on every reply (the target rules, independent of how the code is built)
#   2. a rubric graded by a bigger model, from docs/state_frameworks.md
#   3. a markdown report the developer reads, with the dream version next to each transcript
#
# From the repo root (buddy/), see testing/README.md:
#   backend/venv/bin/python -m testing.evals.run                      # all scenarios, current GROQ_MODEL
#   backend/venv/bin/python -m testing.evals.run --model openai/gpt-oss-120b --no-rubric
#   backend/venv/bin/python -m testing.evals.run --only ambiguity_main,fatigue_main --no-rubric
#   backend/venv/bin/python -m testing.evals.run --resume testing/results/<run>.json  # finish a cut-short run
#   backend/venv/bin/python -m testing.evals.run --regrade testing/results/<run>.json # re-score with Groq's grader
#
# Not part of pytest: it spends real Groq quota and replies vary run to run. Per-minute limits are
# waited out (Retry-After). When the daily limit hits, the run stops cleanly: the scenario in
# progress is dropped (its replies would be quota fallbacks, not Buddy) and --resume finishes it later.

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
FRAMEWORKS = HERE.parent.parent / "docs" / "state_frameworks.md"
DEFAULT_GRADER = "openai/gpt-oss-120b"

# ── mechanical checks (the target rules from CLAUDE.md / docs/state_frameworks.md) ─────────────
MAX_SENTENCES = 3
_SENTENCE_END = re.compile(r"[.!?]+(?:\s+|$)")
# The developer's voice allows warm reactions; these stay banned: therapy phrases, promises, pressure.
_BANNED = re.compile(
    r"\bi hear you\b|\bit['’]?s (?:totally |completely |perfectly )?(?:okay|ok) to feel\b|\bunderstandable\b"
    r"|\btrust me\b|\beasily fixed\b|\brelax\b|\bbuckle up\b|\bcalm down\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"\b(?:(?:1[0-2]|0?[1-9])(?::[0-5]\d)?\s*[ap]\.?\s?m\.?|(?:[01]?\d|2[0-3]):[0-5]\d)(?!\w)", re.IGNORECASE)
REPEAT_RATIO = 0.85

MECH_LABELS = {
    "http_error": "request failed",
    "fallback": "canned fallback reply (Groq failed or every draft broke a hard rule)",
    "too_many_questions": "more than one question",
    "too_long": f"more than {MAX_SENTENCES} sentences",
    "banned_phrase": "therapy phrase, promise or pressure",
    "clock_time": "invented clock time",
    "repeated_opener": "opens like an earlier reply",
    "repeats_earlier": "near-copy of an earlier reply",
    "question_in_release": "asks something after the user signed off",
}

CRITERIA = {
    "follows_framework": "Does it do what the framework says Buddy should do at this point in the conversation "
                         "(the right stage, the right kind of question or move)?",
    "reacts_to_user": "Does it respond to something specific the user just said, rather than a generic line? "
                      "(n/a for Buddy's opening message)",
    "offers_not_assigns": "If it suggests a step or technique, is it offered for the user to choose, or is it the "
                          "user's own idea? (n/a if it suggests nothing)",
    "no_premature_step": "Does it avoid giving a step, fix or technique earlier than the framework allows?",
    "keeps_their_plan": "If the user stated their own plan, does Buddy back it as they said it, without "
                        "shrinking, changing or adding to it? (n/a if they stated no plan)",
    "warm_voice": "Is it warm, kind and a little peppy, like a sweet friend, without therapy phrases, empty "
                  "cheering, lecturing or pressure?",
    "no_invention": "Does it avoid inventing facts about the user, the task, deadlines, tools, buttons or features?",
}


def _normalize(text: str) -> list[str]:
    return re.sub(r"\W+", " ", text.lower()).split()


def mechanical(reply: str, earlier: list[str], is_release: bool) -> list[str]:
    flags = []
    if reply.count("?") > 1:
        flags.append("too_many_questions")
    if len([s for s in _SENTENCE_END.split(reply.strip()) if s.strip()]) > MAX_SENTENCES:
        flags.append("too_long")
    if _BANNED.search(reply):
        flags.append("banned_phrase")
    if _CLOCK.search(reply):
        flags.append("clock_time")
    words = _normalize(reply)
    if len(words) >= 4 and any(_normalize(e)[:4] == words[:4] for e in earlier):
        flags.append("repeated_opener")
    if any(SequenceMatcher(None, " ".join(words), " ".join(_normalize(e))).ratio() >= REPEAT_RATIO for e in earlier):
        flags.append("repeats_earlier")
    if is_release and "?" in reply:
        flags.append("question_in_release")
    return flags


# ── frameworks (rubric context) ──────────────────────────────────────────────────────────

def load_frameworks() -> tuple[str, dict[str, str]]:
    """(shared rules, {state: framework text}) from docs/state_frameworks.md, examples excluded."""
    text = FRAMEWORKS.read_text().split("## Example conversations")[0]
    shared, states = "", {}
    for block in re.split(r"(?m)^## ", text)[1:]:
        heading = block.splitlines()[0]
        if heading.startswith("Shared"):
            shared = block
        elif m := re.search(r"\(([\w ]+)\)", heading):
            states[m.group(1).replace(" ", "_")] = block
    return shared, states


# ── Groq: patient calls + usage accounting ───────────────────────────────────────────────

class Usage(logging.Handler):
    """Counts calls and tokens from brain.llm's 'llm usage' log line, split writer vs grader."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.role = "pipeline"
        self.totals = {r: {"calls": 0, "prompt": 0, "completion": 0} for r in ("pipeline", "grader")}

    def emit(self, record):
        if record.getMessage().startswith("llm usage") and record.args:
            t = self.totals[self.role]
            t["calls"] += 1
            t["prompt"] += int(record.args[0] or 0)
            t["completion"] += int(record.args[1] or 0)


def make_patient(llm):
    original = llm.complete

    async def patient(messages, **kw):
        # Wait out the free tier's rate limits instead of falling back: a fallback is a quota
        # artifact, not something the eval should score.
        kw["retries"] = max(kw.get("retries", 2), 6)
        kw["max_wait"] = max(kw.get("max_wait", 20.0), 120.0)
        kw["timeout"] = max(kw.get("timeout", 15.0), 30.0)
        try:
            return await original(messages, **kw)
        except llm.LLMError as e:
            if "429" in str(e):
                patient.quota_hit = True  # Groq wants a longer wait than any run can give: the daily limit
            raise

    patient.quota_hit = False
    return patient


async def grade(llm, usage, grader, shared, framework, task, convo, reply) -> dict:
    criteria = "\n".join(f"- {k}: {v}" for k, v in CRITERIA.items())
    transcript = "\n".join(f"{who}: {text}" for who, text in convo) or "(Buddy speaks first)"
    prompt = (
        f"Shared rules:\n{shared}\n\nFramework for this state:\n{framework}\n\n"
        f"Task: {task}\n\nConversation so far:\n{transcript}\n\nBuddy's reply to grade:\n{reply}\n\n"
        f"Criteria:\n{criteria}"
    )
    keys = '"expected": "<one sentence: what the framework says Buddy should do at this exact point>", ' + ", ".join(f'"{k}": {{"verdict": "yes" | "no" | "n/a", "why": "<max 12 words>"}}' for k in CRITERIA)
    previous, usage.role = os.environ.get("GROQ_MODEL"), "grader"
    os.environ["GROQ_MODEL"] = grader
    try:
        raw = await llm.complete(
            [{"role": "system", "content": (
                "You grade one reply from Buddy, a task companion that helps people start by finding out why "
                "they're stuck. Judge only against the rules, the framework and the conversation. The task's timing "
                "in the Task line is real: Buddy mentioning it (in any wording, like 48 hours for 2 days) is not an "
                "invention. First work out which "
                "stage of the framework this point in the conversation is, and what Buddy should do there. Then "
                "grade. Be strict: \"yes\" only when the reply clearly meets the criterion; a reply that skips, "
                "repeats or mixes up a stage fails follows_framework. Reply with JSON only: {" + keys + "}")},
             {"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=1200, json_mode=True,
        )
        parsed = json.loads(raw)
        graded = {k: parsed.get(k) if isinstance(parsed.get(k), dict) else {"verdict": "error", "why": ""}
                  for k in CRITERIA}
        graded["_expected"] = str(parsed.get("expected", ""))[:300]
        return graded
    except (llm.LLMError, ValueError) as e:
        return {k: {"verdict": "error", "why": str(e)[:60]} for k in CRITERIA}
    finally:
        usage.role = "pipeline"
        if previous is None:
            os.environ.pop("GROQ_MODEL", None)
        else:
            os.environ["GROQ_MODEL"] = previous


# ── one scenario ─────────────────────────────────────────────────────────────────────────

def task_line(task: dict) -> str:
    days = task.get("due_in_days")
    return f'"{task["title"]}", ' + (f"due in about {days} days" if days is not None else "no due date") + \
        " (Buddy may mention this real timing)"


def run_scenario(api, sc, models, SessionLocal) -> dict:
    from sqlalchemy import select

    h = {"Authorization": "Bearer " + api.post("/auth/anonymous", headers={"X-Invite-Code": "eval-invite"})
         .json()["token"]}
    days = sc["task"].get("due_in_days")
    due = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat() if days is not None else None
    task_id = api.post("/tasks", json={"title": sc["task"]["title"], "due_date": due}, headers=h).json()["id"]
    for step in sc["task"].get("steps", []):
        api.post(f"/tasks/{task_id}/subtasks", json={"title": step}, headers=h)

    def latest_reasoning() -> dict:
        with SessionLocal() as db:
            raw = db.execute(
                select(models.Message.reasoning).where(models.Message.task_id == task_id,
                                                       models.Message.role == "assistant")
                .order_by(models.Message.id.desc()).limit(1)).scalar_one_or_none()
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            return {}

    turns = []
    sends = [{"reason": sc["chip"]}] + [{"message": line} for line in sc["user"]]
    for i, payload in enumerate(sends):
        started = time.monotonic()
        r = api.post("/chat", json={"task_id": task_id, **payload}, headers=h)
        took = time.monotonic() - started
        ok = r.status_code == 200
        reasoning = latest_reasoning() if ok else {}
        turns.append({
            "user": payload.get("message"),
            "reply": r.json()["reply"] if ok else f"(HTTP {r.status_code})",
            "status": r.status_code,
            "seconds": round(took, 1),
            "phase": reasoning.get("phase"),
            "intervention": reasoning.get("intervention"),
            "state": (reasoning.get("flow") or {}).get("state"),
            "read": ((reasoning.get("flow") or {}).get("read") or {}).get("kind"),
            "fallback": bool(reasoning.get("fallback")),
            "checks": reasoning.get("checks") or {},
        })
        print(f"  {sc['id']} turn {i + 1}/{len(sends)}  {took:.0f}s", flush=True)

    with SessionLocal() as db:
        saved = db.execute(select(models.Memory.value).where(
            models.Memory.key == f"blocker.task.{task_id}")).scalar_one_or_none()
    return {"turns": turns, "saved_cause": saved}


# ── report ───────────────────────────────────────────────────────────────────────────────

def _pct(yes: int, no: int) -> str:
    return f"{round(100 * yes / (yes + no))}%" if yes + no else "-"


def summarize(results: list[dict]) -> dict:
    by_state: dict[str, dict] = {}
    criteria = {k: {"yes": 0, "no": 0, "n/a": 0, "error": 0} for k in CRITERIA}
    mech = {k: 0 for k in MECH_LABELS}
    for res in results:
        s = by_state.setdefault(res["state"], {"scenarios": 0, "replies": 0, "clean": 0, "yes": 0, "no": 0,
                                               "cause_ok": 0, "fallbacks": 0})
        s["scenarios"] += 1
        s["cause_ok"] += res["cause_ok"]
        for t in res["turns"]:
            s["replies"] += 1
            s["clean"] += not t["flags"]
            s["fallbacks"] += t["fallback"]
            for f in t["flags"]:
                mech[f] += 1
            for k, v in (t.get("rubric") or {}).items():
                if k not in CRITERIA:
                    continue
                verdict = v.get("verdict") if isinstance(v, dict) else "error"
                verdict = verdict if verdict in ("yes", "no", "n/a") else "error"
                criteria[k][verdict] += 1
                s["yes"] += verdict == "yes"
                s["no"] += verdict == "no"
    return {"by_state": by_state, "criteria": criteria, "mech": mech}


def write_report(path: Path, meta: dict, results: list[dict], summary: dict) -> None:
    out = [f"# Eval run: {meta['model']}", ""]
    out += [f"- When: {meta['started']}  ({meta['minutes']} min)",
            f"- Code: {meta['commit']}",
            *( [f"- **Unfinished (daily limit): {', '.join(meta['unfinished'])}**"] if meta.get("unfinished") else []),
            f"- Writer model: `{meta['model']}`; grader: `{meta['grader'] or 'none (rubric skipped)'}`",
            f"- Groq calls: pipeline {meta['usage']['pipeline']['calls']} "
            f"({meta['usage']['pipeline']['prompt']} prompt / {meta['usage']['pipeline']['completion']} completion "
            f"tokens), grader {meta['usage']['grader']['calls']}",
            "", "## Summary", "",
            "| State | Scenarios | Replies | Clean replies (no mechanical flag) | Rubric pass | Cause saved right "
            "| Fallbacks |",
            "|---|---|---|---|---|---|---|"]
    for state, s in summary["by_state"].items():
        out.append(f"| {state} | {s['scenarios']} | {s['replies']} | {_pct(s['clean'], s['replies'] - s['clean'])} "
                   f"| {_pct(s['yes'], s['no'])} | {s['cause_ok']}/{s['scenarios']} | {s['fallbacks']} |")
    out += ["", "| Rubric criterion | Pass | n/a | Errors |", "|---|---|---|---|"]
    for k, c in summary["criteria"].items():
        out.append(f"| {k} | {_pct(c['yes'], c['no'])} ({c['yes']}/{c['yes'] + c['no']}) | {c['n/a']} "
                   f"| {c['error']} |")
    out += ["", "| Mechanical flag | Replies |", "|---|---|"]
    out += [f"| {MECH_LABELS[k]} | {n} |" for k, n in summary["mech"].items()]

    out += ["", "## Scenarios", ""]
    for res in results:
        out += [f"### {res['id']}  ({res['state']}, chip: {res['chip']})", "", f"_{res['note']}_", "",
                f"Cause expected: `{res['expect_cause']}` · saved: `{res['saved_cause']}` · "
                f"{'OK' if res['cause_ok'] else 'MISMATCH'}", ""]
        for t in res["turns"]:
            if t["user"]:
                out.append(f"> **User:** {t['user']}")
                out.append(">")
            detail = ", ".join(x for x in (t.get("state"), t["phase"], t["intervention"],
                                           f"read: {t['read']}" if t.get("read") else None) if x)
            out.append(f"> **Buddy** ({detail}; {t['seconds']}s): {t['reply']}")
            notes = [MECH_LABELS[f] for f in t["flags"]]
            notes += [f"✗ {k}: {v.get('why', '')}" for k, v in (t.get("rubric") or {}).items()
                      if k in CRITERIA and isinstance(v, dict) and v.get("verdict") == "no"]
            if notes and (t.get("rubric") or {}).get("_expected"):
                notes.append(f"grader expected: {t['rubric']['_expected']}")
            if notes:
                out.append(">")
                out += [f"> - ⚠ {n}" for n in notes]
            out.append("")
        if res.get("dream"):
            out += ["<details><summary>Dream version (the developer's reference)</summary>", ""]
            for i, line in enumerate(res["dream"]):
                user = res["user_lines"][i - 1] if i >= 1 and i - 1 < len(res["user_lines"]) else None
                if user:
                    out.append(f"> **User:** {user}")
                    out.append(">")
                out.append(f"> **Buddy:** {line}")
                out.append("")
            out += ["</details>", ""]
    path.write_text("\n".join(out))


# ── main ─────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", help="writer model (sets GROQ_MODEL); default: current GROQ_MODEL or llm default")
    ap.add_argument("--grader", default=DEFAULT_GRADER)
    ap.add_argument("--no-rubric", action="store_true")
    ap.add_argument("--only", help="comma-separated scenario ids")
    ap.add_argument("--code", help="label for the code under test (default: git commit of this checkout)")
    ap.add_argument("--resume", help="results .json of a run to finish: reruns its unfinished scenarios")
    ap.add_argument("--regrade", help="results .json to re-score with the current grader (no Buddy calls)")
    args = ap.parse_args()

    if args.model:
        os.environ["GROQ_MODEL"] = args.model
    # Set before db.py is imported (below): a fresh DB per run, never the local buddy.db.
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='buddy-eval-')}/eval.db"
    os.environ["INVITE_CODE"] = "eval-invite"
    from fastapi.testclient import TestClient

    import models
    from brain import llm
    from db import SessionLocal
    from main import app

    from testing.evals.scenarios import SCENARIOS

    model = os.getenv("GROQ_MODEL", llm.DEFAULT_MODEL)
    needed = "ANTHROPIC_API_KEY" if model.startswith("claude-") else "GROQ_API_KEY"
    if not os.getenv(needed):
        sys.exit(f"{needed} is not set (it is read from buddy/.env).")
    usage = Usage()
    logging.getLogger("brain.llm").addHandler(usage)
    logging.getLogger("brain.llm").setLevel(logging.INFO)
    for noisy in ("httpx", "brain.llm"):
        logging.getLogger(noisy).propagate = False  # keep the console to progress lines
    llm.complete = make_patient(llm)

    shared, frameworks = load_frameworks()
    by_id = {s["id"]: s for s in SCENARIOS}
    if args.regrade:
        return regrade(Path(args.regrade), llm, usage, args.grader, shared, frameworks, by_id)

    chosen = [s for s in SCENARIOS if not args.only or s["id"] in args.only.split(",")]
    results, prior = [], None
    if args.resume:
        prior = json.loads(Path(args.resume).read_text())
        if prior["meta"]["model"] != model:
            sys.exit(f"--resume run used {prior['meta']['model']}; pass --model {prior['meta']['model']}")
        # keep finished scenarios; an older run without quota stops may hold quota fallbacks, so redo those
        results = [r for r in prior["results"] if not any(t["fallback"] for t in r["turns"])]
        kept = {r["id"] for r in results}
        chosen = [by_id[i] for i in prior["meta"]["scenarios"] if i not in kept and i in by_id]
        print(f"resuming: {len(results)} kept, {len(chosen)} to run", flush=True)
    if not chosen and not results:
        sys.exit("no scenarios match --only")
    started, t0 = datetime.now(), time.monotonic()
    unfinished = []
    with TestClient(app) as api:
        for n, sc in enumerate(chosen):
            if llm.complete.quota_hit:
                unfinished = [s["id"] for s in chosen[n:]]
                break
            print(f"{sc['id']}", flush=True)
            run = run_scenario(api, sc, models, SessionLocal)
            if llm.complete.quota_hit:
                unfinished = [s["id"] for s in chosen[n:]]
                print(f"\nGroq's daily limit hit during {sc['id']}: stopping. Finish later with --resume.", flush=True)
                break
            convo, earlier = [], []
            for i, t in enumerate(run["turns"]):
                if t["user"]:
                    convo.append(("User", t["user"]))
                is_release = sc["ends_with_release"] and i == len(run["turns"]) - 1
                t["flags"] = ["http_error"] if t["status"] != 200 else (
                    (["fallback"] if t["fallback"] else []) + mechanical(t["reply"], earlier, is_release))
                if not args.no_rubric and t["status"] == 200:
                    t["rubric"] = asyncio.run(grade(llm, usage, args.grader, shared,
                                                    frameworks.get(sc["state"], ""), task_line(sc["task"]),
                                                    convo, t["reply"]))
                convo.append(("Buddy", t["reply"]))
                earlier.append(t["reply"])
            results.append({**{k: sc.get(k) for k in ("id", "state", "chip", "note", "expect_cause", "dream")},
                            "user_lines": sc["user"], "saved_cause": run["saved_cause"],
                            "cause_ok": run["saved_cause"] == sc["expect_cause"], "turns": run["turns"]})

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], capture_output=True, text=True).stdout.strip()
    meta = {"model": model, "grader": None if args.no_rubric else args.grader,
            "started": started.strftime("%Y-%m-%d %H:%M"), "minutes": round((time.monotonic() - t0) / 60, 1),
            "commit": args.code or (prior and prior["meta"]["commit"]) or (
                commit + (" + uncommitted changes" if dirty else "")),
            "usage": usage.totals, "unfinished": unfinished,
            "scenarios": prior["meta"]["scenarios"] if prior else [s["id"] for s in chosen]}
    summary = summarize(results)

    results_dir = HERE.parent / "results"
    results_dir.mkdir(exist_ok=True)
    stem = f"{started:%Y-%m-%d_%H%M}_{model.replace('/', '-')}"
    (results_dir / f"{stem}.json").write_text(json.dumps(
        {"meta": meta, "summary": summary, "results": results}, indent=2))
    write_report(results_dir / f"{stem}.md", meta, results, summary)
    print(f"\nReport: {results_dir / (stem + '.md')}")
    if unfinished:
        print(f"Unfinished ({len(unfinished)}): {', '.join(unfinished)}. "
              f"Resume: backend/venv/bin/python -m testing.evals.run --model {model}{' --no-rubric' if args.no_rubric else ''} --resume {results_dir / (stem + '.json')}")


def regrade(path: Path, llm, usage, grader, shared, frameworks, by_id) -> None:
    """Re-score every reply of a finished run with the current grader, so runs are compared on equal terms."""
    data = json.loads(path.read_text())
    for res in data["results"]:
        sc = by_id[res["id"]]
        convo = []
        print(res["id"], flush=True)
        for t in res["turns"]:
            if t["user"]:
                convo.append(("User", t["user"]))
            if t["status"] == 200:
                t["rubric"] = asyncio.run(grade(llm, usage, grader, shared, frameworks.get(sc["state"], ""),
                                                task_line(sc["task"]), convo, t["reply"]))
            convo.append(("Buddy", t["reply"]))
    data["meta"]["grader"] = f"{grader} (regraded {datetime.now():%Y-%m-%d %H:%M})"
    data["summary"] = summarize(data["results"])
    out = path.with_name(path.stem + "_regraded")
    out.with_suffix(".json").write_text(json.dumps(data, indent=2))
    write_report(out.with_suffix(".md"), data["meta"], data["results"], data["summary"])
    print(f"\nReport: {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
