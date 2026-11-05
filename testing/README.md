# Buddy testing kit

Evals that run Buddy's real pipeline against the real model, plus the tools to grade them by hand.
The unit tests are separate (`backend/tests/`, run with `cd backend && venv/bin/python -m pytest -q`):
they use a fake model and must stay green. The evals here spend real Groq quota, so they're never part
of pytest.

```
testing/
  README.md          this file: what's here and how to run it
  GRADING.md         the grading rules: how to score each reply by hand
  evals/
    run.py           conversation eval: scripted chats through the real app, mechanical checks, report
    scenarios.py     the scripted conversations (3 per chip), with the developer's dream lines
    read_eval.py     read-call eval: does Buddy read each user message right? (idk / answer / own_plan ...)
    read_cases.py    the labeled messages for the read eval
  grading/
    export.py        makes a grading packet (frameworks + transcripts) and a blank grades file
    merge.py         applies grades files to runs and writes the graded reports
    grades/          hand-written grades (one .json per batch)
    packets/         generated packets (safe to delete, export remakes them)
  results/           every run: <date>_<time>_<model>.json/.md, plus _graded and _rescored copies
  echo_report.py     Echo's weekly facts as a text report (dev only, read-only)
  echo_reports/      its output (gitignored: holds task titles)
```

## Setup

- Run everything from the repo root (`buddy/`) with the backend's Python: `backend/venv/bin/python -m ...`.
- The Groq key comes from `buddy/.env` (`GROQ_API_KEY=...`).
- Each run uses a throwaway SQLite database. Your real data and Neon are never touched.

## Conversation eval

```
backend/venv/bin/python -m testing.evals.run --model openai/gpt-oss-20b --no-rubric          # all 15 chats
backend/venv/bin/python -m testing.evals.run --model qwen/qwen3.8-27b --no-rubric --only ambiguity_main,fatigue_main
backend/venv/bin/python -m testing.evals.run --model <model> --no-rubric --resume testing/results/<run>.json
```

- `--no-rubric`: skip Groq's grader. Use it: grading is done by hand now (GRADING.md).
- `--resume`: finish a run the daily limit cut short. It reruns only the unfinished chats, and needs the same `--model`.
- `--only`: run some scenario ids (see `evals/scenarios.py`).
- `--code "<label>"`: name the code under test in the report (default: the git commit, plus "uncommitted" if dirty).
- `--regrade <run>.json` / `--grader <model>`: re-score with Groq's grader (old way; spends quota on the grader model).

Every reply also gets mechanical checks, which need no grader: repeats, a repeated opener, a canned
fallback, a question in a wrap-up, and so on. They're in the report's "Clean replies" column.

Then grade it: see GRADING.md (export, then grade, then merge).

## Read eval

```
backend/venv/bin/python -m testing.evals.read_eval --model openai/gpt-oss-120b
backend/venv/bin/python -m testing.evals.read_eval --rescore testing/results/<run>_read_<model>.json   # offline
```

Two scores per message: the exact label, and "same route" (the reading sends the chat to the same next
stage). Route is the one that matters to the user. `--rescore` re-scores a saved run against the current
stage table, with no Groq calls.

## Echo report

```
backend/venv/bin/python -m testing.echo_report --demo         # a made-up week on a throwaway DB
backend/venv/bin/python -m testing.echo_report                # local backend/buddy.db, this week so far
backend/venv/bin/python -m testing.echo_report --last-week    # the last finished week (what the cron saves)
```

It shows what Echo counts per user and the one line Buddy would get per task. It never writes to the DB.

## Groq free-tier limits

- Each model has its own daily caps: about 1,000 requests and a hidden token cap. Some refills during
  the day, all of it in about 24 hours.
- When a cap hits, the run stops cleanly and prints its `--resume` command. Nothing half-done is scored.
- The phone app on Render uses the same account. Running evals on the production model (gpt-oss-20b)
  eats the allowance your phone needs, so don't eval and phone-test on the same afternoon.
- Never make extra accounts to get around the caps (against Groq's terms, and it risks the account Buddy
  runs on). If quota is the blocker, use Groq's paid tier.

## Results so far (hand-graded, "follows the framework")

| Run | What | Score |
|---|---|---|
| `2026-11-04_1244_openai-gpt-oss-20b_graded.md` | old Buddy (the one on the phone), all 5 chips | 17/69 (25%) |
| `2026-11-04_1549_openai-gpt-oss-20b_graded.md` | new Buddy, don't know where to start | 13/15 (87%) |
| `2026-11-04_1312_openai-gpt-oss-20b_graded.md` | new Buddy, scared + too tired (slightly older code) | 16/20 (80%) |

The plan and its status live in `PIVOTS.md` (repo root).
