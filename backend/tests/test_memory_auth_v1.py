"""JWT is required for user-facing memory endpoints (Phase 1E-a)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.core.security import create_access_token
from backend.app.models import DailyMemorySummary, Memory, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _retain_until():
    return datetime.now(timezone.utc) + timedelta(days=30)


def _save_body(**overrides) -> dict:
    body = {
        "summary": "User walked 5000 steps, slept 6 hours.",
        "mood": "neutral",
        "context": "Slight fatigue reported",
    }
    body.update(overrides)
    return body


def test_memory_save_requires_auth(client, db):
    _create_user(db, "MemSaveNoAuth")
    response = client.post("/memory/save", json=_save_body())
    assert response.status_code == 401


def test_memory_latest_requires_auth(client, db):
    _create_user(db, "MemLatestNoAuth")
    response = client.get("/memory/latest")
    assert response.status_code == 401


def test_memory_history_requires_auth(client, db):
    _create_user(db, "MemHistNoAuth")
    response = client.get("/memory/history?group=daily&limit=10")
    assert response.status_code == 401


def test_memory_save_works_without_user_id_in_body(client, db):
    from backend.app.services.i6.consent_service import grant_memory_consent
    from backend.app.models import UserPeriodSummary

    u = _create_user(db, "MemSaveOwner")
    grant_memory_consent(db, u.id, commit=True)
    response = client.post(
        "/memory/save",
        json=_save_body(),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("data", {}).get("memory_id") is not None
    assert data.get("data", {}).get("legacy_dms_write") is False

    row = (
        db.query(UserPeriodSummary)
        .filter(UserPeriodSummary.user_id == u.id, UserPeriodSummary.summary_type == "DAILY")
        .order_by(UserPeriodSummary.id.desc())
        .first()
    )
    assert row is not None
    assert _save_body()["summary"] in (row.narrative_summary or "")


def test_memory_save_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "MemSaveLegacy")
    response = client.post(
        "/memory/save",
        json=_save_body(user_id=u.id + 9999),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_memory_latest_works_without_user_id_query(client, db):
    from backend.app.models import UserPeriodSummary

    u = _create_user(db, "MemLatestOwner")
    now = datetime.now(timezone.utc)
    db.add(
        UserPeriodSummary(
            user_id=u.id,
            summary_type="DAILY",
            period_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=now.replace(hour=23, minute=59, second=59),
            version=1,
            structured_summary_json="{}",
            narrative_summary="Latest summary",
            evidence_range="{}",
            generated_at=now,
            status="active",
            source_complete=False,
        )
    )
    db.commit()

    response = client.get("/memory/latest", headers=_auth_header(u.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert payload.get("data", {}).get("summary") == "Latest summary"
    assert payload.get("data", {}).get("canonical_owner") == "UserPeriodSummary.DAILY"


def test_memory_latest_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "MemLatestLegacy")
    response = client.get(
        f"/memory/latest?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_memory_history_works_without_user_id_query(client, db):
    u = _create_user(db, "MemHistOwner")
    db.add(
        Memory(
            user_id=u.id,
            user_message="hello",
            sedi_response="hi",
            language="en",
            durable_write=True,
            retain_until=_retain_until(),
        )
    )
    db.commit()

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["group"] == "daily"
    assert len(body["items"]) >= 1
    assert body["items"][0]["turns"][0]["user_message"] == "hello"


def test_memory_history_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "MemHistLegacy")
    response = client.get(
        f"/memory/history?user_id={u.id}&group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_memory_latest_cross_user_isolation(client, db):
    user_a = _create_user(db, "MemLatestA")
    user_b = _create_user(db, "MemLatestB")
    db.add(
        DailyMemorySummary(
            user_id=user_b.id,
            summary="User B secret summary",
            mood="tired",
            context="private",
            last_interaction=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get("/memory/latest", headers=_auth_header(user_a.id))
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is False
    assert payload.get("error", {}).get("code") == "NO_MEMORY"


def test_memory_history_cross_user_isolation(client, db):
    user_a = _create_user(db, "MemHistUserA")
    user_b = _create_user(db, "MemHistUserB")
    db.add(
        Memory(
            user_id=user_b.id,
            user_message="secret",
            sedi_response="hidden",
            language="en",
            retain_until=_retain_until(),
        )
    )
    db.commit()

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(user_a.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
