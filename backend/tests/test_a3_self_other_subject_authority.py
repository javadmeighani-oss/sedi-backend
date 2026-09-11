"""Targeted A3 SELF/OTHER HealthSubject authority foundation (Postgres)."""

from __future__ import annotations

import os

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app.core.security import create_access_token
from backend.app.models import AccountHealthSubjectAccess, HealthSubject, User
from backend.app.services.i9.health_subject_service import (
    ensure_self_subject_for_account,
    require_account_subject_access,
)
from backend.app.services.managed_person_service import create_managed_person


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _user(db, phone: str, name: str = "U") -> User:
    u = User(name=name, secret_key="t", preferred_language="en", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    ensure_self_subject_for_account(db, u.id)
    db.commit()
    return u


def test_a_self_only_list(client, db):
    u = _user(db, "+16660000001")
    r = client.get("/health-subjects", headers=_auth(u.id))
    assert r.status_code == 200
    items = (r.json().get("data") or {}).get("health_subjects") or []
    assert len(items) == 1
    assert items[0]["subject_kind"] == "self"
    assert items[0]["access_role"] == "SELF"


def test_b_self_plus_one_other(client, db):
    u = _user(db, "+16660000002")
    other, _ = create_managed_person(
        db, account_user_id=u.id, display_name="Alex", access_role="MANAGER"
    )
    r = client.get("/health-subjects", headers=_auth(u.id))
    items = (r.json().get("data") or {}).get("health_subjects") or []
    kinds = {i["subject_kind"] for i in items}
    assert "self" in kinds and "managed" in kinds
    assert any(i["health_subject_id"] == other.id for i in items)


def test_c_multiple_other(client, db):
    u = _user(db, "+16660000003")
    create_managed_person(db, account_user_id=u.id, display_name="A", access_role="MANAGER")
    create_managed_person(db, account_user_id=u.id, display_name="B", access_role="CAREGIVER")
    items = (
        client.get("/health-subjects", headers=_auth(u.id)).json().get("data") or {}
    ).get("health_subjects") or []
    assert sum(1 for i in items if i["subject_kind"] == "managed") >= 2


def test_d_revoked_other_denied(client, db):
    u = _user(db, "+16660000004")
    other, _ = create_managed_person(
        db, account_user_id=u.id, display_name="Rev", access_role="MANAGER"
    )
    row = (
        db.query(AccountHealthSubjectAccess)
        .filter(
            AccountHealthSubjectAccess.account_user_id == u.id,
            AccountHealthSubjectAccess.health_subject_id == other.id,
        )
        .first()
    )
    from datetime import datetime, timezone

    row.is_active = False
    row.revoked_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    r = client.get(f"/health-subjects/{other.id}", headers=_auth(u.id))
    assert r.status_code == 403


def test_e_cross_account_denied(client, db):
    a = _user(db, "+16660000005", "A")
    b = _user(db, "+16660000006", "B")
    other, _ = create_managed_person(
        db, account_user_id=a.id, display_name="OnlyA", access_role="MANAGER"
    )
    r = client.get(f"/health-subjects/{other.id}", headers=_auth(b.id))
    assert r.status_code == 403


def test_f_chat_self_ok_other_blocked(client, db):
    u = _user(db, "+16660000007")
    self_hs = ensure_self_subject_for_account(db, u.id)
    db.commit()
    other, _ = create_managed_person(
        db, account_user_id=u.id, display_name="Other", access_role="MANAGER"
    )
    # SELF chat allowed (may hit orchestration; accept 200)
    r_self = client.post(
        "/interact/chat",
        json={"message": "hello timezone check", "health_subject_id": self_hs.id},
        headers=_auth(u.id),
    )
    # Orchestration/upstream may 500/502 in CI (no real OpenAI key); not auth deny.
    assert r_self.status_code in (200, 500, 502)
    assert r_self.status_code != 403
    r_other = client.post(
        "/interact/chat",
        json={"message": "hello", "health_subject_id": other.id},
        headers=_auth(u.id),
    )
    assert r_other.status_code == 200
    body = r_other.json()
    assert body.get("other_chat_blocked") is True
    assert body.get("health_subject_id") == other.id


def test_g_unauthorized_subject_chat_403(client, db):
    a = _user(db, "+16660000008")
    b = _user(db, "+16660000009")
    other, _ = create_managed_person(
        db, account_user_id=a.id, display_name="X", access_role="MANAGER"
    )
    r = client.post(
        "/interact/chat",
        json={"message": "hi", "health_subject_id": other.id},
        headers=_auth(b.id),
    )
    assert r.status_code == 403


def test_h_i8_subject_access(client, db):
    u = _user(db, "+16660000010")
    other, _ = create_managed_person(
        db, account_user_id=u.id, display_name="I8", access_role="MANAGER"
    )
    r = client.post(
        "/i8/actions/generate",
        json={
            "request": "suggest a walk",
            "domain": "exercise",
            "persist": False,
            "health_subject_id": other.id,
        },
        headers=_auth(u.id),
    )
    assert r.status_code == 200
    # May be SUBJECT_ACCESS_DENIED only if AHSA broken; expect ok result or blocked status not 403 HTTP
    payload = r.json()
    assert payload.get("ok") is True


def test_i_lifestyle_other_fail_closed(client, db):
    u = _user(db, "+16660000011")
    other, _ = create_managed_person(
        db, account_user_id=u.id, display_name="Life", access_role="MANAGER"
    )
    r = client.get(
        f"/lifestyle/summary?health_subject_id={other.id}&lang=en",
        headers=_auth(u.id),
    )
    assert r.status_code == 409


def test_j_mother_als_fixture_not_architecture(client, db):
    """Fixture display_name=Mother + condition ALS does not create Mother-specific access."""
    u = _user(db, "+16660000012")
    other, _ = create_managed_person(
        db, account_user_id=u.id, display_name="Mother", access_role="MANAGER"
    )
    assert other.display_name == "Mother"
    # Access is AHSA-based, not display_name
    require_account_subject_access(db, u.id, other.id)
    stranger = _user(db, "+16660000013")
    r = client.get(f"/health-subjects/{other.id}", headers=_auth(stranger.id))
    assert r.status_code == 403


def test_devices_carry_health_subject_id_field(client, db):
    u = _user(db, "+16660000014")
    r = client.get("/devices", headers=_auth(u.id))
    assert r.status_code == 200
    data = r.json().get("data") or {}
    assert "devices" in data
