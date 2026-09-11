"""Rolling 7-local-day Lifestyle weekly cycle + shared I8 nutrition/exercise plan."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i8.action_completion import complete_exact_operational_action
from backend.app.services.i8.local_day import (
    CYCLE_START_META_KEY,
    rolling_cycle_end,
    _window_for_local_date,
)
from backend.app.services.i8.unified_core import generate_operational_action
from backend.app.services.lifestyle.a3_schedule_i8_projection import (
    build_lifestyle_i8_schedule_projection,
)
from backend.app.services.lifestyle.a3_weekly_plan_projection import (
    build_lifestyle_weekly_plan_projection,
)


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _user(db, phone: str, *, tz: str | None = "UTC") -> models.User:
    u = models.User(name="RollU", secret_key="t", preferred_language="en", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    if tz is not None:
        db.add(models.UserProfileCore(user_id=u.id, timezone=tz))
        db.commit()
    return u


def _ok_item(domain: str = "nutrition", statement: str = "Eat balanced meals"):
    return RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="KU-1",
        immutable_version_id="v1",
        memory_item_id="m1",
        memory_row_id=1,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=None,
        domain=domain,
        language="en",
        topic_taxonomy=None,
        normalized_statement=statement,
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )


def _seed_consent(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=True)
    write_fact(db, user_id, "lifestyle", "diet_notes", "home cooking", commit=True)


def _patch_knowledge(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        lambda *a, **k: SimpleNamespace(
            status=STATUS_OK,
            items=[_ok_item(domain=k.get("domain") or "nutrition")],
        ),
    )


def _gen(db, user, *, request: str, domain: str, **kwargs):
    return generate_operational_action(
        db,
        user_id=user.id,
        actor_user_id=user.id,
        request=request,
        domain=domain,
        persist=True,
        **kwargs,
    )


def _dates(start: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def test_1_friday_start_seven_days(db, monkeypatch):
    u = _user(db, "+17770000001")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    friday = date(2026, 9, 11)  # Friday
    r = _gen(
        db,
        u,
        request="friday lunch meal",
        domain="nutrition",
        target_local_date=friday,
    )
    assert r.status == "ACTION_PERSISTED"
    # Freeze "today" inside cycle for projection
    now = datetime(2026, 9, 12, 15, 0, tzinfo=timezone.utc)  # Sat
    proj = build_lifestyle_weekly_plan_projection(db, u.id, now_utc=now)
    assert proj["cycle_start"] == friday.isoformat()
    assert proj["cycle_end"] == (friday + timedelta(days=6)).isoformat()
    assert [d["local_date"] for d in proj["days"]] == _dates(friday)
    assert proj["days"][0]["local_date"].startswith("2026-09-11")  # Fri
    assert proj["days"][6]["local_date"].startswith("2026-09-17")  # Thu
    assert proj["state"] == "active"


def test_2_monday_start_seven_days(db, monkeypatch):
    u = _user(db, "+17770000002")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    monday = date(2026, 9, 7)
    _gen(db, u, request="monday meal", domain="nutrition", target_local_date=monday)
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    proj = build_lifestyle_weekly_plan_projection(db, u.id, now_utc=now)
    assert [d["local_date"] for d in proj["days"]] == _dates(monday)
    assert proj["cycle_end"] == date(2026, 9, 13).isoformat()


def test_3_wednesday_start_seven_days(db, monkeypatch):
    u = _user(db, "+17770000003")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    wed = date(2026, 9, 9)
    _gen(db, u, request="wed meal", domain="nutrition", target_local_date=wed)
    now = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    proj = build_lifestyle_weekly_plan_projection(db, u.id, now_utc=now)
    assert [d["local_date"] for d in proj["days"]] == _dates(wed)
    assert proj["days"][-1]["local_date"] == date(2026, 9, 15).isoformat()  # Tue


def test_4_review_due_boundary(db, monkeypatch):
    u = _user(db, "+17770000004")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    start = date(2026, 9, 11)  # Fri
    end = rolling_cycle_end(start)  # Thu 17
    _gen(db, u, request="boundary meal", domain="nutrition", target_local_date=start)
    before_end = datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc)  # still Day 7
    proj_active = build_lifestyle_weekly_plan_projection(db, u.id, now_utc=before_end)
    assert proj_active["state"] == "active"
    assert proj_active["review_due"] is False
    after_end = datetime(2026, 9, 18, 0, 30, tzinfo=timezone.utc)  # Fri after cycle
    proj_due = build_lifestyle_weekly_plan_projection(db, u.id, now_utc=after_end)
    assert proj_due["state"] == "review_due"
    assert proj_due["review_due"] is True
    assert proj_due["cycle_start"] == start.isoformat()
    assert proj_due["cycle_end"] == end.isoformat()


def test_5_new_cycle_supersedes_old_review(db, monkeypatch):
    u = _user(db, "+17770000005")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    old_start = date(2026, 9, 4)  # Fri
    _gen(db, u, request="old cycle meal", domain="nutrition", target_local_date=old_start)
    # After old cycle ends, start a new cycle
    new_start = date(2026, 9, 18)  # Fri
    now_new = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc)
    # Persist using now-aware path: monkeypatch local today via target on new start
    # First ensure review_due would show old
    due = build_lifestyle_weekly_plan_projection(
        db, u.id, now_utc=datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    )
    assert due["state"] == "review_due"
    _gen(
        db,
        u,
        request="new cycle meal",
        domain="nutrition",
        target_local_date=new_start,
    )
    proj = build_lifestyle_weekly_plan_projection(db, u.id, now_utc=now_new)
    assert proj["state"] == "active"
    assert proj["review_due"] is False
    assert proj["cycle_start"] == new_start.isoformat()


def test_6_empty_account(db):
    u = _user(db, "+17770000006")
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    assert proj["state"] == "empty"
    assert proj["cycle_start"] is None
    assert proj["days"] == []
    assert proj["review_due"] is False


def test_7_dst_seven_local_dates():
    # Spring-forward day inside a Fri→Thu cycle still yields 7 local dates.
    start = date(2026, 3, 6)  # Friday
    days = [start + timedelta(days=i) for i in range(7)]
    assert date(2026, 3, 8) in days  # DST transition date in US
    assert len(days) == 7
    w = _window_for_local_date("America/New_York", date(2026, 3, 8))
    assert w.user_local_date == date(2026, 3, 8)


def test_8_missing_timezone(db, monkeypatch):
    u = _user(db, "+17770000008", tz=None)
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    r = _gen(db, u, request="meal", domain="nutrition")
    assert r.status == "TIMEZONE_REQUIRED"
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    assert proj["state"] == "unavailable"


def test_9_invalid_timezone(db, monkeypatch):
    u = _user(db, "+17770000009", tz="Not/AZone")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    r = _gen(db, u, request="meal", domain="nutrition")
    assert r.status == "TIMEZONE_INVALID"
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    assert proj["state"] == "unavailable"


def test_10_nutrition_exercise_same_plan(db, monkeypatch):
    u = _user(db, "+17770000010")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    n = _gen(db, u, request="lunch meal", domain="nutrition")
    e = _gen(db, u, request="walk workout", domain="exercise")
    assert n.plan_id == e.plan_id
    act = db.get(models.I8OperationalPlanAction, n.action_id)
    assert json.loads(act.presentation_json)[CYCLE_START_META_KEY]


def test_11_no_cross_domain_supersede(db, monkeypatch):
    u = _user(db, "+17770000011")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    n = _gen(db, u, request="meal one", domain="nutrition")
    e = _gen(db, u, request="exercise one", domain="exercise")
    assert (
        db.query(models.I8OperationalPlan)
        .filter_by(user_id=u.id, status="ACTIVE")
        .count()
        == 1
    )
    assert n.plan_id == e.plan_id


def test_12_action_idempotency(db, monkeypatch):
    u = _user(db, "+17770000012")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    a = _gen(db, u, request="same lunch meal", domain="nutrition")
    b = _gen(db, u, request="same lunch meal", domain="nutrition")
    assert a.action_id == b.action_id


def test_13_done_semantics(db, monkeypatch):
    u = _user(db, "+17770000013")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    n = _gen(db, u, request="meal done", domain="nutrition")
    e = _gen(db, u, request="exercise keep", domain="exercise")
    complete_exact_operational_action(db, actor_user_id=u.id, action_id=n.action_id)
    db.commit()
    assert db.get(models.I8OperationalPlanAction, n.action_id).status == "COMPLETED"
    assert db.get(models.I8OperationalPlanAction, e.action_id).status == "ACTIVE"


def test_14_i5_grounding(db, monkeypatch):
    u = _user(db, "+17770000014")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    r = _gen(db, u, request="grounded meal", domain="nutrition")
    act = db.get(models.I8OperationalPlanAction, r.action_id)
    assert json.loads(act.presentation_json)["grounding"] == "governed_i5_reference"
    assert "Eat balanced" not in (act.presentation_json or "")


def test_15_i6_consent(db, monkeypatch):
    u = _user(db, "+17770000015")
    _patch_knowledge(monkeypatch)
    r = _gen(db, u, request="meal", domain="nutrition")
    assert r.status == "CONSENT_REQUIRED"


def test_16_i7_no_raw_transcript(db, monkeypatch):
    u = _user(db, "+17770000016")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    r = _gen(db, u, request="meal", domain="nutrition")
    act = db.get(models.I8OperationalPlanAction, r.action_id)
    blob = (act.presentation_json or "") + (act.summary_text or "")
    assert "transcript" not in blob.lower()


def test_17_get_side_effect_free(client, db):
    u = _user(db, "+17770000017")
    before = db.query(models.I8OperationalPlan).count()
    r = client.get("/lifestyle/weekly-plan", headers=_auth(u.id))
    assert r.status_code == 200
    assert db.query(models.I8OperationalPlan).count() == before


def test_18_schedule_actions_unchanged(client, db, monkeypatch):
    u = _user(db, "+17770000018")
    _seed_consent(db, u.id)
    _patch_knowledge(monkeypatch)
    _gen(db, u, request="lunch meal", domain="nutrition")
    _gen(db, u, request="walk workout", domain="exercise")
    r = client.get("/lifestyle/schedule-actions", headers=_auth(u.id))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["plan_state"] == "active"
    domains = {i["domain"] for i in data["items"]}
    assert "nutrition" in domains and "exercise" in domains


def test_19_my_schedule_userevent_separation(db):
    u = _user(db, "+17770000019")
    before = db.query(models.UserEvent).filter_by(user_id=u.id).count()
    build_lifestyle_weekly_plan_projection(db, u.id)
    build_lifestyle_i8_schedule_projection(db, u.id)
    assert db.query(models.UserEvent).filter_by(user_id=u.id).count() == before
