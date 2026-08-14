"""I5 calendar lock: Friday 03:30 Asia/Tehran = Friday 00:00 UTC. Restart-invariant."""

from __future__ import annotations

import inspect
from datetime import datetime

import pytz

from backend.app.services.i5.governed_weekly_runtime import (
    WEEKLY_CRON_DAY_OF_WEEK,
    WEEKLY_CRON_HOUR,
    WEEKLY_CRON_MINUTE,
    WEEKLY_SCHEDULER_TIMEZONE_NAME,
    next_weekly_calendar_fire,
    weekly_calendar_trigger_kwargs,
    weekly_scheduler_tz,
)


def test_cron_kwargs_friday_0330_tehran_singleton_coalesce():
    kw = weekly_calendar_trigger_kwargs()
    assert kw["trigger"] == "cron"
    assert kw["day_of_week"] == "fri" == WEEKLY_CRON_DAY_OF_WEEK
    assert kw["hour"] == 3 == WEEKLY_CRON_HOUR
    assert kw["minute"] == 30 == WEEKLY_CRON_MINUTE
    assert kw["timezone"] == "Asia/Tehran" == WEEKLY_SCHEDULER_TIMEZONE_NAME
    assert kw["max_instances"] == 1
    assert kw["coalesce"] is True


def test_timezone_is_asia_tehran():
    tz = weekly_scheduler_tz()
    assert str(tz) == "Asia/Tehran"


def test_next_fire_from_thursday_is_friday_0330():
    tz = weekly_scheduler_tz()
    now = tz.localize(datetime(2026, 8, 13, 10, 0, 0))  # Thursday
    nxt = next_weekly_calendar_fire(now=now)
    assert nxt.tzinfo.zone == "Asia/Tehran"
    assert nxt.weekday() == 4
    assert nxt.hour == 3 and nxt.minute == 30 and nxt.second == 0
    assert nxt.date().isoformat() == "2026-08-14"
    utc = nxt.astimezone(pytz.UTC)
    assert utc.weekday() == 4
    assert utc.hour == 0 and utc.minute == 0


def test_next_fire_friday_before_slot_is_same_day():
    tz = weekly_scheduler_tz()
    now = tz.localize(datetime(2026, 8, 14, 3, 29, 0))
    nxt = next_weekly_calendar_fire(now=now)
    assert nxt.date().isoformat() == "2026-08-14"
    assert nxt.hour == 3 and nxt.minute == 30


def test_next_fire_friday_at_or_after_slot_rolls_seven_days():
    tz = weekly_scheduler_tz()
    now = tz.localize(datetime(2026, 8, 14, 3, 30, 0))
    nxt = next_weekly_calendar_fire(now=now)
    assert nxt.date().isoformat() == "2026-08-21"
    later = tz.localize(datetime(2026, 8, 14, 3, 31, 0))
    assert next_weekly_calendar_fire(now=later).date().isoformat() == "2026-08-21"


def test_restart_does_not_shift_weekday_or_time(monkeypatch):
    tz = weekly_scheduler_tz()
    now = tz.localize(datetime(2026, 8, 13, 18, 45, 0))
    first = next_weekly_calendar_fire(now=now)
    monkeypatch.setenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "120")
    monkeypatch.setenv("SEDI_I5_WEEKLY_ORCHESTRATOR_INTERVAL_MIN", "60")
    second = next_weekly_calendar_fire(now=now)
    third = next_weekly_calendar_fire(now=now)
    assert first == second == third
    assert first.weekday() == 4
    assert first.hour == 3 and first.minute == 30


def test_winter_and_summer_utc_equivalent_no_iran_dst():
    tz = weekly_scheduler_tz()
    winter = next_weekly_calendar_fire(now=tz.localize(datetime(2026, 1, 8, 12, 0, 0)))
    summer = next_weekly_calendar_fire(now=tz.localize(datetime(2026, 7, 9, 12, 0, 0)))
    assert winter.astimezone(pytz.UTC).hour == 0
    assert summer.astimezone(pytz.UTC).hour == 0
    assert winter.weekday() == 4 and summer.weekday() == 4


def test_apscheduler_cron_trigger_next_fire_matches_helper():
    from apscheduler.triggers.cron import CronTrigger

    kw = weekly_calendar_trigger_kwargs()
    trigger = CronTrigger(
        day_of_week=kw["day_of_week"],
        hour=kw["hour"],
        minute=kw["minute"],
        timezone=kw["timezone"],
    )
    tz = weekly_scheduler_tz()
    now = tz.localize(datetime(2026, 8, 13, 10, 0, 0))
    aps = trigger.get_next_fire_time(None, now)
    helper = next_weekly_calendar_fire(now=now)
    assert aps is not None
    assert aps.replace(microsecond=0) == helper.replace(microsecond=0)


def test_scheduler_registers_cron_not_interval_and_ignores_first_run_delay():
    from backend.app.core import scheduler as sched_mod

    src = inspect.getsource(sched_mod.start_scheduler)
    assert "weekly_calendar_trigger_kwargs" in src
    assert "next_weekly_calendar_fire" in src
    assert "first_run_delay_sec=ignored" in src
    assert "trigger=cron" in src
    start = src.find("cron_kwargs = weekly_calendar_trigger_kwargs")
    end = src.find("I7 lifelong", start)
    assert start != -1 and end != -1
    weekly_chunk = src[start:end]
    assert "weekly_interval_minutes" not in weekly_chunk
    assert "weekly_first_run_at" not in weekly_chunk
    assert "next_run_time" not in weekly_chunk
    assert "minutes=" not in weekly_chunk
