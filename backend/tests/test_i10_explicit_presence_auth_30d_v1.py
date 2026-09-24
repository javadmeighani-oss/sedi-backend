"""AUTH 30-day presence consumes canonical I10 explicit responses only."""

from __future__ import annotations

import os

os.environ["SMS_DISABLED"] = "true"

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from unittest.mock import patch

from backend.app import models
from backend.app.models import User
from backend.app.services.auth_session_policy import (
    AUTH_LOGIN_EVENT_TYPE,
    refresh_allowed_for_presence,
)
from backend.app.services.gate4.interaction_event_service import create_interaction_event
from backend.app.services.i10.interaction_recorder import (
    NOTIFICATION_PRESENCE_EVENT_TYPES,
    get_last_notification_presence_at,
    record_notification_interaction,
    record_notification_read,
)
from backend.app.services.i10.interaction_vocabulary import (
    CanonicalInteractionVerb,
    event_type_for_verb,
)
from backend.tests.otp_test_helpers import issue_access_token


def _login(client, db, monkeypatch, phone: str, code: str = "123456") -> dict:
    from backend.app.services import auth_otp_service as svc

    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value=code):
        ok, err, _ = svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
        assert ok, err
    body = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": code, "purpose": "LOGIN"},
    ).json()
    assert body.get("ok") is True, body
    return body["data"]


def _refresh(client, refresh_token: str):
    return client.post("/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"})


def _age_presence(db, user_id: int, *, days: int) -> None:
    when = datetime.utcnow() - timedelta(days=days)
    for ev in (
        db.query(models.InteractionEvent)
        .filter(models.InteractionEvent.user_id == user_id)
        .all()
    ):
        ev.created_at = when
    for mem in db.query(models.Memory).filter(models.Memory.user_id == user_id).all():
        mem.created_at = when
    db.commit()


