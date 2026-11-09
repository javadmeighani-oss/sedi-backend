"""R-074 step 5b (B): the weekly layer report for Javad - aggregate only, fail-open per layer, real queries on the test DB."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from backend.app import models
from backend.app.services.i5 import weekly_layers_report as lr

NOW = datetime(2026, 11, 8, 12, 0, 0)


def _user(db, name="layers"):
    u = models.User(name=name, secret_key="layers-test", preferred_language="en")
    db.add(u)
    db.flush()
    return u


def test_the_report_counts_the_last_seven_days_only(db):
    u = _user(db)
    old, fresh = NOW - timedelta(days=10), NOW - timedelta(days=1)
    for when, sent, opened in ((fresh, True, True), (fresh, True, False), (fresh, False, False), (old, True, True)):
        db.add(
            models.Notification(
                user_id=u.id, type="INSIGHT", body="x", is_sent=sent, created_at=when, category="care",
                opened_at=when if opened else None,
            )
        )
    for when, kind in ((fresh, "user_schedule_done"), (fresh, "user_schedule_done"), (fresh, "user_schedule_notdone"), (old, "user_schedule_done")):
        db.add(models.InteractionEvent(user_id=u.id, source="schedule", event_type=kind, source_id=f"x:{when.timestamp()}", created_at=when))
    for when, status in ((fresh, "open"), (fresh, "done"), (old, "open")):
        db.add(models.CareFollowUpTask(user_id=u.id, title="t", status=status, source="commitment", created_at=when))
    db.flush()

    r = lr.build_weekly_layers_report(db, models, now_utc=NOW)
    hands = r["layers"]["L4_agent_hands"]
    assert hands["notifications"]["created"] == 3 and hands["notifications"]["sent"] == 2 and hands["notifications"]["opened"] == 1
    assert hands["notifications"]["open_rate_of_sent"] == 0.5 and hands["notifications"]["by_category"] == {"care": 3}
    assert hands["user_done"] == {"state": "ok", "done": 2, "not_done": 1, "done_rate": 0.667}
    assert hands["commitments"]["opened_this_week"] == 2 and hands["commitments"]["still_open"] == 1
    assert hands["commitments"]["by_source"] == {"commitment": 2}


def test_the_report_has_no_user_text_or_ids(db):
    u = _user(db, "privacy")
    db.add(models.Notification(user_id=u.id, type="INSIGHT", body="SECRET-BODY", title="SECRET-TITLE", is_sent=True, created_at=NOW))
    db.flush()
    blob = json.dumps(lr.build_weekly_layers_report(db, models, now_utc=NOW), ensure_ascii=False)
    assert "SECRET" not in blob and "privacy" not in blob and f'"user_id"' not in blob


def test_the_depth_layer_is_marked_external_not_invented(db):
    r = lr.build_weekly_layers_report(db, models, now_utc=NOW)
    assert r["layers"]["L1_L2_answer_depth"]["state"] == "external"
    assert "i5-depth-audit-readonly" in r["layers"]["L1_L2_answer_depth"]["note"]
    assert r["layers"]["L5_state_contract"]["contract"] == "UserState"
    assert r["layers"]["L3_rag_books"]["state"] == "ok" and r["layers"]["L3_rag_books"]["eligible_total"] >= 0


def test_one_broken_layer_does_not_hide_the_others(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(lr, "_l4_notifications", boom)
    r = lr.build_weekly_layers_report(db, models, now_utc=NOW)
    assert r["layers"]["L4_agent_hands"]["notifications"] == {"state": "unavailable", "error": "RuntimeError"}
    assert r["layers"]["L4_agent_hands"]["user_done"]["state"] == "ok"


def test_the_weekly_hook_logs_one_line_and_never_raises(db, caplog):
    with caplog.at_level("INFO", logger=lr.logger.name):
        out = lr.log_weekly_layers_report(db, models)
    assert out and any("i5_weekly_layers_report " in rec.getMessage() for rec in caplog.records)
    assert lr.log_weekly_layers_report(None) is None


def test_rate_helper_handles_zero():
    assert lr._rate(1, 0) is None and lr._rate(1, 4) == 0.25


def test_the_weekly_runtime_calls_the_layer_hook_after_the_growth_report():
    import inspect

    from backend.app.services.i5 import governed_weekly_runtime as gwr

    src = inspect.getsource(gwr)
    assert src.index("log_weekly_growth_report(session") < src.index("log_weekly_layers_report(session")
