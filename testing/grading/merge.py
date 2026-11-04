# Apply hand-written grades (testing/grading/grades/*.json) to eval runs and write graded reports.
# See testing/GRADING.md for the grades file format.
#
# From the repo root (buddy/):
#   backend/venv/bin/python -m testing.grading.merge testing/grading/grades/<file>.json [more.json ...]
#   backend/venv/bin/python -m testing.grading.merge --all      # every grades file
#
# For each run named in the grades files, writes testing/results/<run>_graded.json and .md, holding
# ONLY the graded conversations (so partial grading never mixes with another grader's scores).
# Several grades files for the same run are combined.

from __future__ import annotations

import argparse
import json
from pathlib import Path

from testing.evals.run import CRITERIA, summarize, write_report

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
VERDICT = {"y": "yes", "n": "no", "-": "n/a"}


class GradesError(ValueError):
    pass


def load(paths: list[Path]) -> tuple[dict[str, dict], set[str]]:
    """{run file name: {scenario id: [[codes, why], ...]}}, and who graded."""
    merged: dict[str, dict] = {}
    graders = set()
    for path in paths:
        data = json.loads(path.read_text())
        if data.get("order") != list(CRITERIA):
            raise GradesError(f"{path.name}: 'order' must be exactly {list(CRITERIA)}")
        graders.add(str(data.get("grader") or "unknown"))
        for run, scenarios in data["files"].items():
            merged.setdefault(run, {}).update(scenarios)
    return merged, graders


def check(run: str, result: dict, grades: list) -> None:
    where = f"{run} / {result['id']}"
    if len(grades) != len(result["turns"]):
        raise GradesError(f"{where}: {len(grades)} grades for {len(result['turns'])} replies")
    for i, (codes, why) in enumerate(grades):
        if len(codes) != len(CRITERIA) or set(codes) - set(VERDICT):
            raise GradesError(f"{where} B[{i}]: '{codes}' must be {len(CRITERIA)} letters, each y, n or -")
        if "n" in codes and not why.strip():
            raise GradesError(f"{where} B[{i}]: a 'n' needs a why")


def apply(run: str, scenarios: dict, graders: set[str]) -> dict:
    data = json.loads((RESULTS / run).read_text())
    keep = []
    for result in data["results"]:
        if result["id"] not in scenarios:
            continue
        grades = scenarios[result["id"]]
        check(run, result, grades)
        for turn, (codes, why) in zip(result["turns"], grades):
            turn["rubric"] = {k: {"verdict": VERDICT[c], "why": why if c == "n" else ""}
                              for k, c in zip(CRITERIA, codes)}
        keep.append(result)
    missing = set(scenarios) - {r["id"] for r in keep}
    if missing:
        raise GradesError(f"{run}: no such conversations {sorted(missing)}")
    data["results"] = keep
    data["meta"]["grader"] = " + ".join(sorted(graders)) + " (by hand, testing/GRADING.md)"
    data["summary"] = summarize(keep)
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("grades", nargs="*", help="grades .json files")
    ap.add_argument("--all", action="store_true", help="use every file in testing/grading/grades/")
    args = ap.parse_args()
    paths = sorted((HERE / "grades").glob("*.json")) if args.all else [Path(g) for g in args.grades]
    paths = [p for p in paths if not p.name.endswith(".todo.json")]
    if not paths:
        raise SystemExit("no grades files given")
    merged, graders = load(paths)
    for run, scenarios in merged.items():
        data = apply(run, scenarios, graders)
        out = RESULTS / (Path(run).stem + "_graded")
        out.with_suffix(".json").write_text(json.dumps(data, indent=2))
        write_report(out.with_suffix(".md"), data["meta"], data["results"], data["summary"])
        crit = data["summary"]["criteria"]
        print(f"{out.name}.md  " + "  ".join(f"{k} {v['yes']}/{v['yes'] + v['no']}" for k, v in crit.items()))


if __name__ == "__main__":
    main()
