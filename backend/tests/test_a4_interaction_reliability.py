"""A4 P2A — interaction reliability: read-on-success + sequential retry idempotency."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import InteractionEvent, Notification, NotificationFeedback, User
from backend.app.services.i10.interaction_vocabulary import (
    CanonicalInteractionVerb,
    assert_generic_verb_cannot_complete_domain,
)
from backend.app.services.i10.policy_types import I10SemanticFamily


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


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
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        sent_at=now,
        status="sent",
        provider="fcm",
        created_at=now,
        channel="engagement",
    )
    base.update(overrides)
    n = Notification(**base)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _feedback(client, user: User, notif_id: int, payload: dict):
    return client.post(
        f"/notifications/{notif_id}/feedback",
        json=payload,
        headers=_auth(user.id),
    )


def _action_events(db, notif_id: int, event_type: str):
    return (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.source_notification_id == notif_id,
            InteractionEvent.event_type == event_type,
        )
        .all()
    )


def _feedback_rows(db, notif_id: int, action: str):
    return (
        db.query(NotificationFeedback)
        .filter(
            NotificationFeedback.notification_id == notif_id,
            NotificationFeedback.action == action,
        )
        .all()
    )


@pytest.mark.parametrize(
    "payload,action,event_type",
    [
        ({"action": "like"}, "like", "notification_like"),
        ({"action": "dislike"}, "dislike", "notification_dislike"),
        (
            {"action": "dislike", "reason": "irrelevant"},
            "dislike",
            "notification_dislike_reason",
        ),
        ({"action": "open_chat"}, "open_chat", "notification_open_chat"),
    ],
)
def test_canonical_success_marks_read_and_one_read_event(
    client, db, payload, action, event_type
):
    u = _user(db, f"p2a-{action}-{event_type}")
    n = _notif(db, u.id)
    r = _feedback(client, u, n.id, payload)
    assert r.status_code == 200
    db.refresh(n)
    assert n.is_read is True
    assert len(_action_events(db, n.id, event_type)) == 1
    assert len(_action_events(db, n.id, "notification_read")) == 1
    assert len(_feedback_rows(db, n.id, action)) == 1


def test_already_read_no_duplicate_read_event(client, db):
    u = _user(db, "p2a-already-read")
    n = _notif(db, u.id, is_read=True)
    r = _feedback(client, u, n.id, {"action": "like"})
    assert r.status_code == 200
    db.refresh(n)
    assert n.is_read is True
    assert len(_action_events(db, n.id, "notification_like")) == 1
    assert len(_action_events(db, n.id, "notification_read")) == 0


def test_retry_same_action_no_duplicate_feedback_or_event(client, db):
    u = _user(db, "p2a-retry")
    n = _notif(db, u.id)
    r1 = _feedback(client, u, n.id, {"action": "like"})
    r2 = _feedback(client, u, n.id, {"action": "like"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(_feedback_rows(db, n.id, "like")) == 1
    assert len(_action_events(db, n.id, "notification_like")) == 1
    assert len(_action_events(db, n.id, "notification_read")) == 1
    db.refresh(n)
    assert n.is_read is True


def test_failed_interaction_leaves_unread(db):
    from backend.app.routers.notifications import submit_notification_feedback

    u = _user(db, "p2a-fail")
    n = _notif(db, u.id)
    notif_id = n.id
    with patch(
        "backend.app.services.i10.interaction_recorder.create_interaction_event",
        side_effect=RuntimeError("forced_ledger_failure"),
    ):
        with pytest.raises(RuntimeError, match="forced_ledger_failure"):
            submit_notification_feedback(
                notification_id=notif_id,
                payload={"action": "like"},
                auth_user=u,
                user_id=None,
                db=db,
            )
    db.rollback()
    n2 = db.query(Notification).filter(Notification.id == notif_id).one()
    assert n2.is_read is False
    assert len(_action_events(db, notif_id, "notification_like")) == 0
    assert len(_action_events(db, notif_id, "notification_read")) == 0
    assert len(_feedback_rows(db, notif_id, "like")) == 0


def test_dismiss_does_not_mark_read(client, db):
    u = _user(db, "p2a-dismiss")
    n = _notif(db, u.id)
    r = _feedback(client, u, n.id, {"action": "dismissed"})
    assert r.status_code == 200
    db.refresh(n)
    assert n.is_read is False
    assert len(_action_events(db, n.id, "notification_read")) == 0


def test_ownership_unchanged(client, db):
    owner = _user(db, "p2a-owner")
    other = _user(db, "p2a-other")
    n = _notif(db, owner.id)
    r = client.post(
        f"/notifications/{n.id}/feedback",
        json={"action": "like"},
        headers=_auth(other.id),
    )
    assert r.status_code == 403
    db.refresh(n)
    assert n.is_read is False


def test_generic_actions_cannot_complete_governed_domains(db):
    u = _user(db, "p2a-domain")
    n = _notif(
        db,
        u.id,
        semantic_family=I10SemanticFamily.MEDICATION_DUE.value,
    )
    for verb in (
        CanonicalInteractionVerb.LIKE,
        CanonicalInteractionVerb.DISLIKE,
        CanonicalInteractionVerb.DISLIKE_REASON,
        CanonicalInteractionVerb.TALK_TO_SEDI,
        CanonicalInteractionVerb.NOT_NOW,
    ):
        assert_generic_verb_cannot_complete_domain(n, verb) is None
    with pytest.raises(ValueError, match="done_requires_domain_authority"):
        assert_generic_verb_cannot_complete_domain(n, CanonicalInteractionVerb.DONE)


def test_talk_to_sedi_writes_no_memory(client, db):
    from backend.app.models import Memory

    u = _user(db, "p2a-talk-mem")
    n = _notif(db, u.id)
    before = db.query(Memory).filter(Memory.user_id == u.id).count()
    r = _feedback(client, u, n.id, {"action": "open_chat"})
    assert r.status_code == 200
    after = db.query(Memory).filter(Memory.user_id == u.id).count()
    assert after == before
    db.refresh(n)
    assert n.is_read is True
