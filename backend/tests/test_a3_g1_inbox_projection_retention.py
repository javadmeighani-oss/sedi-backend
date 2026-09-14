"""A3 G1 sent-history projection + retention FK foundation tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import (
    I10NotificationDecision,
    InteractionEvent,
    Notification,
    NotificationFeedback,
    User,
)
from backend.app.services.notifications.inbox_projection import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    encode_inbox_cursor,
    fetch_sent_history_page,
)
from backend.app.services.notifications.retention import (
    FULL_NOTIFICATION_CONTENT_RETENTION_DAYS,
    I10_DECISION_AUDIT_RETENTION_DAYS,
    prune_expired_notification_content,
    retention_cutoffs,
)


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _user(db, name: str) -> User:
    u = User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _notif(db, user_id: int, **overrides) -> Notification:
    now = datetime.utcnow()
    base = dict(
        user_id=user_id,
        type="connection_ping",
        title="Hello",
        body="Body",
        priority="normal",
        is_read=False,
        is_sent=True,
        sent_at=now,
        status="sent",
        created_at=now,
        channel="engagement",
    )
    base.update(overrides)
    n = Notification(**base)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_sent_appears_queued_future_failed_hidden(client, db):
    u = _user(db, "proj_hide")
    now = datetime.utcnow()
    sent = _notif(db, u.id, title="sent", sent_at=now, is_sent=True, status="sent")
    _notif(
        db,
        u.id,
        title="queued",
        is_sent=False,
        sent_at=None,
        status="queued",
        scheduled_for=now + timedelta(hours=2),
    )
    _notif(
        db,
        u.id,
        title="failed",
        is_sent=False,
        sent_at=None,
        status="failed",
    )
    _notif(
        db,
        u.id,
        title="old_sent",
        is_sent=True,
        sent_at=now - timedelta(days=200),
        created_at=now - timedelta(days=200),
        status="sent",
    )

    resp = client.get(f"/notifications/?user_id={u.id}&limit=20", headers=_auth_header(u.id))
    assert resp.status_code == 200
    data = resp.json()["data"]
    ids = [n["id"] for n in data["notifications"]]
    titles = [n["title"] for n in data["notifications"]]
    assert sent.id in ids
    assert "sent" in titles
    assert "queued" not in titles
    assert "failed" not in titles
    assert "old_sent" not in titles
    assert data["unread_count"] == 1


def test_order_sent_at_then_id_and_cursor_pagination(client, db):
    u = _user(db, "proj_page")
    t0 = datetime.utcnow().replace(microsecond=0)
    rows = []
    for i in range(25):
        rows.append(
            _notif(
                db,
                u.id,
                title=f"n{i}",
                sent_at=t0 - timedelta(seconds=i),
                created_at=t0 - timedelta(seconds=i),
            )
        )

    first = client.get(
        f"/notifications/?user_id={u.id}&limit=20",
        headers=_auth_header(u.id),
    ).json()["data"]
    assert first["limit"] == DEFAULT_PAGE_SIZE
    assert len(first["notifications"]) == 20
    assert first["has_more"] is True
    assert first["next_cursor"]
    ids1 = [n["id"] for n in first["notifications"]]
    assert ids1 == [r.id for r in rows[:20]]

    second = client.get(
        f"/notifications/?user_id={u.id}&limit=20&cursor={first['next_cursor']}",
        headers=_auth_header(u.id),
    ).json()["data"]
    ids2 = [n["id"] for n in second["notifications"]]
    assert ids2 == [r.id for r in rows[20:]]
    assert set(ids1).isdisjoint(set(ids2))
    assert second["has_more"] is False

    # Max allowed request is 50 (FastAPI validates before clamp)
    clamped = client.get(
        f"/notifications/?user_id={u.id}&limit=50",
        headers=_auth_header(u.id),
    ).json()["data"]
    assert clamped["limit"] == MAX_PAGE_SIZE
    rejected = client.get(
        f"/notifications/?user_id={u.id}&limit=999",
        headers=_auth_header(u.id),
    )
    assert rejected.status_code == 422


def test_tie_break_same_sent_at_uses_id_desc(db):
    u = _user(db, "tie")
    ts = datetime.utcnow().replace(microsecond=0)
    a = _notif(db, u.id, title="a", sent_at=ts)
    b = _notif(db, u.id, title="b", sent_at=ts)
    page = fetch_sent_history_page(db, user_id=u.id, limit=10)
    ids = [n.id for n in page["notifications"]]
    assert ids[0] == max(a.id, b.id)
    assert ids[1] == min(a.id, b.id)


def test_unread_excludes_unsent_and_failed(client, db):
    u = _user(db, "unread")
    now = datetime.utcnow()
    _notif(db, u.id, is_sent=True, sent_at=now, is_read=False, status="sent")
    _notif(db, u.id, is_sent=False, sent_at=None, is_read=False, status="queued")
    _notif(db, u.id, is_sent=False, sent_at=None, is_read=False, status="failed")
    resp = client.get(f"/notifications/unread?user_id={u.id}", headers=_auth_header(u.id))
    data = resp.json()["data"]
    assert data["unread_count"] == 1
    assert data["count"] == 1


def test_auth_isolation(client, db):
    a = _user(db, "iso_a")
    b = _user(db, "iso_b")
    _notif(db, a.id, title="private-a")
    resp = client.get(f"/notifications/?user_id={a.id}", headers=_auth_header(b.id))
    assert resp.status_code == 403


def test_retention_fk_safe_delete_content_and_decisions(db):
    u = _user(db, "ret")
    old = datetime.utcnow() - timedelta(days=FULL_NOTIFICATION_CONTENT_RETENTION_DAYS + 5)
    n = _notif(db, u.id, sent_at=old, created_at=old, is_sent=True, status="sent")
    fb = NotificationFeedback(
        notification_id=n.id, user_id=u.id, action="like", created_at=old
    )
    db.add(fb)
    ev = InteractionEvent(
        user_id=u.id,
        event_type="notification_like",
        source="notification",
        interaction_channel="text",
        source_notification_id=n.id,
        created_at=old,
    )
    db.add(ev)
    dec_old = I10NotificationDecision(
        candidate_key=f"old-{n.id}",
        recipient_user_id=u.id,
        source_owner="test",
        source_type="test",
        source_id="1",
        decision="SEND",
        reason_code="TEST",
        notification_id=n.id,
        created_at=datetime.utcnow()
        - timedelta(days=I10_DECISION_AUDIT_RETENTION_DAYS + 3),
        updated_at=datetime.utcnow(),
    )
    db.add(dec_old)
    db.commit()
    notif_id = n.id
    ev_id = ev.id

    result = prune_expired_notification_content(
        db, dry_run=False, force=True, batch_size=50
    )
    assert result.notifications_deleted >= 1
    assert result.decisions_deleted >= 1
    assert db.query(Notification).filter(Notification.id == notif_id).first() is None
    assert (
        db.query(NotificationFeedback)
        .filter(NotificationFeedback.notification_id == notif_id)
        .count()
        == 0
    )
    # interaction SET NULL, not hard-deleted
    remaining = db.query(InteractionEvent).filter(InteractionEvent.id == ev_id).first()
    assert remaining is not None
    assert remaining.source_notification_id is None


def test_retention_cutoffs_policy_values():
    cuts = retention_cutoffs(datetime(2026, 9, 13))
    assert (datetime(2026, 9, 13) - cuts.content_cutoff).days == FULL_NOTIFICATION_CONTENT_RETENTION_DAYS
    assert (datetime(2026, 9, 13) - cuts.decision_cutoff).days == I10_DECISION_AUDIT_RETENTION_DAYS


def test_retention_disabled_without_force(db):
    result = prune_expired_notification_content(db, dry_run=False, force=False)
    assert result.enabled is False
    assert result.notifications_deleted == 0


def test_fcm_message_includes_channel_and_sound():
    from backend.app.services.notifications.fcm_client import _build_fcm_message

    msg = _build_fcm_message(
        token="x" * 120,
        title="t",
        body="b",
        data={
            "channel_id": "health_alert_v2",
            "sound": "sedi_alarm",
            "ios_sound": "sedi_alarm.wav",
            "play_sound": "true",
        },
        android_priority="high",
    )
    android_notif = msg["message"]["android"]["notification"]
    assert android_notif["channel_id"] == "health_alert_v2"
    assert android_notif["sound"] == "sedi_alarm"
    assert msg["message"]["apns"]["payload"]["aps"]["sound"] == "sedi_alarm.wav"


def test_encode_cursor_roundtrip():
    ts = datetime(2026, 1, 2, 3, 4, 5)
    cur = encode_inbox_cursor(sent_at=ts, notification_id=99)
    from backend.app.services.notifications.inbox_projection import decode_inbox_cursor

    back_ts, back_id = decode_inbox_cursor(cur)
    assert back_id == 99
    assert back_ts == ts
