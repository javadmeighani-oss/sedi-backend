"""Session identity + 30-day re-auth + I7 derived continuity after raw expiry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.models import Memory, User
from backend.app.services.auth_session_policy import (
    AUTH_LOGIN_EVENT_TYPE,
    SECURITY_REAUTH_DAYS,
    get_last_meaningful_user_presence_at,
)
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i6.memory_writes import get_readable_fact_or_none
from backend.app.services.i7.derived_continuity import get_bounded_continuity_topic
from backend.app.services.i7.governed_raw import try_durable_raw_write
from backend.app.services.i7.retention import RAW_VISIBLE_DAYS
from backend.app.services.intelligence.adapters import CurrentMemoryContextAdapter
from backend.tests.otp_test_helpers import issue_access_token


WALK_TOPIC = "I want to start walking 30 minutes every evening."
CONTINUE_TOPIC = "همان بحث قبلی را ادامه بده"
NEW_TOPIC = "What is a healthy breakfast?"


class _FakeCompletion:
    def __init__(self, text: str):
        self.output_text = text


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


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
    for mem in db.query(Memory).filter(Memory.user_id == user_id).all():
        mem.created_at = when
        mem.retain_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()


def _patch_gpt(text: str = "Governed Sedi response.", captured: dict | None = None):
    def _create(*_a, **kwargs):
        if captured is not None:
            captured["input"] = kwargs.get("input")
        return _FakeCompletion(text)

    return patch(
        "backend.app.core.conversation.prompts.client.responses.create",
        side_effect=_create,
    )


def test_raw_retention_days_unchanged():
    assert RAW_VISIBLE_DAYS == 30
    assert SECURITY_REAUTH_DAYS == 30


def test_access_expiry_silent_refresh_same_user(client, db, monkeypatch):
    phone = "+989160010001"
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    data = _login(client, db, monkeypatch, phone)
    assert data["user_id"] == user.id
    r = _refresh(client, data["refresh_token"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"] != data["refresh_token"]
    assert db.query(User).filter(User.phone == phone).count() == 1


def test_refresh_does_not_count_as_presence(client, db, monkeypatch):
    phone = "+989160010002"
    issue_access_token(client, db, monkeypatch, phone)
    data = _login(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    before = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.user_id == user.id,
            models.InteractionEvent.event_type == AUTH_LOGIN_EVENT_TYPE,
        )
        .count()
    )
    last_before = get_last_meaningful_user_presence_at(db, user.id)
    r = _refresh(client, data["refresh_token"])
    assert r.status_code == 200, r.text
    after = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.user_id == user.id,
            models.InteractionEvent.event_type == AUTH_LOGIN_EVENT_TYPE,
        )
        .count()
    )
    assert after == before
    last_after = get_last_meaningful_user_presence_at(db, user.id)
    assert last_after == last_before


def test_explicit_logout_requires_login_otp(client, db, monkeypatch):
    phone = "+989160010003"
    issue_access_token(client, db, monkeypatch, phone)
    data = _login(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    grant_memory_consent(db, user.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    out = client.post("/auth/logout", headers={"Authorization": f"Bearer {data['refresh_token']}"})
    assert out.status_code == 200, out.text
    assert out.json().get("data", {}).get("revoked") is True
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401
    assert "Invalid or expired refresh token" in (denied.json().get("detail") or "")
    assert db.query(User).filter(User.id == user.id).count() == 1
    assert db.query(Memory).filter(Memory.user_id == user.id).count() >= 1
    again = _login(client, db, monkeypatch, phone)
    assert again["user_id"] == user.id
    assert db.query(User).filter(User.phone == phone).count() == 1


def test_30d_inactivity_requires_login_otp_same_user(client, db, monkeypatch):
    phone = "+989160010004"
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    users_before = db.query(User).count()
    data = _login(client, db, monkeypatch, phone)
    _age_presence(db, user.id, days=31)
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401
    assert "Invalid or expired refresh token" in (denied.json().get("detail") or "")
    restored = _login(client, db, monkeypatch, phone)
    assert restored["user_id"] == user.id
    assert db.query(User).count() == users_before
    ok = _refresh(client, restored["refresh_token"])
    assert ok.status_code == 200, ok.text


def test_ignored_notification_does_not_extend_session(client, db, monkeypatch):
    phone = "+989160010005"
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    data = _login(client, db, monkeypatch, phone)
    notif = models.Notification(
        user_id=user.id,
        type="companion_ping",
        title="Ping",
        body="ignored",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow() - timedelta(days=31),
    )
    db.add(notif)
    db.commit()
    _age_presence(db, user.id, days=31)
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401


def test_explicit_notification_interaction_counts_as_presence(client, db, monkeypatch):
    phone = "+989160010006"
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    data = _login(client, db, monkeypatch, phone)
    notif = models.Notification(
        user_id=user.id,
        type="companion_ping",
        title="Ping",
        body="act",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow() - timedelta(days=31),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    _age_presence(db, user.id, days=31)
    from backend.app.services.i10.interaction_recorder import record_notification_interaction

    record_notification_interaction(
        db,
        notification=notif,
        recipient_user_id=user.id,
        payload={"action_id": "OPEN_CHAT"},
    )
    db.commit()
    ok = _refresh(client, data["refresh_token"])
    assert ok.status_code == 200, ok.text


def test_login_never_creates_account(client, db, monkeypatch):
    phone = "+989160010007"
    before = db.query(User).count()
    from backend.app.services import auth_otp_service as svc

    monkeypatch.setenv("OTP_SECRET", "test_otp_0007")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone, purpose=svc.OTP_PURPOSE_LOGIN)
    body = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": "123456", "purpose": "LOGIN"},
    ).json()
    assert body.get("ok") is False
    assert body.get("error", {}).get("code") == "ACCOUNT_NOT_FOUND"
    assert db.query(User).count() == before
    assert db.query(User).filter(User.phone == phone).first() is None


def test_long_term_derived_continuity_after_raw_expiry_and_reauth(client, db, monkeypatch):
    phone = "+989160010008"
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    grant_memory_consent(db, user.id, commit=True)
    user.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    assert written.durable is True
    assert get_bounded_continuity_topic(db, user.id)
    data = _login(client, db, monkeypatch, phone)
    _age_presence(db, user.id, days=31)
    assert CurrentMemoryContextAdapter().load(db, authenticated_user_id=user.id)
    raw = (
        db.query(Memory)
        .filter(Memory.user_id == user.id, Memory.user_message == WALK_TOPIC)
        .one()
    )
    assert raw.retain_until < datetime.now(timezone.utc)
    denied = _refresh(client, data["refresh_token"])
    assert denied.status_code == 401
    users_before = db.query(User).count()
    restored = _login(client, db, monkeypatch, phone)
    assert restored["user_id"] == user.id
    assert db.query(User).count() == users_before
    opened = client.post("/interact/session/open", headers=_auth(user.id))
    assert opened.status_code == 200, opened.text
    msg = (opened.json().get("message") or "").lower()
    assert "walking" in msg
    captured: dict = {}
    with _patch_gpt("We can continue the evening walking plan.", captured):
        cont = client.post(
            "/interact/chat",
            json={"message": CONTINUE_TOPIC},
            headers=_auth(user.id),
        )
    assert cont.status_code == 200, cont.text
    blob = " ".join(
        (m.get("content") if isinstance(m, dict) else str(m))
        for m in (captured.get("input") or [])
    )
    assert "walking" in blob.lower()
    assert CONTINUE_TOPIC in blob
    captured2: dict = {}
    with _patch_gpt("Breakfast can include oats and fruit.", captured2):
        nxt = client.post(
            "/interact/chat",
            json={"message": NEW_TOPIC},
            headers=_auth(user.id),
        )
    assert nxt.status_code == 200, nxt.text
    prompt = captured2.get("input") or []
    user_contents = [
        m.get("content")
        for m in prompt
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    assert user_contents[-1] == NEW_TOPIC


def test_revoke_blocks_derived_continuity(client, db, monkeypatch):
    phone = "+989160010009"
    issue_access_token(client, db, monkeypatch, phone)
    user = db.query(User).filter(User.phone == phone).first()
    grant_memory_consent(db, user.id, commit=True)
    user.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.commit()
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    _age_presence(db, user.id, days=31)
    revoke_memory_consent(db, user.id, commit=True)
    assert get_bounded_continuity_topic(db, user.id) is None
    assert CurrentMemoryContextAdapter().load(db, authenticated_user_id=user.id) == []
    opened = client.post("/interact/session/open", headers=_auth(user.id))
    assert opened.status_code == 200, opened.text
    assert "walking" not in (opened.json().get("message") or "").lower()
    restored = _login(client, db, monkeypatch, phone)
    assert restored["user_id"] == user.id


def test_cross_user_derived_continuity_isolation(db):
    a = User(name="IsoA", secret_key="k", preferred_language="en", phone="+989160010010")
    b = User(name="IsoB", secret_key="k", preferred_language="en", phone="+989160010011")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=a.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted.",
        actor_user_id=a.id,
        commit=True,
    )
    assert get_bounded_continuity_topic(db, a.id)
    assert get_bounded_continuity_topic(db, b.id) is None
    items = CurrentMemoryContextAdapter().load(db, authenticated_user_id=b.id)
    text = " ".join(str(getattr(i, "structured_value", "")) for i in items)
    assert WALK_TOPIC not in text
    assert "walking" not in text.lower()


def test_no_consent_no_derived_write(db):
    user = User(name="NoWrite", secret_key="k", preferred_language="en", phone="+989160010012")
    db.add(user)
    db.commit()
    db.refresh(user)
    denied = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="no",
        actor_user_id=user.id,
        commit=True,
    )
    assert denied.durable is False
    assert get_bounded_continuity_topic(db, user.id) is None
    assert get_readable_fact_or_none(db, user.id, "lifestyle", "walk") is None
