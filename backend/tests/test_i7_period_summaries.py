"""I7 period summaries are compression only; I6 facts remain source of truth."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import correct_fact, delete_fact, write_fact
from backend.app.services.i7.period_summaries import (
    PeriodSummaryError,
    invalidate_summaries_for_user,
    period_bounds,
    rebuild_summary,
)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key="i7-test", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def test_i7_period_boundaries_tehran_daily_weekly_monthly_yearly():
    import pytz

    tz = pytz.timezone("Asia/Tehran")
    now = datetime(2026, 8, 13, 22, 15, 0)
    d0, d1 = period_bounds("DAILY", now=now)
    assert (d1 - d0).days == 1
    assert d0.astimezone(tz).hour == 0
    w0, w1 = period_bounds("WEEKLY", now=now)
    assert (w1 - w0).days == 7
    assert w0.astimezone(tz).weekday() == 0
    m0, m1 = period_bounds("MONTHLY", now=now)
    assert m0.astimezone(tz).day == 1
    assert m0.astimezone(tz).hour == 0
    y0, y1 = period_bounds("YEARLY", now=now)
    assert y0.astimezone(tz).month == 1 and y0.astimezone(tz).day == 1
    assert y1.astimezone(tz).year == y0.astimezone(tz).year + 1
    with pytest.raises(PeriodSummaryError):
        period_bounds("HOUR")


def test_i7_rebuild_is_compression_not_authority(db):
    user = _user(db, "i7-rebuild")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "vegetarian", commit=True)
    summary = rebuild_summary(db, user.id, "DAILY", commit=True)
    assert "I6_FACTS_ARE_SOT" in summary.structured_summary_json
    assert "not source of truth" in summary.narrative_summary.lower()
    assert summary.status == "active"
    again = rebuild_summary(db, user.id, "DAILY", commit=True)
    db.refresh(summary)
    assert again.version == summary.version + 1
    assert summary.status == "superseded"
    assert again.status == "active"


def test_i7_weekly_monthly_yearly_rebuild(db):
    user = _user(db, "i7-periods")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "goals", "health_goals", "walk", commit=True)
    for kind in ("WEEKLY", "MONTHLY", "YEARLY"):
        row = rebuild_summary(db, user.id, kind, commit=True)
        assert row.summary_type == kind
        assert row.status == "active"


def test_i7_correction_and_deletion_invalidate(db):
    user = _user(db, "i7-propagate")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "black tea", commit=True)
    daily = rebuild_summary(db, user.id, "DAILY", commit=True)
    correct_fact(db, user.id, "lifestyle", "food_habits", "coffee", commit=True)
    db.refresh(daily)
    assert daily.status == "stale"
    daily2 = rebuild_summary(db, user.id, "DAILY", commit=True)
    delete_fact(db, user.id, "lifestyle", "food_habits", commit=True)
    db.refresh(daily2)
    assert daily2.status == "stale"


def test_i7_retry_rebuild_increments_version(db):
    user = _user(db, "i7-retry")
    grant_memory_consent(db, user.id, commit=True)
    a = rebuild_summary(db, user.id, "DAILY", commit=True)
    b = rebuild_summary(db, user.id, "DAILY", commit=True)
    assert b.version == a.version + 1


def test_i7_isolation(db):
    a = _user(db, "i7-iso-a")
    b = _user(db, "i7-iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "lifestyle", "mood", "a-only", commit=True)
    sa = rebuild_summary(db, a.id, "DAILY", commit=True)
    sb = rebuild_summary(db, b.id, "DAILY", commit=True)
    assert "lifestyle.mood" in sa.structured_summary_json
    assert "lifestyle.mood" not in sb.structured_summary_json
    n = invalidate_summaries_for_user(db, a.id, reason="test", commit=True)
    assert n == 1
    db.refresh(sb)
    assert sb.status == "active"
