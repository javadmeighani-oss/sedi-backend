"""I6 product/API write-surface closure — consent-gated lifestyle, admin, consent HTTP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import User, UserFactCandidate, UserMemoryFact, UserPeriodSummary
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent

_TEST_ADMIN_TOKEN = "test-i6-closure-admin"


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _admin() -> dict[str, str]:
    return {"X-Admin-Token": _TEST_ADMIN_TOKEN}


def _user(db, name: str) -> User:
    u = User(name=name, secret_key="i6-closure", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _lifestyle_body(**overrides) -> dict:
    body = {
        "entries": [
            {
                "domain": "lifestyle",
                "key": "sleep_duration_hours",
                "value": 7.5,
                "confidence": 0.8,
                "source": "manual",
            }
        ]
    }
    body.update(overrides)
    return body


def test_lifestyle_update_fails_without_consent(client, db):
    u = _user(db, "i6-no-consent")
    resp = client.post("/lifestyle/update", json=_lifestyle_body(), headers=_auth(u.id))
    assert resp.status_code == 200
    payload = resp.json()
    assert payload.get("ok") is False
    assert db.query(UserMemoryFact).filter_by(user_id=u.id).count() == 0


def test_lifestyle_update_succeeds_with_consent(client, db):
    u = _user(db, "i6-granted")
    grant_memory_consent(db, u.id, commit=True)
    resp = client.post("/lifestyle/update", json=_lifestyle_body(), headers=_auth(u.id))
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
    assert db.query(UserMemoryFact).filter_by(user_id=u.id, fact_status="active").count() == 1


def test_lifestyle_update_blocked_after_revoke(client, db):
    u = _user(db, "i6-revoked")
    grant_memory_consent(db, u.id, commit=True)
    first = client.post("/lifestyle/update", json=_lifestyle_body(), headers=_auth(u.id))
    assert first.json().get("ok") is True
    revoke_memory_consent(db, u.id, commit=True)
    second = client.post("/lifestyle/update", json=_lifestyle_body(), headers=_auth(u.id))
    assert second.json().get("ok") is False


def test_lifestyle_update_blocked_after_expiry(client, db, monkeypatch):
    u = _user(db, "i6-expired")
    consent = grant_memory_consent(db, u.id, commit=True)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    resp = client.post("/lifestyle/update", json=_lifestyle_body(), headers=_auth(u.id))
    assert resp.json().get("ok") is False


def test_lifestyle_update_jwt_identity_only(client, db):
    u = _user(db, "i6-jwt")
    grant_memory_consent(db, u.id, commit=True)
    body = _lifestyle_body(user_id=u.id + 999)
    resp = client.post("/lifestyle/update", json=body, headers=_auth(u.id))
    assert resp.status_code == 422


def test_admin_candidate_accept_requires_consent(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _user(db, "i6-admin-no-consent")
    cand = UserFactCandidate(
        user_id=u.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value_json="8.0",
        confidence=0.9,
        is_explicit=True,
        status="pending",
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    resp = client.post(
        f"/lifestyle/admin/candidates/{cand.id}/decision",
        json={"status": "accepted"},
        headers=_admin(),
    )
    assert resp.status_code == 200
    assert resp.json().get("ok") is False
    assert resp.json().get("error", {}).get("code") == "CONSENT_DENIED"
    db.refresh(cand)
    assert cand.status == "pending"


def test_admin_candidate_accept_with_consent(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _user(db, "i6-admin-consent")
    grant_memory_consent(db, u.id, commit=True)
    cand = UserFactCandidate(
        user_id=u.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value_json="8.0",
        confidence=0.9,
        is_explicit=True,
        status="pending",
    )
    db.add(cand)
    db.commit()
    db.refresh(cand)
    resp = client.post(
        f"/lifestyle/admin/candidates/{cand.id}/decision",
        json={"status": "accepted"},
        headers=_admin(),
    )
    assert resp.json().get("ok") is True
    assert db.query(UserMemoryFact).filter_by(user_id=u.id, fact_status="active").count() == 1


def test_lifestyle_correction_invalidates_i7_derived_state(client, db):
    u = _user(db, "i6-i7-invalidate")
    grant_memory_consent(db, u.id, commit=True)
    summary = UserPeriodSummary(
        user_id=u.id,
        summary_type="DAILY",
        period_start=datetime(2026, 8, 18, tzinfo=timezone.utc),
        period_end=datetime(2026, 8, 18, 23, 59, 59, tzinfo=timezone.utc),
        version=1,
        narrative_summary="day",
        generated_at=datetime.now(timezone.utc),
        status="active",
    )
    db.add(summary)
    db.commit()
    client.post(
        "/lifestyle/update",
        json=_lifestyle_body(),
        headers=_auth(u.id),
    )
    client.post(
        "/lifestyle/update",
        json=_lifestyle_body(
            entries=[
                {
                    "domain": "lifestyle",
                    "key": "sleep_duration_hours",
                    "value": 6.0,
                    "confidence": 0.8,
                    "source": "manual",
                }
            ]
        ),
        headers=_auth(u.id),
    )
    db.refresh(summary)
    assert summary.status == "stale"


def test_memory_consent_api_grant_get_revoke(client, db):
    u = _user(db, "i6-consent-api")
    get0 = client.get("/memory/consent", headers=_auth(u.id))
    assert get0.status_code == 200
    assert get0.json().get("data", {}).get("granted") is False

    grant = client.post("/memory/consent/grant", headers=_auth(u.id))
    assert grant.status_code == 200
    assert grant.json().get("data", {}).get("granted") is True
    assert grant.json().get("data", {}).get("permissions", {}).get("memory.write") is True

    get1 = client.get("/memory/consent", headers=_auth(u.id))
    assert get1.json().get("data", {}).get("granted") is True

    revoke = client.post("/memory/consent/revoke", headers=_auth(u.id))
    assert revoke.status_code == 200
    assert revoke.json().get("data", {}).get("revoked") is True
    assert revoke.json().get("data", {}).get("granted") is False


def test_memory_consent_api_cross_user_isolation(client, db):
    a = _user(db, "i6-iso-a")
    b = _user(db, "i6-iso-b")
    grant_memory_consent(db, a.id, commit=True)
    client.post("/lifestyle/update", json=_lifestyle_body(), headers=_auth(a.id))
    ctx_b = client.get("/lifestyle/context", headers=_auth(b.id))
    assert ctx_b.json().get("data", {}).get("sleep_duration_hours") is None
