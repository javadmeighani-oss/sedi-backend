"""A4 has_user_response projection — existing InteractionEvent ledger only."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import event

from backend.app.core.security import create_access_token
from backend.app.models import InteractionEvent, Notification, User
from backend.app.services.i10.interaction_vocabulary import (
    CanonicalInteractionVerb,
    event_type_for_verb,
)
from backend.app.services.notifications.inbox_projection import (
    USER_RESPONSE_EVENT_TYPES,
    bulk_has_user_response_ids,
    fetch_sent_history_page,
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


def _event(db, user_id: int, notif_id: int, verb: CanonicalInteractionVerb) -> None:
    ev = InteractionEvent(
        user_id=user_id,
        event_type=event_type_for_verb(verb),
        source="notification",
        interaction_channel="text",
        source_notification_id=notif_id,
    )
    db.add(ev)
    db.commit()


def test_user_response_event_types_exclude_read():
    assert event_type_for_verb(CanonicalInteractionVerb.READ) not in USER_RESPONSE_EVENT_TYPES
    for verb in (
        CanonicalInteractionVerb.LIKE,
        CanonicalInteractionVerb.DISLIKE,
        CanonicalInteractionVerb.DISLIKE_REASON,
        CanonicalInteractionVerb.TALK_TO_SEDI,
    ):
        assert event_type_for_verb(verb) in USER_RESPONSE_EVENT_TYPES


def test_has_user_response_false_when_no_event(client, db):
    u = _user(db, "hur_none")
    n = _notif(db, u.id, title="no_event")
    resp = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert resp.status_code == 200
    row = next(x for x in resp.json()["data"]["notifications"] if x["id"] == n.id)
    assert row["has_user_response"] is False
    assert row["is_read"] is False


def test_has_user_response_false_when_read_only(client, db):
    u = _user(db, "hur_read")
    n = _notif(db, u.id, title="read_only", is_read=True)
    _event(db, u.id, n.id, CanonicalInteractionVerb.READ)
    resp = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert resp.status_code == 200
    row = next(x for x in resp.json()["data"]["notifications"] if x["id"] == n.id)
    assert row["is_read"] is True
    assert row["has_user_response"] is False


def test_has_user_response_true_for_like(client, db):
    u = _user(db, "hur_like")
    n = _notif(db, u.id, title="liked", is_read=True)
    _event(db, u.id, n.id, CanonicalInteractionVerb.LIKE)
    resp = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    row = next(x for x in resp.json()["data"]["notifications"] if x["id"] == n.id)
    assert row["has_user_response"] is True


def test_has_user_response_true_for_dislike(client, db):
    u = _user(db, "hur_dislike")
    n = _notif(db, u.id, title="disliked", is_read=True)
    _event(db, u.id, n.id, CanonicalInteractionVerb.DISLIKE)
    resp = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    row = next(x for x in resp.json()["data"]["notifications"] if x["id"] == n.id)
    assert row["has_user_response"] is True


def test_has_user_response_true_for_talk_to_sedi(client, db):
    u = _user(db, "hur_talk")
    n = _notif(db, u.id, title="talked", is_read=True)
    _event(db, u.id, n.id, CanonicalInteractionVerb.TALK_TO_SEDI)
    resp = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    row = next(x for x in resp.json()["data"]["notifications"] if x["id"] == n.id)
    assert row["has_user_response"] is True


def test_bulk_page_projection_no_n_plus_one(client, db):
    u = _user(db, "hur_bulk")
    now = datetime.utcnow()
    items = []
    for i in range(8):
        n = _notif(db, u.id, title=f"bulk_{i}", sent_at=now, is_read=(i % 2 == 0))
        items.append(n)
        if i % 2 == 0:
            _event(db, u.id, n.id, CanonicalInteractionVerb.LIKE)

    engine = db.get_bind()
    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(str(statement))

    event.listen(engine, "before_cursor_execute", _count)
    try:
        page = fetch_sent_history_page(db, user_id=u.id, limit=20)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    responded = page["has_user_response_ids"]
    assert len(responded) == 4
    for i, n in enumerate(items):
        if i % 2 == 0:
            assert n.id in responded
        else:
            assert n.id not in responded

    # One bulk DISTINCT projection query — never one SELECT per row.
    interaction_selects = [
        s
        for s in statements
        if "interaction_events" in s.lower() and s.lstrip().upper().startswith("SELECT")
    ]
    assert len(interaction_selects) == 1

    # HTTP path also projects the flag for the page.
    resp = client.get(
        f"/notifications/?user_id={u.id}&limit=20",
        headers=_auth_header(u.id),
    )
    assert resp.status_code == 200
    by_id = {x["id"]: x["has_user_response"] for x in resp.json()["data"]["notifications"]}
    for i, n in enumerate(items):
        assert by_id[n.id] is (i % 2 == 0)


def test_bulk_helper_empty_ids(db):
    assert bulk_has_user_response_ids(db, user_id=1, notification_ids=[]) == set()
