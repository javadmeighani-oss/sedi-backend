"""A3 session/open notification-origin continuity seam tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.app.core.security import create_access_token
from backend.app.models import Memory, Notification, User
from backend.app.services.i10.policy_types import I10SemanticFamily


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _user(db, name: str, *, lang: str = "en", intro: bool = True) -> User:
    row = User(name=name, secret_key="sess-open-n", preferred_language=lang)
    if intro:
        row.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _notif(db, user: User, *, family: str, body: str = "SAFE_LOCK_BODY", **extra) -> Notification:
    n = Notification(
        user_id=user.id,
        type="companion",
        title="Sedi",
        body=body,
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
        semantic_family=family,
        **extra,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_session_open_normal_body_unchanged(client, db):
    u = _user(db, "NormalOpen")
    before = db.query(Memory).filter(Memory.user_id == u.id).count()
    r = client.post("/interact/session/open", headers=_auth(u.id), json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("first_intro") is False
    assert not body.get("continued_from_notification")
    assert body.get("source_notification_id") is None
    assert db.query(Memory).filter(Memory.user_id == u.id).count() == before


def test_session_open_owned_presence_contextual_opener(client, db, monkeypatch):
    u = _user(db, "جواد", lang="fa")
    n = _notif(
        db,
        u,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
        body="LEAK_RAW_BODY_SHOULD_NOT_APPEAR",
        context_json=json.dumps({"diagnosis": "diabetes", "dose": "500mg"}),
    )
    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_privacy_safe_recent_topic_label",
        lambda *_a, **_k: "activity_plan",
    )
    # Recent Memory would block ordinary 12h opener — notification origin must bypass.
    mem = Memory(
        user_id=u.id,
        user_message="recent",
        sedi_response="ok",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=30),
    )
    db.add(mem)
    db.commit()
    before = db.query(Memory).filter(Memory.user_id == u.id).count()

    r = client.post(
        "/interact/session/open",
        headers=_auth(u.id),
        json={"source_notification_id": n.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    msg = body.get("message") or ""
    assert body.get("continued_from_notification") is True
    assert body.get("source_notification_id") == n.id
    assert body.get("first_intro") is False
    assert "فعالیت" in msg or "ادامه" in msg
    assert "LEAK_RAW_BODY_SHOULD_NOT_APPEAR" not in msg
    assert "diabetes" not in msg.lower()
    assert "500mg" not in msg
    assert db.query(Memory).filter(Memory.user_id == u.id).count() == before


def test_session_open_presence_sensitive_topic_generic(client, db, monkeypatch):
    u = _user(db, "SensTopic", lang="en")
    n = _notif(
        db,
        u,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
        body="LOCKSCREEN_SECRET_BODY",
        context_json=json.dumps({"raw_memory": "SECRET_DIAGNOSIS_PHRASE"}),
    )
    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_privacy_safe_recent_topic_label",
        lambda *_a, **_k: None,
    )
    r = client.post(
        "/interact/session/open",
        headers=_auth(u.id),
        json={"source_notification_id": n.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    msg = (body.get("message") or "").lower()
    assert body.get("continued_from_notification") is True
    assert "continue" in msg or "left off" in msg
    assert "lockscreen_secret_body" not in msg
    assert "secret_diagnosis_phrase" not in msg
    assert "diabetes" not in msg


def test_session_open_other_family_ack_opener(client, db):
    u = _user(db, "OtherFam", lang="en")
    n = _notif(
        db,
        u,
        family=I10SemanticFamily.DAILY_WELLNESS_DIGEST.value,
        body="DIGEST_RAW_SHOULD_NOT_LEAK",
    )
    r = client.post(
        "/interact/session/open",
        headers=_auth(u.id),
        json={"source_notification_id": n.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    msg = body.get("message") or ""
    assert body.get("continued_from_notification") is True
    assert body.get("source_notification_id") == n.id
    # A4: DAILY_WELLNESS_DIGEST gets calm family-specific opener (no raw body).
    assert "daily" in msg.lower() and "sedi" in msg.lower()
    assert "DIGEST_RAW_SHOULD_NOT_LEAK" not in msg


def test_session_open_foreign_notification_403(client, db):
    owner = _user(db, "OwnerN")
    stranger = _user(db, "StrangerN")
    n = _notif(db, owner, family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value)
    r = client.post(
        "/interact/session/open",
        headers=_auth(stranger.id),
        json={"source_notification_id": n.id},
    )
    assert r.status_code == 403


def test_session_open_missing_notification_404(client, db):
    u = _user(db, "MissingN")
    r = client.post(
        "/interact/session/open",
        headers=_auth(u.id),
        json={"source_notification_id": 99999999},
    )
    assert r.status_code == 404


def test_session_open_intro_priority_over_notification(client, db):
    u = _user(db, "IntroFirst", lang="fa", intro=False)
    n = _notif(db, u, family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value)
    before = db.query(Memory).filter(Memory.user_id == u.id).count()
    r = client.post(
        "/interact/session/open",
        headers=_auth(u.id),
        json={"source_notification_id": n.id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("first_intro") is True
    assert "صدی" in (body.get("message") or "") or "Sedi" in (body.get("message") or "")
    assert body.get("continued_from_notification") is True
    assert body.get("source_notification_id") == n.id
    assert db.query(Memory).filter(Memory.user_id == u.id).count() == before
