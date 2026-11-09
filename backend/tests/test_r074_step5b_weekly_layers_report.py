"""R-074 step 5b (B): the weekly layer report for Javad - aggregate only, fail-open per layer, real queries on the test DB."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import models
from backend.app.services.i5 import weekly_layers_report as lr

NOW = datetime(2026, 11, 8, 12, 0, 0)


def _user(db, name="layers"):
    u = models.User(name=name, secret_key="layers-test", preferred_language="en")
    db.add(u)
    db.flush()
    return u


def test_the_report_counts_the_last_seven_days_by_event_time_and_resolved_outcomes(db):
    from backend.app.services.i7 import user_done

    now = datetime.utcnow()
    u = _user(db)
    old, fresh = now - timedelta(days=10), now - timedelta(days=1)
    # created old but delivered/opened inside the window counts as sent/opened this week (Codex P2: event time)
    rows = [
        dict(created_at=fresh, is_sent=True, sent_at=fresh, opened_at=fresh.replace(tzinfo=timezone.utc)),
        dict(created_at=fresh, is_sent=True, sent_at=fresh, opened_at=None),
        dict(created_at=fresh, is_sent=False, sent_at=None, opened_at=None),
        dict(created_at=old, is_sent=True, sent_at=fresh, opened_at=fresh.replace(tzinfo=timezone.utc)),
        dict(created_at=old, is_sent=True, sent_at=old, opened_at=old.replace(tzinfo=timezone.utc)),
    ]
    for r in rows:
        db.add(models.Notification(user_id=u.id, type="INSIGHT", body="x", category="care", **r))
    today = now.date()
    # two done, one done-then-undone (must NOT count), one not-done
    user_done.record(db, u.id, kind="medication", ref_id=1, day=today, hhmm="0800", domain="medication", done=True)
    user_done.record(db, u.id, kind="medication", ref_id=2, day=today, hhmm="0800", domain="medication", done=True)
    user_done.record(db, u.id, kind="medication", ref_id=3, day=today, hhmm="0800", domain="medication", done=True)
    user_done.record(db, u.id, kind="medication", ref_id=3, day=today, hhmm="0800", domain="medication", done=False)
    user_done.record_not_done(db, u.id, kind="medication", ref_id=4, day=today, hhmm="0800", domain="medication", reason="tired")
    marker = '"follow_up_kind":"commitment"'
    for status, desc in (("open", marker), ("notified", marker), ("done", marker), ("open", '"follow_up_kind":"post_event"'), ("open", None)):
        db.add(models.CareFollowUpTask(user_id=u.id, title="t", status=status, source="general_contextual", description=desc, created_at=fresh))
    db.add(models.CareFollowUpTask(user_id=u.id, title="t", status="open", source="x", description=marker, created_at=old))
    db.flush()

    r = lr.build_weekly_layers_report(db, models, now_utc=now)
    hands = r["layers"]["L4_agent_hands"]
    n = hands["notifications"]
    assert n["created"] == 3 and n["sent"] == 3 and n["opened"] == 2 and n["open_rate_of_sent"] == 0.667
    assert n["by_category"] == {"care": 3}
    assert hands["user_done"]["done"] == 2 and hands["user_done"]["not_done"] == 1 and hands["user_done"]["done_rate"] == 0.667
    c = hands["commitments"]
    assert c["opened_this_week"] == 3 and c["still_open"] == 2  # commitments only; open + notified
    assert c["by_status"] == {"done": 1, "notified": 1, "open": 1}


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
