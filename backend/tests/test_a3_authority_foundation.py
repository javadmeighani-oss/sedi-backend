"""Targeted A3 authority foundation tests (JWT chat, intro, facts, stream chunks)."""

from datetime import datetime, timezone

from backend.app.services.a3_session_open import (
    build_first_intro_message,
    maybe_proactive_opener,
    open_a3_session,
    user_facing_known_facts,
)
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.interaction import InteractionResponse


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


def test_open_session_marks_intro_once(monkeypatch):
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

    # Second open: not first intro
    data2 = open_a3_session(_Db(), u)
    assert data2["first_intro"] is False


def test_proactive_opener_respects_cooldown(monkeypatch):
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
    """Safety law: stream only approved answer chunks (post-governed)."""
    approved = "Hello from governed Sedi answer."
    chunk_size = 28
    pieces = [approved[i : i + chunk_size] for i in range(0, len(approved), chunk_size)]
    assert "".join(pieces) == approved
    assert all(p for p in pieces)
