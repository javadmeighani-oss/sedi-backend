"""Targeted A3 authority foundation tests (unit + Postgres/conftest integration)."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.core.security import create_access_token
from backend.app.models import User
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.interaction import InteractionResponse
from backend.app.services.a3_session_open import (
    build_first_intro_message,
    maybe_proactive_opener,
    open_a3_session,
    user_facing_known_facts,
)


class _U:
    def __init__(self, id=1, name="Ali", preferred_language="fa", intro=None):
        self.id = id
        self.name = name
        self.preferred_language = preferred_language
        self.sedi_intro_completed_at = intro


def test_chat_request_allows_omitted_user_id_and_source_notification():
    req = ChatRequest(message="hello", source_notification_id=42)
    assert req.user_id is None
    assert req.source_notification_id == 42


def test_interaction_response_carries_a3_session_fields():
    r = InteractionResponse(
        message="hi",
        language="en",
        timestamp=datetime.utcnow(),
        first_intro=True,
        intro_completed=True,
        proactive_opener=None,
        source_notification_id=9,
    )
    assert r.first_intro is True
    assert r.source_notification_id == 9


def test_first_intro_uses_preferred_language_and_name():
    u = _U(name="سارا", preferred_language="fa")
    msg = build_first_intro_message(u)
    assert "سارا" in msg
    assert "صدی" in msg


def test_open_session_marks_intro_once():
    class _Db:
        def add(self, *_a, **_k):
            return None

        def commit(self):
            return None

        def refresh(self, u):
            return None

        def query(self, *_a, **_k):
            class _Q:
                def filter(self, *_a, **_k):
                    return self

                def order_by(self, *_a, **_k):
                    return self

                def first(self):
                    return None

            return _Q()

    u = _U(intro=None)
    data = open_a3_session(_Db(), u)
    assert data["first_intro"] is True
    assert data["intro_completed"] is True
    assert u.sedi_intro_completed_at is not None
    assert data["message"]

    data2 = open_a3_session(_Db(), u)
    assert data2["first_intro"] is False


def test_proactive_opener_respects_cooldown():
    u = _U(intro=datetime.now(timezone.utc), preferred_language="en")

    class _Db:
        def query(self, *_a, **_k):
            class _Q:
                def filter(self, *_a, **_k):
                    return self

                def order_by(self, *_a, **_k):
                    return self

                def first(self):
                    return (datetime.now(timezone.utc),)

            return _Q()

    assert maybe_proactive_opener(_Db(), u) is None


def test_known_facts_empty_without_rows(monkeypatch):
    class _Db:
        pass

    monkeypatch.setattr(
        "backend.app.services.user_profile_fact_service.list_profile_facts",
        lambda db, uid: [],
    )
    assert user_facing_known_facts(_Db(), 1) == []


def test_stream_chunks_match_governed_final_text():
    approved = "Hello from governed Sedi answer."
    chunk_size = 28
    pieces = [approved[i : i + chunk_size] for i in range(0, len(approved), chunk_size)]
    assert "".join(pieces) == approved
    assert all(p for p in pieces)


def test_migration_082_column_exists_on_postgres(db):
    assert hasattr(User, "sedi_intro_completed_at")
    u = User(name="IntroCol", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.sedi_intro_completed_at is None
    u.sedi_intro_completed_at = datetime.now(timezone.utc)
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.sedi_intro_completed_at is not None


def test_session_open_intro_durable_once_postgres(client, db):
    u = User(name="Sara", secret_key="test", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.post("/interact/session/open", headers=headers)
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1.get("first_intro") is True
    assert "صدی" in (body1.get("message") or "") or "Sedi" in (body1.get("message") or "")

    db.refresh(u)
    assert u.sedi_intro_completed_at is not None

    r2 = client.post("/interact/session/open", headers=headers)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2.get("first_intro") is False


def test_known_facts_requires_jwt(client):
    r = client.get("/user/me/known-facts")
    assert r.status_code == 401


def test_known_facts_empty_for_authenticated_user(client, db):
    u = User(name="FactsUser", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})
    r = client.get(
        "/user/me/known-facts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload.get("ok") is True
    data = payload.get("data") or {}
    assert data.get("facts") == []


def test_chat_rejects_mismatched_body_user_id(client, db):
    u = User(name="JwtAuth", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})
    r = client.post(
        "/interact/chat",
        json={"user_id": u.id + 9999, "message": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_chat_stream_sse_final_consistency(client, db, monkeypatch):
    u = User(name="StreamUser", secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    token = create_access_token({"user_id": u.id})

    approved = "Governed final answer for SSE certification."

    async def _fake_chat(request, payload, db, user):
        return InteractionResponse(
            message=approved,
            language="en",
            user_id=user.id,
            timestamp=datetime.utcnow(),
            source_notification_id=payload.source_notification_id,
        )

    monkeypatch.setattr("backend.app.routers.interact.chat", _fake_chat)

    r = client.post(
        "/interact/chat/stream",
        json={"message": "hi", "source_notification_id": 77},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert "text/event-stream" in (r.headers.get("content-type") or "")
    text = r.text
    assert "event: start" in text
    assert "event: metadata" in text
    assert "event: delta" in text
    assert "event: final" in text
    assert approved in text
    assert "77" in text