def _notif(db, user_id: int, body: str = "ping") -> models.Notification:
    row = models.Notification(
        user_id=user_id,
        type="companion_ping",
        title="Ping",
        body=body,
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow() - timedelta(days=31),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _session(client, db, monkeypatch, phone: str):
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    data = _login(client, db, monkeypatch, phone)
    return user, data


def test_presence_set_is_canonical_verbs_minus_read():
    expected = frozenset(
        event_type_for_verb(verb)
        for verb in CanonicalInteractionVerb
        if verb is not CanonicalInteractionVerb.READ
    )
    assert NOTIFICATION_PRESENCE_EVENT_TYPES == expected
    assert event_type_for_verb(CanonicalInteractionVerb.READ) not in NOTIFICATION_PRESENCE_EVENT_TYPES
    for verb in (
        CanonicalInteractionVerb.ACKNOWLEDGE,
        CanonicalInteractionVerb.LIKE,
        CanonicalInteractionVerb.DISLIKE,
        CanonicalInteractionVerb.DISLIKE_REASON,
        CanonicalInteractionVerb.TALK_TO_SEDI,
        CanonicalInteractionVerb.NOT_NOW,
        CanonicalInteractionVerb.TALK_LATER,
        CanonicalInteractionVerb.DONE,
    ):
        assert event_type_for_verb(verb) in NOTIFICATION_PRESENCE_EVENT_TYPES


def test_ignored_notification_does_not_extend_session(client, db, monkeypatch):
    user, data = _session(client, db, monkeypatch, "+989160031001")
    _notif(db, user.id, "ignored")
    _age_presence(db, user.id, days=31)
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401


def test_read_seen_only_does_not_extend_session(client, db, monkeypatch):
    user, data = _session(client, db, monkeypatch, "+989160031002")
    notif = _notif(db, user.id, "read-only")
    _age_presence(db, user.id, days=31)
    record_notification_read(db, notification=notif, recipient_user_id=user.id)
    db.commit()
    assert get_last_notification_presence_at(db, user.id) is None or (
        datetime.utcnow() - get_last_notification_presence_at(db, user.id)
    ) >= timedelta(days=30)
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401


@pytest.mark.parametrize(
    "phone,payload",
    [
        ("+989160031003", {"action_id": "ACK_THANKS"}),
        ("+989160031004", {"action_id": "like"}),
        ("+989160031005", {"action_id": "dislike"}),
        ("+989160031006", {"action_id": "dislike", "reason": "too_frequent"}),
        ("+989160031007", {"action_id": "OPEN_CHAT"}),
        ("+989160031008", {"action_id": "NOT_NOW"}),
        ("+989160031009", {"action_id": "TALK_LATER"}),
    ],
)
def test_explicit_canonical_response_extends_session(client, db, monkeypatch, phone, payload):
    user, data = _session(client, db, monkeypatch, phone)
    notif = _notif(db, user.id, "act")
    _age_presence(db, user.id, days=31)
    record_notification_interaction(
        db,
        notification=notif,
        recipient_user_id=user.id,
        payload=payload,
    )
    db.commit()
    ok = _refresh(client, data["refresh_token"])
    assert ok.status_code == 200, ok.text


def test_domain_authorized_done_counts_as_presence(client, db, monkeypatch):
    user, data = _session(client, db, monkeypatch, "+989160031010")
    notif = _notif(db, user.id, "done")
    _age_presence(db, user.id, days=31)
    with pytest.raises(HTTPException) as denied_done:
        record_notification_interaction(
            db,
            notification=notif,
            recipient_user_id=user.id,
            payload={"action_id": "done"},
        )
    assert denied_done.value.status_code == 422
    still = _refresh(client, data["refresh_token"])
    assert still.status_code == 401
    record_notification_interaction(
        db,
        notification=notif,
        recipient_user_id=user.id,
        payload={"action_id": "done"},
        domain_completion_authorized=True,
    )
    db.commit()
    ok = _refresh(client, data["refresh_token"])
    assert ok.status_code == 200, ok.text


def test_cross_user_notification_interaction_cannot_extend_other_session(client, db, monkeypatch):
    user_a, data_a = _session(client, db, monkeypatch, "+989160031011")
    user_b, data_b = _session(client, db, monkeypatch, "+989160031012")
    notif_b = _notif(db, user_b.id, "b-only")
    _age_presence(db, user_a.id, days=31)
    _age_presence(db, user_b.id, days=31)
    record_notification_interaction(
        db,
        notification=notif_b,
        recipient_user_id=user_b.id,
        payload={"action_id": "OPEN_CHAT"},
    )
    db.commit()
    denied_a = _refresh(client, data_a["refresh_token"])
    assert denied_a.status_code == 401
    ok_b = _refresh(client, data_b["refresh_token"])
    assert ok_b.status_code == 200, ok_b.text
    assert refresh_allowed_for_presence(db, user_a.id) is False


def test_fcm_provider_activity_is_not_presence(client, db, monkeypatch):
    user, data = _session(client, db, monkeypatch, "+989160031013")
    notif = _notif(db, user.id, "fcm")
    _age_presence(db, user.id, days=31)
    notif.is_sent = True
    notif.provider = "fcm"
    notif.provider_message_id = "msg-fcm-1"
    notif.status = "delivered"
    create_interaction_event(
        db,
        user_id=user.id,
        event_type="fcm_send",
        source="system",
        source_notification_id=notif.id,
        metadata={"provider": "fcm"},
    )
    create_interaction_event(
        db,
        user_id=user.id,
        event_type="notification_sent",
        source="notification",
        source_notification_id=notif.id,
        metadata={"provider": "fcm"},
    )
    db.commit()
    login_events = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.user_id == user.id,
            models.InteractionEvent.event_type == AUTH_LOGIN_EVENT_TYPE,
        )
        .count()
    )
    assert login_events >= 1
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401
    assert get_last_notification_presence_at(db, user.id) is None or (
        datetime.utcnow() - get_last_notification_presence_at(db, user.id)
    ) >= timedelta(days=30)
