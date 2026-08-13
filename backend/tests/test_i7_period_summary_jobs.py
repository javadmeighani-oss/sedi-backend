"""I7 period-summary job contracts — dormant by default, idempotent, isolated."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime
import inspect

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import (
    export_memory_bundle,
    list_fact_history,
    write_fact,
)
from backend.app.services.i7.jobs import (
    closed_period_anchor,
    period_summary_cron_kwargs,
    period_summary_jobs_enabled,
    run_period_summary_sweep,
)
from backend.app.services.i7.period_summaries import GENERATOR_VERSION, rebuild_summary


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key="i7job", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def test_i7_cron_specs_timezone_singleton_coalesce():
    daily = period_summary_cron_kwargs("DAILY")
    weekly = period_summary_cron_kwargs("WEEKLY")
    monthly = period_summary_cron_kwargs("MONTHLY")
    yearly = period_summary_cron_kwargs("YEARLY")
    for kw in (daily, weekly, monthly, yearly):
        assert kw["trigger"] == "cron"
        assert kw["timezone"] == "Asia/Tehran"
        assert kw["max_instances"] == 1
        assert kw["coalesce"] is True
    assert daily["hour"] == 0 and daily["minute"] == 10
    assert weekly["day_of_week"] == "mon"
    assert monthly["day"] == 1
    assert yearly["month"] == 1 and yearly["day"] == 1


def test_i7_jobs_default_dormant(monkeypatch):
    monkeypatch.delenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", raising=False)
    assert period_summary_jobs_enabled() is False


def test_i7_sweep_dormant_without_flag(db, monkeypatch):
    monkeypatch.delenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", raising=False)
    user = _user(db, "i7-dormant")
    grant_memory_consent(db, user.id, commit=True)
    result = run_period_summary_sweep(db, "DAILY", persist=True)
    assert result.detail == "DORMANT_FLAG_OFF"
    assert result.rebuilt == 0
    assert db.query(models.UserPeriodSummary).count() == 0


def test_i7_sweep_rebuild_idempotent_and_isolated(db, monkeypatch):
    monkeypatch.setenv("SEDI_I7_PERIOD_SUMMARY_JOBS_ENABLED", "true")
    a = _user(db, "i7-job-a")
    b = _user(db, "i7-job-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "lifestyle", "diet_notes", "vegetarian meals", commit=True)
    first = run_period_summary_sweep(
        db, "DAILY", now=datetime(2026, 8, 14, 0, 10, 0), persist=True
    )
    assert first.enabled is True
    assert first.rebuilt >= 1
    assert first.failed == 0
    second = run_period_summary_sweep(
        db, "DAILY", now=datetime(2026, 8, 14, 0, 10, 0), persist=True
    )
    assert second.skipped >= 1
    a_rows = db.query(models.UserPeriodSummary).filter_by(user_id=a.id).all()
    b_rows = db.query(models.UserPeriodSummary).filter_by(user_id=b.id).all()
    assert a_rows
    assert all("I6_FACTS_ARE_SOT" in (r.structured_summary_json or "") for r in a_rows)
    assert all(GENERATOR_VERSION in (r.structured_summary_json or "") for r in a_rows)
    assert all("lifestyle.diet_notes" not in (r.structured_summary_json or "") for r in b_rows)


def test_i7_closed_period_is_previous_window():
    now = datetime(2026, 8, 14, 0, 10, 0)
    anchor = closed_period_anchor("DAILY", now=now)
    assert anchor.day == 13


def test_i6_history_and_export_are_not_diagnosis(db):
    user = _user(db, "i6-hist")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "vegetarian meals", commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "pescatarian meals", commit=True)
    hist = list_fact_history(db, user.id, "lifestyle", "diet_notes")
    assert len(hist) == 2
    assert hist[0].fact_status == "superseded"
    assert hist[1].fact_status == "active"
    bundle = export_memory_bundle(db, user.id)
    assert bundle["authority"] == "I6_FACTS_ARE_SOT"
    assert bundle["export_is_not_diagnosis"] is True
    assert len(bundle["facts"]) == 2


def test_scheduler_registers_i7_jobs():
    from backend.app.core import scheduler as sched_mod

    src = inspect.getsource(sched_mod.start_scheduler)
    assert "DAILY_JOB_ID" in src
    assert "period_summary_cron_kwargs" in src
    assert "period_summary_jobs_enabled" in src
    assert "i7 period summary jobs registered" in src


def test_i7_idempotent_rebuild_same_payload(db):
    user = _user(db, "i7-idemp")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "goals", "health_goals", "walk daily", commit=True)
    a = rebuild_summary(db, user.id, "DAILY", commit=True)
    b = rebuild_summary(db, user.id, "DAILY", commit=True)
    assert a.id == b.id
