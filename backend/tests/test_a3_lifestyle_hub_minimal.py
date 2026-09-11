"""A3 Lifestyle hub — HR + I8 schedule projections + generic reminder eligibility."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app.core.security import create_access_token
from backend.app.models import (
    Device,
    I8OperationalPlan,
    I8OperationalPlanAction,
    PhysiologicalMeasurement,
    User,
    UserEvent,
    UserProfileCore,
)
from backend.app.services.i10.event_reminder_i10_adapter import (
    is_generic_remindable_event,
    is_medical_remindable_event,
    is_remindable_event,
    resolve_event_semantic_family,
)
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.lifestyle.a3_health_hr_projection import build_lifestyle_hr_projection


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _user(db, phone: str) -> User:
    u = User(name="LifeU", secret_key="t", preferred_language="en", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(UserProfileCore(user_id=u.id, timezone="UTC"))
    db.commit()
    return u


def _add_hr(db, user: User, value: float, key: str) -> None:
    device = Device(
        user_id=user.id,
        device_id=f"dev-{key}",
        device_type="heart_rate",
        status="active",
        token_hash=f"th-{key}",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    now = datetime.now(timezone.utc)
    db.add(
        PhysiologicalMeasurement(
            user_id=user.id,
            device_id=device.id,
            measurement_type="heart_rate",
            numeric_value=value,
            unit="bpm",
            measured_at=now,
            received_at=now,
            idempotency_key=f"pm-{key}",
            ingestion_status="accepted",
        )
    )
    db.commit()


def test_1_jwt_required_health_hr(client, db):
    assert client.get("/lifestyle/health-hr").status_code == 401


def test_2_self_hr_projection_shape(client, db):
    u = _user(db, "+18880000001")
    _add_hr(db, u, 72.0, "a1")
    r = client.get("/lifestyle/health-hr?range_key=7d", headers=_auth(u.id))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["hr_status"] in (
        "STABLE",
        "UNSTABLE_OR_CHANGED",
        "INSUFFICIENT_DATA",
    )
    assert "health_subject" not in str(data).lower()
    assert data["latest_value"] == 72.0
    assert data["range_key"] == "7d"
    assert "history" in data
    assert "available_from" in data


def test_3_cross_account_isolation(client, db):
    a = _user(db, "+18880000002")
    b = _user(db, "+18880000003")
    _add_hr(db, a, 88.0, "a2")
    ra = client.get("/lifestyle/health-hr", headers=_auth(a.id)).json()["data"]
    rb = client.get("/lifestyle/health-hr", headers=_auth(b.id)).json()["data"]
    assert ra["latest_value"] == 88.0
    assert rb["latest_value"] is None


def test_4_i8_schedule_actions(client, db):
    u = _user(db, "+18880000004")
    now = datetime.now(timezone.utc)
    window = resolve_local_day_window(db, u.id, now_utc=now)
    plan = I8OperationalPlan(
        user_id=u.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        status="ACTIVE",
        generation_mode="reactive",
        plan_idempotency_key=f"life-plan-{u.id}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    db.add(
        I8OperationalPlanAction(
            user_id=u.id,
            plan_id=plan.id,
            action_domain="lifestyle",
            action_type="walk",
            action_idempotency_key=f"life-act-{u.id}",
            status="ACTIVE",
            summary_text="Evening walk",
            presentation_json="{}",
            knowledge_refs_json="[]",
            safety_state="SAFE",
            clarification_required=False,
            valid_from=now,
            valid_until=now + timedelta(hours=6),
            expires_at=now + timedelta(hours=6),
        )
    )
    db.commit()
    r = client.get("/lifestyle/schedule-actions", headers=_auth(u.id))
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Evening walk"
    assert items[0]["status"] == "upcoming"
    assert "id" not in items[0]


def test_5_userevent_ownership_list(client, db):
    a = _user(db, "+18880000005")
    b = _user(db, "+18880000006")
    now = datetime.utcnow()
    db.add(
        UserEvent(
            user_id=a.id,
            title="Exam",
            event_domain="education",
            event_type="exam",
            starts_at=now + timedelta(hours=5),
            status="scheduled",
            importance="normal",
            reminder_enabled=True,
            reminder_offsets_json="[60]",
            source="manual",
        )
    )
    db.commit()
    ra = client.get("/user/events", headers=_auth(a.id)).json()["data"]["events"]
    rb = client.get("/user/events", headers=_auth(b.id)).json()["data"]["events"]
    assert any(e["title"] == "Exam" for e in ra)
    assert not any(e["title"] == "Exam" for e in rb)


def test_6_generic_reminder_eligibility():
    medical = UserEvent(
        user_id=1,
        title="Doc",
        event_domain="medical",
        event_type="doctor_visit",
        starts_at=datetime.utcnow(),
        status="scheduled",
    )
    exam = UserEvent(
        user_id=1,
        title="Exam",
        event_domain="education",
        event_type="exam",
        starts_at=datetime.utcnow(),
        status="scheduled",
    )
    assert is_medical_remindable_event(medical)
    assert not is_generic_remindable_event(medical)
    assert is_generic_remindable_event(exam)
    assert is_remindable_event(exam)
    assert resolve_event_semantic_family("exam", medical=False) == I10SemanticFamily.REMINDER


def test_7_hr_range_keys(client, db):
    u = _user(db, "+18880000007")
    for key in ("7d", "30d", "3m", "1y"):
        data = build_lifestyle_hr_projection(db, u.id, range_key=key)
        assert data["range_key"] == key
        assert data["hr_status"] in (
            "STABLE",
            "UNSTABLE_OR_CHANGED",
            "INSUFFICIENT_DATA",
        )
