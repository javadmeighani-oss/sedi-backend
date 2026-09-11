"""A3 Profile I6+I8 summary projection — targeted Postgres tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app.core.security import create_access_token
from backend.app.models import I8OperationalPlan, I8OperationalPlanAction, User, UserProfileCore
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.profile.a3_profile_summary import build_a3_profile_summary


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _user(db, phone: str, *, tz: str | None = "UTC") -> User:
    u = User(name="ProfileU", secret_key="t", preferred_language="en", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    if tz:
        db.add(UserProfileCore(user_id=u.id, timezone=tz))
        db.commit()
    return u


def _keys(data: dict) -> dict[str, str]:
    return {r["key"]: r["status"] for r in (data.get("rows") or [])}


def _add_plan_with_action(db, user: User, *, action_status: str) -> None:
    now = datetime.now(timezone.utc)
    window = resolve_local_day_window(db, user.id, now_utc=now)
    plan = I8OperationalPlan(
        user_id=user.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        status="ACTIVE",
        generation_mode="reactive",
        plan_idempotency_key=f"plan-{user.id}-{action_status}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    db.add(
        I8OperationalPlanAction(
            user_id=user.id,
            plan_id=plan.id,
            action_domain="lifestyle",
            action_type="check_in",
            action_idempotency_key=f"act-{user.id}-{action_status}",
            status=action_status,
            summary_text="Check in",
            presentation_json="{}",
            knowledge_refs_json="[]",
            safety_state="SAFE",
            clarification_required=False,
            valid_from=now,
            valid_until=now + timedelta(hours=12),
            expires_at=now + timedelta(hours=12),
        )
    )
    db.commit()


def test_1_jwt_required(client, db):
    r = client.get("/auth/me/profile-summary")
    assert r.status_code == 401


def test_2_i6_granted_projected(client, db):
    u = _user(db, "+17770000001")
    grant_memory_consent(db, u.id, commit=True)
    r = client.get("/auth/me/profile-summary", headers=_auth(u.id))
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    rows = _keys(body.get("data") or {})
    assert rows["memory_consent"] == "granted"
    assert rows["memory_write"] == "allowed"
    assert rows["memory_read"] == "allowed"
    assert all(set(r.keys()) == {"key", "status"} for r in body["data"]["rows"])


def test_3_i6_absent_and_revoked(client, db):
    u = _user(db, "+17770000002")
    r = client.get("/auth/me/profile-summary", headers=_auth(u.id))
    rows = _keys(r.json().get("data") or {})
    assert rows["memory_consent"] == "not_granted"
    assert rows["memory_write"] == "denied"

    grant_memory_consent(db, u.id, commit=True)
    revoke_memory_consent(db, u.id, commit=True)
    r2 = client.get("/auth/me/profile-summary", headers=_auth(u.id))
    rows2 = _keys(r2.json().get("data") or {})
    assert rows2["memory_consent"] in ("revoked", "not_granted")


def test_4_i8_active_plan(client, db):
    u = _user(db, "+17770000003")
    _add_plan_with_action(db, u, action_status="ACTIVE")
    rows = _keys(
        client.get("/auth/me/profile-summary", headers=_auth(u.id)).json().get("data") or {}
    )
    assert rows["daily_plan"] == "active"
    assert rows["plan_actions"] == "in_progress"


def test_5_i8_no_active_plan(client, db):
    u = _user(db, "+17770000004")
    rows = _keys(
        client.get("/auth/me/profile-summary", headers=_auth(u.id)).json().get("data") or {}
    )
    assert rows["daily_plan"] == "none"
    assert rows["plan_actions"] == "none"


def test_6_i8_completed_actions(client, db):
    u = _user(db, "+17770000005")
    _add_plan_with_action(db, u, action_status="COMPLETED")
    rows = _keys(
        client.get("/auth/me/profile-summary", headers=_auth(u.id)).json().get("data") or {}
    )
    assert rows["plan_actions"] == "completed"


def test_7_cross_account_isolation(client, db):
    a = _user(db, "+17770000006")
    b = _user(db, "+17770000007")
    grant_memory_consent(db, a.id, commit=True)
    ra = _keys(client.get("/auth/me/profile-summary", headers=_auth(a.id)).json().get("data") or {})
    rb = _keys(client.get("/auth/me/profile-summary", headers=_auth(b.id)).json().get("data") or {})
    assert ra["memory_consent"] == "granted"
    assert rb["memory_consent"] == "not_granted"


def test_8_no_raw_ids_or_codes(client, db):
    u = _user(db, "+17770000008")
    data = build_a3_profile_summary(db, u.id)
    blob = str(data).lower()
    assert "trace" not in blob
    assert "plan_id" not in blob
    assert "action_id" not in blob
    assert "health_subject" not in blob
    for row in data["rows"]:
        assert set(row.keys()) == {"key", "status"}
