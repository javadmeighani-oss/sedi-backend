"""A4 inbox visibility (10-day window) + hide-from-inbox foundation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.core.security import create_access_token
from backend.app.models import InteractionEvent, Notification, NotificationFeedback, User
from backend.app.services.notifications.inbox_projection import (
    USER_VISIBLE_HISTORY_DAYS,
    fetch_sent_history_page,
    visible_cutoff,
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
        provider="fcm",
        created_at=now,
        channel="engagement",
        inbox_hidden_at=None,
    )
    base.update(overrides)
    n = Notification(**base)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_visible_days_default_is_10():
    assert USER_VISIBLE_HISTORY_DAYS == 10


def test_ten_day_inclusive_boundary_and_older_excluded(client, db):
    u = _user(db, "a4_bound")
    now = datetime.utcnow().replace(microsecond=0)
    cutoff = visible_cutoff(now)
    assert cutoff == now - timedelta(days=10)

    at_boundary = _notif(
        db, u.id, title="at_boundary", sent_at=cutoff, created_at=cutoff
    )
    just_inside = _notif(
        db,
        u.id,
        title="just_inside",
        sent_at=cutoff + timedelta(seconds=1),
        created_at=cutoff + timedelta(seconds=1),
    )
    just_outside = _notif(
        db,
        u.id,
        title="just_outside",
        sent_at=cutoff - timedelta(seconds=1),
        created_at=cutoff - timedelta(seconds=1),
    )
    older = _notif(
        db,
        u.id,
        title="older_11d",
        sent_at=now - timedelta(days=11),
        created_at=now - timedelta(days=11),
    )
    clearly_visible = _notif(
        db,
        u.id,
        title="clearly_visible_9d",
        sent_at=now - timedelta(days=9),
        created_at=now - timedelta(days=9),
    )

    # Inclusive boundary uses a pinned `now` (same clock as projection).
    page = fetch_sent_history_page(db, user_id=u.id, limit=50, now=now)
    ids = [n.id for n in page["notifications"]]
    assert at_boundary.id in ids
    assert just_inside.id in ids
    assert clearly_visible.id in ids
    assert just_outside.id not in ids
    assert older.id not in ids

    # Rows older than window remain in DB (projection only).
    assert db.query(Notification).filter(Notification.id == older.id).first() is not None
    assert (
        db.query(Notification).filter(Notification.id == just_outside.id).first()
        is not None
    )

    # HTTP path uses live utcnow — assert stable inside/outside points only.
    resp = client.get(
        f"/notifications/?user_id={u.id}&limit=50",
        headers=_auth_header(u.id),
    )
    assert resp.status_code == 200
    api_ids = [n["id"] for n in resp.json()["data"]["notifications"]]
    assert clearly_visible.id in api_ids
    assert older.id not in api_ids


def test_hidden_row_excluded_from_list_and_unread_count(client, db):
    u = _user(db, "a4_hide_unread")
    now = datetime.utcnow()
    visible = _notif(db, u.id, title="visible", sent_at=now, is_read=False)
    hidden_unread = _notif(db, u.id, title="hidden_unread", sent_at=now, is_read=False)
    hidden_unread.inbox_hidden_at = datetime.now(timezone.utc)
    db.commit()

    list_data = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    ).json()["data"]
    unread_data = client.get(
        f"/notifications/unread?user_id={u.id}",
        headers=_auth_header(u.id),
    ).json()["data"]

    list_ids = [n["id"] for n in list_data["notifications"]]
    unread_ids = [n["id"] for n in unread_data["notifications"]]
    assert visible.id in list_ids
    assert hidden_unread.id not in list_ids
    assert hidden_unread.id not in unread_ids
    assert list_data["unread_count"] == 1
    assert unread_data["unread_count"] == 1


def test_hide_idempotent_preserves_row_feedback_interaction_and_is_read(client, db):
    u = _user(db, "a4_hide_preserve")
    now = datetime.utcnow()
    n = _notif(db, u.id, title="to_hide", sent_at=now, is_read=False)
    fb = NotificationFeedback(
        notification_id=n.id, user_id=u.id, action="like", meta_json="{}"
    )
    db.add(fb)
    ev = InteractionEvent(
        user_id=u.id,
        event_type="notification_like",
        source="notification",
        interaction_channel="text",
        source_notification_id=n.id,
    )
    db.add(ev)
    db.commit()
    fb_id = fb.id
    ev_id = ev.id
    notif_id = n.id

    headers = _auth_header(u.id)
    first = client.post(
        "/notifications/inbox/hide",
        headers=headers,
        json={"notification_ids": [notif_id, notif_id]},
    )
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert first.json()["data"]["newly_hidden"] == 1
    assert first.json()["data"]["already_hidden"] == 0
    assert first.json()["data"]["count"] == 1

    row = db.query(Notification).filter(Notification.id == notif_id).first()
    assert row is not None
    assert row.inbox_hidden_at is not None
    assert row.is_read is False
    first_hidden_at = row.inbox_hidden_at

    second = client.post(
        "/notifications/inbox/hide",
        headers=headers,
        json={"notification_ids": [notif_id]},
    )
    assert second.status_code == 200
    assert second.json()["data"]["newly_hidden"] == 0
    assert second.json()["data"]["already_hidden"] == 1

    db.refresh(row)
    assert row.inbox_hidden_at == first_hidden_at
    assert row.is_read is False
    assert db.query(Notification).filter(Notification.id == notif_id).count() == 1
    assert (
        db.query(NotificationFeedback).filter(NotificationFeedback.id == fb_id).count()
        == 1
    )
    rem_ev = db.query(InteractionEvent).filter(InteractionEvent.id == ev_id).first()
    assert rem_ev is not None
    assert rem_ev.source_notification_id == notif_id

    # No fake READ interaction invented by hide.
    read_events = (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.source_notification_id == notif_id,
            InteractionEvent.event_type == "notification_read",
        )
        .count()
    )
    assert read_events == 0


def test_hide_owner_only_and_mixed_owner_fail_closed(client, db):
    owner = _user(db, "a4_owner")
    other = _user(db, "a4_other")
    now = datetime.utcnow()
    mine = _notif(db, owner.id, title="mine", sent_at=now, is_read=False)
    theirs = _notif(db, other.id, title="theirs", sent_at=now, is_read=False)

    # Cross-user alone
    alone = client.post(
        "/notifications/inbox/hide",
        headers=_auth_header(owner.id),
        json={"notification_ids": [theirs.id]},
    )
    assert alone.status_code == 403
    db.refresh(theirs)
    assert theirs.inbox_hidden_at is None

    # Mixed: fail-closed, no partial mutation on owner row
    mixed = client.post(
        "/notifications/inbox/hide",
        headers=_auth_header(owner.id),
        json={"notification_ids": [mine.id, theirs.id]},
    )
    assert mixed.status_code == 403
    db.refresh(mine)
    db.refresh(theirs)
    assert mine.inbox_hidden_at is None
    assert theirs.inbox_hidden_at is None
    assert mine.is_read is False


def test_pagination_cannot_surface_hidden_rows(client, db):
    u = _user(db, "a4_page_hide")
    t0 = datetime.utcnow().replace(microsecond=0)
    rows = []
    for i in range(12):
        rows.append(
            _notif(
                db,
                u.id,
                title=f"n{i}",
                sent_at=t0 - timedelta(seconds=i),
                created_at=t0 - timedelta(seconds=i),
            )
        )
    # Hide every other row
    hide_ids = [rows[i].id for i in range(0, 12, 2)]
    resp = client.post(
        "/notifications/inbox/hide",
        headers=_auth_header(u.id),
        json={"notification_ids": hide_ids},
    )
    assert resp.status_code == 200

    first = client.get(
        f"/notifications/?user_id={u.id}&limit=20",
        headers=_auth_header(u.id),
    ).json()["data"]
    ids = [n["id"] for n in first["notifications"]]
    assert set(ids).isdisjoint(set(hide_ids))
    assert set(ids) == {rows[i].id for i in range(1, 12, 2)}

    # Cursor over remaining visible set still excludes hidden
    if first["next_cursor"]:
        second = client.get(
            f"/notifications/?user_id={u.id}&limit=20&cursor={first['next_cursor']}",
            headers=_auth_header(u.id),
        ).json()["data"]
        assert set(n["id"] for n in second["notifications"]).isdisjoint(set(hide_ids))


def test_hide_requires_auth(client, db):
    u = _user(db, "a4_auth")
    n = _notif(db, u.id)
    resp = client.post(
        "/notifications/inbox/hide",
        json={"notification_ids": [n.id]},
    )
    assert resp.status_code in (401, 403)
