"""DEBT-044: repeating reminders asked for in chat ("هر روز ساعت ۸ صبح یادم بنداز آب بخورم").

Parser -> UserEvent.recurrence_rule -> scheduler fires every occurrence once, via the same I10 chain.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.intelligence.reminder_event_dispatch import (
    confirmation_message,
    dispatch_reminder_user_event,
)
from backend.app.services.intelligence.reminder_event_readiness import (
    describe_when,
    parse_reminder_event_draft,
)
from backend.app.services.section10.event_reminder_scheduler import (
    process_event_reminders,
    recurring_occurrences_utc,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

# 2026-10-27 06:00 UTC = 09:30 Tehran (Tuesday).
NOW = datetime(2026, 10, 27, 6, 0)
TZ = "Asia/Tehran"


def _parse(message: str, language: str | None = None):
    return parse_reminder_event_draft(message=message, timezone_name=TZ, now_utc=NOW, language=language)


@pytest.mark.parametrize(
    "message, first, rule, title",
    [
        ("هر روز ساعت ۸ صبح یادم بنداز آب بخورم", "2026-10-28 08:00", "FREQ=DAILY", "آب بخورم"),
        ("هر روز ساعت ۱۱ صبح یادم بنداز قرص ویتامین", "2026-10-27 11:00", "FREQ=DAILY", "قرص ویتامین"),
        ("هر دوشنبه ساعت ۱۰ صبح یادم بنداز جلسه", "2026-11-02 10:00", "FREQ=WEEKLY;BYDAY=MO", "جلسه"),
        ("هر سه‌شنبه ساعت ۱۶ یادم بنداز ورزش", "2026-10-27 16:00", "FREQ=WEEKLY;BYDAY=TU", "ورزش"),
        ("هر هفته ساعت ۷ عصر یادآوری کن ورزش", "2026-10-27 19:00", "FREQ=WEEKLY;BYDAY=TU", "ورزش"),
        ("every day at 9pm remind me to stretch", "2026-10-27 21:00", "FREQ=DAILY", "stretch"),
        ("remind me every monday at 8am to weigh myself", "2026-11-02 08:00", "FREQ=WEEKLY;BYDAY=MO", "weigh myself"),
    ],
)
def test_parser_builds_repeat_rule(message, first, rule, title):
    draft, missing = _parse(message)
    assert missing is None and draft is not None, (message, missing)
    assert draft.recurrence_rule == rule
    assert draft.starts_at_local.strftime("%Y-%m-%d %H:%M") == first
    assert draft.title == title
    assert draft.reminder_offsets == (0,) and not draft.relative


def test_habit_statements_and_unsupported_patterns_stay_refused():
    assert _parse("هر شب ساعت ۱۱ می‌خوابم")[1] == "recurrence"  # a habit, not a reminder request
    assert _parse("هر ۲ ساعت یادم بنداز آب بخورم")[1] == "recurrence"
    assert _parse("remind me every 3 hours to drink")[1] == "recurrence"
    assert _parse("هر روز یادم بنداز آب بخورم")[1] == "datetime"  # a repeat needs a time of day


def test_one_off_reminders_are_unchanged():
    d, miss = _parse("فردا ساعت ۱۰ صبح یادم بنداز دارو")
    assert miss is None and d.recurrence_rule is None


def test_confirmation_states_the_repeat():
    d, _ = _parse("هر دوشنبه ساعت ۱۰ صبح یادم بنداز جلسه")
    assert describe_when(d, "fa", NOW) == "هر هفته دوشنبه ساعت ۱۰:۰۰"
    d, _ = _parse("هر روز ساعت ۸ صبح یادم بنداز آب بخورم")
    msg = confirmation_message({"when": describe_when(d, "fa", NOW), "title": d.title, "offset_min": 0}, "fa")
    assert "هر روز ساعت ۰۸:۰۰" in msg and "آب بخورم" in msg
    assert describe_when(d, "en", NOW) == "every day at 08:00"


# ---------------------------------------------------------------- occurrence math (no DB)
class _Ev:
    def __init__(self, rule, starts_at, tz="Asia/Tehran"):
        self.recurrence_rule, self.starts_at, self.timezone = rule, starts_at, tz


def test_daily_occurrences_keep_wall_clock_and_skip_days_before_the_first():
    ev = _Ev("FREQ=DAILY", datetime(2026, 10, 28, 8, 0))
    occ = recurring_occurrences_utc(ev, NOW)  # NOW is Tue 27th: the 27th is before the first occurrence
    days = [tag for _, tag in occ]
    assert days[0] == "20261028" and days[-1] == "20261104"  # window: yesterday .. +8 days
    assert all(start.hour == 4 and start.minute == 30 for start, _ in occ)  # 08:00 Tehran (+03:30)


def test_weekly_occurrences_only_on_the_chosen_weekday_and_bad_rule_is_ignored():
    ev = _Ev("FREQ=WEEKLY;BYDAY=MO", datetime(2026, 10, 19, 10, 0))
    assert [tag for _, tag in recurring_occurrences_utc(ev, NOW)] == ["20261026", "20261102"]  # yesterday's Monday is still in the late-send window
    assert recurring_occurrences_utc(_Ev("FREQ=YEARLY", datetime(2026, 10, 19, 10, 0)), NOW) == []
    assert recurring_occurrences_utc(_Ev("garbage", datetime(2026, 10, 19, 10, 0)), NOW) == []


# ---------------------------------------------------------------- scheduler (DB)
_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch(
    "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
    return_value=True,
)


@pytest.fixture
def chain_patch():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db) -> models.User:
    row = models.User(name="debt044-user", secret_key="sk-debt044", preferred_language="fa")
    db.add(row)
    db.commit()
    db.refresh(row)
    ensure_self_subject_for_account(db, row.id, commit=True)
    return row


def test_chat_repeat_fires_each_day_once(chain_patch, db):
    # Dates are derived from the real clock: the I10 candidate expiry (occurrence + 30 min) is checked against "now".
    from backend.app.services.i10.event_reminder_i10_adapter import event_starts_utc

    user = _user(db)
    result = dispatch_reminder_user_event(
        db,
        user_id=user.id,
        message="هر روز ساعت ۸ صبح یادم بنداز آب بخورم",
        timezone_name=TZ,
        now_utc=datetime.now(timezone.utc),
        language="fa",
    )
    assert result["created"] is True and "هر روز" in result["when"]
    event = db.query(models.UserEvent).filter(models.UserEvent.user_id == user.id).one()
    assert event.recurrence_rule == "FREQ=DAILY" and json.loads(event.reminder_offsets_json) == [0]

    day1 = event_starts_utc(event) + timedelta(minutes=1)  # one minute after the first occurrence (08:00 Tehran)
    assert process_event_reminders(db, now=day1 - timedelta(minutes=30)) == 0
    assert process_event_reminders(db, now=day1) == 1
    assert process_event_reminders(db, now=day1 + timedelta(minutes=5)) == 0  # same occurrence, no duplicate
    # The next day fires again, with its own dedupe key.
    assert process_event_reminders(db, now=day1 + timedelta(days=1)) == 1
    assert process_event_reminders(db, now=day1 + timedelta(days=2)) == 1
    bodies = [n.body for n in db.query(models.Notification).filter(models.Notification.user_id == user.id)]
    assert len(bodies) == 3 and all("آب بخورم" in b for b in bodies)
