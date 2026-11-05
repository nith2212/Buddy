# Read-call eval (docs/PIVOTS.md build plan, step 4): how often brain.flow.read_message reads a
# user message the way it should, per model. Two scores per case:
#   kind   - the exact label (idk / answer / confirm / ...)
#   route  - whether the reading sends the conversation to the same next stage as the label would
#            (what matters for the user: "own_plan" vs "confirm" after Buddy's offer both release)
#
# From the repo root (buddy/), see testing/README.md:
#   backend/venv/bin/python -m testing.evals.read_eval --model openai/gpt-oss-20b
#   backend/venv/bin/python -m testing.evals.read_eval --rescore testing/results/<run>_read_<model>.json
# Not part of pytest: it spends real Groq quota.

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def stage_for(state: str, buddy: str, read_cases) -> str:
    """Which stage Buddy was on when it said `buddy` (decides where each reading leads)."""
    from brain import flow
    rc = read_cases
    by_line = {rc.ASK_CORE: "core", rc.ASK_STEP: "first_step", rc.GUESS_FEAR: "narrow", rc.GUESS_SKILL: "narrow",
               rc.OFFER_TINY: "micro", rc.ASK_BORING: "narrow", rc.ASK_PURPOSE: "purpose",
               rc.OFFER_LIGHTEN: "lighten", rc.RELEASE: "release", rc.OFFER_CHOICE: "offer"}
    if buddy.startswith("Want to try a deliberately rough version"):
        return "reframe"
    if buddy.startswith("Rest up"):
        return "rest"
    stage = by_line.get(buddy, "open")
    fw = flow.FRAMEWORKS[state]
    known = {fw.first, fw.tiny, *fw.on.values(), *(s for s, _ in fw.on), *fw.by_flavor.values(), *flow.GENERIC}
    return stage if stage in known else fw.first


async def run(model: str) -> dict:
    from brain import flow, llm
    from testing.evals import read_cases
    from testing.evals.run import make_patient

    llm.complete = make_patient(llm)
    rows = []
    for state, buddy, user, kind, cause in read_cases.READ_CASES:
        stage = stage_for(state, buddy, read_cases)
        got = await flow.read_message(state, stage, buddy, user)
        want = flow.Reading(kind, cause)
        route_got = flow.next_stage(state, stage, got, 1).stage
        route_want = flow.next_stage(state, stage, want, 1).stage
        rows.append({"state": state, "buddy": buddy, "user": user, "want": kind, "want_cause": cause,
                     "stage": stage, "got": got.kind, "got_cause": got.cause, "got_flavor": got.flavor,
                     "source": got.source,
                     "kind_ok": got.kind == kind and (cause is None or got.cause == cause),
                     "route_ok": route_got == route_want})
        print(f"  {'ok ' if rows[-1]['kind_ok'] else 'MISS'} {kind:>10} <- {got.kind:<10} {user[:50]}", flush=True)
        if llm.complete.quota_hit:
            # a refused call reads as "unclear": scoring it would blame the model for the quota
            sys.exit("Groq's daily limit hit: nothing saved. Run again once it resets.")
    return {"model": model, "rows": rows}


def report(result: dict, path: Path) -> None:
    rows = result["rows"]
    n = len(rows)
    kind_ok = sum(r["kind_ok"] for r in rows)
    route_ok = sum(r["route_ok"] for r in rows)
    by_kind: dict[str, Counter] = {}
    for r in rows:
        by_kind.setdefault(r["want"], Counter())[r["got"]] += 1
    out = [f"# Read-call eval: {result['model']}", "", f"- When: {datetime.now():%Y-%m-%d %H:%M}",
           f"- Exact kind: **{kind_ok}/{n} ({round(100 * kind_ok / n)}%)**",
           f"- Same next stage (what the user feels): **{route_ok}/{n} ({round(100 * route_ok / n)}%)**",
           f"- Caught by patterns, no model call: {sum(r['source'] == 'pattern' for r in rows)}",
           "", "| Should be | n | Right | Read instead as |", "|---|---|---|---|"]
    for kind, c in by_kind.items():
        total, right = sum(c.values()), c[kind]
        wrong = ", ".join(f"{k} ×{v}" for k, v in c.items() if k != kind) or "-"
        out.append(f"| {kind} | {total} | {right} | {wrong} |")
    out += ["", "## Misses", "", "| Stage | Buddy said | User said | Should be | Read as | Same route? |",
            "|---|---|---|---|---|---|"]
    for r in rows:
        if not r["kind_ok"]:
            want = r["want"] + (f" ({r['want_cause']})" if r["want_cause"] else "")
            got = r["got"] + (f" ({r['got_cause']})" if r["got_cause"] else "")
            out.append(f"| {r.get('stage', '')} | {r['buddy']} | {r['user']} | {want} | {got} | "
                       f"{'yes' if r['route_ok'] else '**no**'} |")
    path.write_text("\n".join(out))


def rescore(path: Path) -> None:
    """Re-score a saved run with the current stage table (no Groq calls)."""
    from brain import flow
    from testing.evals import read_cases
    result = json.loads(path.read_text())
    # match by the case itself, not its position: cases get added over time
    cases = {(c[0], c[1], c[2]): c for c in read_cases.READ_CASES}
    result["rows"] = [r for r in result["rows"] if (r["state"], r["buddy"], r["user"]) in cases]
    for r in result["rows"]:
        state, buddy, user, kind, cause = cases[(r["state"], r["buddy"], r["user"])]
        stage = stage_for(state, buddy, read_cases)
        got = flow.Reading(r["got"] if r["got"] in flow.KINDS else "unclear", r["got_cause"], r.get("got_flavor"))
        want = flow.Reading(kind, cause, got.flavor)  # the saved run may not have kept flavors: don't count them
        r.update(stage=stage, route_ok=flow.next_stage(state, stage, got, 1).stage
                 == flow.next_stage(state, stage, want, 1).stage)
    out = path.with_name(path.stem + "_rescored.md")
    report(result, out)
    print(f"Report: {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="model for the read call (sets GROQ_MODEL)")
    ap.add_argument("--rescore", help="saved read-eval .json to re-score offline")
    args = ap.parse_args()
    if args.rescore:
        return rescore(Path(args.rescore))
    if args.model:
        os.environ["GROQ_MODEL"] = args.model
    from dotenv import load_dotenv

    from brain import llm

    load_dotenv(HERE.parent.parent / ".env")  # buddy/.env, where the API keys live
    model = os.getenv("GROQ_MODEL", llm.DEFAULT_MODEL)
    needed = "ANTHROPIC_API_KEY" if model.startswith("claude-") else "GROQ_API_KEY"
    if not os.getenv(needed):
        sys.exit(f"{needed} is not set (it is read from buddy/.env).")
    result = asyncio.run(run(model))
    out_dir = HERE.parent / "results"
    out_dir.mkdir(exist_ok=True)
    stem = f"{datetime.now():%Y-%m-%d_%H%M}_read_{model.replace('/', '-')}"
    (out_dir / f"{stem}.json").write_text(json.dumps(result, indent=2))
    report(result, out_dir / f"{stem}.md")
    print(f"\nReport: {out_dir / (stem + '.md')}")


if __name__ == "__main__":
    main()
