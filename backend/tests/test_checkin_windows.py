# Check-ins go out only inside the hours the person's onboarding answer picked (India time).
from datetime import datetime, timedelta, timezone

import pytest

import models
from cron import CHECKIN_HOURS, DEFAULT_HOURS, _eligible_tasks, in_checkin_window

IST = timezone(timedelta(hours=5, minutes=30))


def at(hour, minute=0):
    """A fixed UTC instant that is `hour`:`minute` in India."""
    return datetime(2026, 11, 9, hour, minute, tzinfo=IST).astimezone(timezone.utc)


@pytest.mark.parametrize("click_time,yes,no", [
    ("morning", [7, 11], [6, 12]),
    ("afternoon", [12, 16], [11, 17]),
    ("evening", [17, 21], [16, 22]),
    ("late_night", [21, 23], [20, 0, 2]),   # no 3 am nudges, even for night owls
    ("changes", [9, 21], [8, 22]),
    (None, [9, 21], [8, 22, 3]),
])
def test_each_answer_has_its_hours(click_time, yes, no):
    assert all(in_checkin_window(click_time, at(h)) for h in yes)
    assert not any(in_checkin_window(click_time, at(h)) for h in no)


def test_an_unknown_answer_gets_the_default_hours():
    assert CHECKIN_HOURS.get("brunch") is None
    assert in_checkin_window("brunch", at(10)) and not in_checkin_window("brunch", at(23))
    assert list(DEFAULT_HOURS) == list(range(9, 22))   # the same 09:00-21:00 as the old cron


def _person(db, click_time=None, onboarding=True):
    user = models.User(token_hash=f"h-{click_time}-{onboarding}")
    db.add(user)
    db.flush()
    if onboarding:
        db.add(models.Onboarding(user_id=user.id, click_time=click_time))
    task = models.Task(user_id=user.id, title="t", due_date=datetime(2020, 1, 1, tzinfo=timezone.utc))
    db.add(task)
    db.commit()
    return user.id


def test_the_hourly_run_only_nudges_people_inside_their_hours(db):
    morning, evening, night = _person(db, "morning"), _person(db, "evening"), _person(db, "late_night")
    unsure, never_onboarded = _person(db, None), _person(db, onboarding=False)

    def nudged(hour):
        return {t.user_id for t in _eligible_tasks(db, at(hour))}

    assert nudged(8) == {morning}
    assert nudged(10) == {morning, unsure, never_onboarded}
    assert nudged(18) == {evening, unsure, never_onboarded}
    assert nudged(21) == {evening, night, unsure, never_onboarded}
    assert nudged(23) == {night}
    assert nudged(3) == set()
