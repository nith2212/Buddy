# Echo's local text report (dev only): what Echo would save for each user, and the one line Buddy
# would get for each task. Read-only: it never writes to the database.
#
# From the repo root (buddy/):
#   backend/venv/bin/python -m testing.echo_report                 # local DB, this week so far
#   backend/venv/bin/python -m testing.echo_report --last-week     # the last finished week (what the cron saves)
#   backend/venv/bin/python -m testing.echo_report --demo          # a made-up week on a throwaway DB
#   backend/venv/bin/python -m testing.echo_report --db <url>      # another database (careful: real data)
#
# Writes testing/echo_reports/<date>_<time>.txt (gitignored: it holds task titles).

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import testing  # noqa: F401  (puts backend/ on the import path)

HERE = Path(__file__).resolve().parent
LOCAL_DB = HERE.parent / "backend" / "buddy.db"


def seed_demo(db) -> None:
    import models
    from brain import echo

    _, end = echo.week_window(datetime.now(timezone.utc))
    start = end - timedelta(days=7)
    user = models.User(id="demo-user", token_hash="demo")
    db.add(user)
    db.flush()
    report = models.Task(user_id=user.id, title="Prepare client report", created_at=start - timedelta(days=9),
                         updated_at=start - timedelta(days=9))
    app = models.Task(user_id=user.id, title="Finish Nixly app", created_at=start - timedelta(days=4),
                      updated_at=start + timedelta(days=5))
    db.add_all([report, app])
    db.flush()
    for day in (1, 3, 5):
        db.add(models.Event(user_id=user.id, task_id=report.id, type="checkin_sent", created_at=start + timedelta(days=day)))
    db.add(models.EmotionLog(user_id=user.id, task_id=app.id, emotion="afraid", created_at=start + timedelta(days=5)))
    db.add(models.Memory(user_id=user.id, key=f"blocker.task.{app.id}", value="afraid", updated_at=start + timedelta(days=5)))
    db.add(models.Memory(user_id=user.id, key="pattern.blocker.afraid", value="3"))
    db.add(models.Event(user_id=user.id, task_id=report.id, type="postponed", created_at=start + timedelta(days=2)))
    # E2: a chat on the app task: asked for a rough version, they took it and ticked a step that evening
    at = start + timedelta(days=5, minutes=5)
    for i, (stage, read) in enumerate([("open", None), ("reframe", "confirm"), ("release", "accept")]):
        flow = {"state": "perfectionism", "stage": stage, "read": read and {"kind": read}}
        db.add(models.Message(user_id=user.id, task_id=app.id, role="assistant", content="(reply)",
                              reasoning=json.dumps({"flow": flow}), created_at=at + timedelta(minutes=i)))
    db.add(models.Subtask(user_id=user.id, task_id=app.id, title="rough draft of the swipe screen", done=True,
                          created_at=at, updated_at=at + timedelta(hours=4)))
    db.commit()


def report(db, last_week: bool) -> str:
    from sqlalchemy import select

    import models
    from brain import echo

    now = datetime.now(timezone.utc)
    start, end = echo.week_window(now)
    if not last_week:
        start, end = end, now  # this week so far
    out = [f"Echo report ({'last finished week' if last_week else 'this week so far'}): "
           f"{start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC", ""]
    users = db.execute(select(models.User.id)).scalars().all()
    for uid in users:
        facts = echo.week_facts(db, uid, start, end)
        out.append(f"=== user {uid}")
        if facts is None:
            out += ["no tasks: no Echo", ""]
            continue
        titles = {t.id: t.title for t in db.execute(select(models.Task).where(models.Task.user_id == uid)).scalars()}
        out.append(f"causes confirmed: {facts['causes_confirmed'] or 'none'}"
                   f"{'  (first week: counted from per-task causes)' if facts['first_week'] else ''}")
        out.append(f"cause totals so far: {facts['cause_totals'] or 'none'}")
        out.append(f"reasons tapped: {facts['reasons_tapped'] or 'none'}")
        out.append(f"finished: {facts['tasks_finished']} task(s), {facts['steps_done']} step(s)")
        out.append(f"days active: {len(facts.get('days_active', []))} {facts.get('days_active', [])}")
        c = facts.get("checkins", {})
        out.append(f"check-ins: {c.get('sent', 0)} sent, {c.get('ignored', 0)} ignored, "
                   f"chat yes {c.get('chat_yes', 0)} / no {c.get('chat_no', 0)}")
        out.append("reactions to Buddy's moves:" if facts.get("reactions") else "reactions to Buddy's moves: none")
        for move, row in sorted(facts.get("reactions", {}).items()):
            parts = ", ".join(f"{k} {v}" for k, v in row.items() if v and k not in ("offered", "progress_after"))
            out.append(f"  - {move}: offered {row['offered']} ({parts}); progress within a day {row['progress_after']}")
        for t in facts["open_tasks"]:
            out.append(f"- \"{titles.get(t['id'])}\": untouched {t['days_untouched']} day(s), check-ins "
                       f"{t['checkins_ignored']}/{t['checkins_sent']} ignored, postponed {t['postponed']}x")
            line = echo.buddy_line(facts, t["id"])
            out.append(f"    Buddy's line: {line or '(none)'}")
        out += ["", "raw (what's saved):", json.dumps(facts, indent=1), ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="database URL (default: the local backend/buddy.db)")
    ap.add_argument("--last-week", action="store_true", help="the last finished week instead of this week so far")
    ap.add_argument("--demo", action="store_true", help="a made-up week on a throwaway database")
    args = ap.parse_args()
    if args.demo:
        os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/echo_demo.db"
    else:
        os.environ["DATABASE_URL"] = args.db or f"sqlite:///{LOCAL_DB}"
    from db import Base, SessionLocal, engine  # reads DATABASE_URL on import

    if args.demo:
        import models  # noqa: F401  (registers the tables)
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if args.demo:
            seed_demo(db)
        text = report(db, args.last_week or args.demo)
    finally:
        db.close()
    out_dir = HERE / "echo_reports"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{datetime.now():%Y-%m-%d_%H%M}{'_demo' if args.demo else ''}.txt"
    path.write_text(text)
    print(text)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
