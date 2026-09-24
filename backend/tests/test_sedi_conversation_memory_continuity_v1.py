"""PostgreSQL-backed Sedi conversation-memory continuity (B1–B8). No production."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app.core.security import create_access_token
from backend.app.models import Memory, User, UserMemoryFact
from backend.app.services.i6.consent_service import (
    PERM_READ,
    grant_memory_consent,
    has_permission,
    revoke_memory_consent,
)
from backend.app.services.i6.memory_writes import get_readable_fact_or_none, list_facts_or_empty
from backend.app.services.i7.governed_raw import try_durable_raw_write
from backend.app.services.intelligence.adapters import CurrentMemoryContextAdapter
from backend.app.services.intelligence.assembler import AuthorizedContextAssembler
from backend.app.services.knowledge.conversation_extraction_service import (
    process_message as kc_process_message,
)


WALK_TOPIC = "I want to start walking 30 minutes every evening."
CONTINUE_TOPIC = "Let's continue what we discussed."
NEW_TOPIC = "What is a healthy breakfast?"


class _FakeCompletion:
    def __init__(self, text: str):
        self.output_text = text


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _user(db, name: str, *, lang: str = "en") -> User:
    row = User(name=name, secret_key="mem-cont", preferred_language=lang)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _patch_gpt(text: str = "Governed Sedi response.", captured: dict | None = None):
    def _create(*_a, **kwargs):
        if captured is not None:
            captured["input"] = kwargs.get("input")
        return _FakeCompletion(text)

    return patch(
        "backend.app.core.conversation.prompts.client.responses.create",
        side_effect=_create,
    )


def _memory_keys(items) -> set[str]:
    return {getattr(i, "canonical_key", "") for i in items}


def _age_last_memory(db, user_id: int, *, hours: int) -> Memory:
    row = (
        db.query(Memory)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.created_at.desc())
        .first()
    )
    assert row is not None
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=hours)
    db.commit()
    db.refresh(row)
    return row


def _projection_text(db, user_id: int) -> str:
    snap = AuthorizedContextAssembler().assemble(
        db, authenticated_user_id=user_id, request_id=f"mem-{user_id}"
    )
    proj = AuthorizedContextAssembler().build_compatibility_projection(snap)
    return proj.text or ""


def test_b1_consented_chat_durable_write(client, db):
    user = _user(db, "MemWriteYes")
    grant_memory_consent(db, user.id, commit=True)
    with _patch_gpt("I can help you build a walking habit."):
        resp = client.post(
            "/interact/chat",
            json={"message": WALK_TOPIC},
            headers=_auth(user.id),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"]
    assert body["user_id"] == user.id
    rows = db.query(Memory).filter(Memory.user_id == user.id).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.durable_write is True
    assert row.user_message == WALK_TOPIC
    assert row.sedi_response == "I can help you build a walking habit."
    assert row.consent_id is not None
    assert row.provenance_json
    assert row.retain_until is not None
    assert row.user_id == user.id


def test_b1_no_consent_no_durable_write(client, db):
    user = _user(db, "MemWriteNo")
    before = db.query(Memory).filter(Memory.user_id == user.id).count()
    with _patch_gpt("Hello, I am here to help."):
        resp = client.post(
            "/interact/chat",
            json={"message": "Hello Sedi"},
            headers=_auth(user.id),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"]
    after = db.query(Memory).filter(Memory.user_id == user.id).all()
    assert len(after) == before
    assert all(not r.durable_write for r in after)


def test_b2_memory_history_jwt_only(client, db):
    user = _user(db, "MemHist")
    other = _user(db, "MemHistOther")
    grant_memory_consent(db, user.id, commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    assert written.durable is True
    resp = client.get("/memory/history?group=daily", headers=_auth(user.id))
    assert resp.status_code == 200, resp.text
    turns = [t for g in resp.json()["items"] for t in g["turns"]]
    assert any(t["user_message"] == WALK_TOPIC for t in turns)
    blocked = client.get(
        f"/memory/history?group=daily&user_id={user.id}",
        headers=_auth(other.id),
    )
    assert blocked.status_code == 422


def test_b3_authorized_recent_turn_to_i2(db):
    user = _user(db, "MemI2Yes")
    grant_memory_consent(db, user.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    assert has_permission(db, user.id, PERM_READ)
    items = CurrentMemoryContextAdapter().load(db, authenticated_user_id=user.id)
    text = " ".join(str(getattr(i, "structured_value", "")) for i in items)
    assert WALK_TOPIC in text
    assert any(k.startswith("memory.turn.") for k in _memory_keys(items))
    for item in items:
        assert item.provenance.owner_user_id == user.id


def test_b3_revoked_and_expired_and_cross_user_not_projected(db):
    owner = _user(db, "MemI2Owner")
    stranger = _user(db, "MemI2Stranger")
    grant_memory_consent(db, owner.id, commit=True)
    grant_memory_consent(db, stranger.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=owner.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=owner.id,
        commit=True,
    )
    expired = try_durable_raw_write(
        db,
        user_id=owner.id,
        user_message="This expired turn must not project.",
        sedi_response="expired-hidden",
        actor_user_id=owner.id,
        idempotency_key="expired-turn",
        commit=True,
    )
    expired.memory.retain_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    stranger_items = CurrentMemoryContextAdapter().load(
        db, authenticated_user_id=stranger.id
    )
    stranger_text = " ".join(str(getattr(i, "structured_value", "")) for i in stranger_items)
    assert WALK_TOPIC not in stranger_text
    assert "expired-hidden" not in stranger_text

    owner_items = CurrentMemoryContextAdapter().load(db, authenticated_user_id=owner.id)
    owner_text = " ".join(str(getattr(i, "structured_value", "")) for i in owner_items)
    assert WALK_TOPIC in owner_text
    assert "This expired turn must not project." not in owner_text

    revoke_memory_consent(db, owner.id, commit=True)
    assert has_permission(db, owner.id, PERM_READ) is False
    revoked_items = CurrentMemoryContextAdapter().load(db, authenticated_user_id=owner.id)
    revoked_text = " ".join(str(getattr(i, "structured_value", "")) for i in revoked_items)
    assert WALK_TOPIC not in revoked_text
    assert revoked_items == []
    retained = db.query(Memory).filter(Memory.user_id == owner.id, Memory.durable_write.is_(True)).count()
    assert retained >= 1


def test_b4_prior_topic_continuation(client, db):
    user = _user(db, "MemContinue")
    grant_memory_consent(db, user.id, commit=True)
    with _patch_gpt("I can help you start evening walks."):
        first = client.post(
            "/interact/chat",
            json={"message": WALK_TOPIC},
            headers=_auth(user.id),
        )
    assert first.status_code == 200, first.text
    captured: dict = {}
    with _patch_gpt("Yes, we can continue the evening walking plan.", captured):
        second = client.post(
            "/interact/chat",
            json={"message": CONTINUE_TOPIC},
            headers=_auth(user.id),
        )
    assert second.status_code == 200, second.text
    prompt = captured.get("input") or []
    blob = " ".join(
        (m.get("content") if isinstance(m, dict) else str(m)) for m in prompt
    )
    assert WALK_TOPIC in blob
    assert CONTINUE_TOPIC in blob
    user_contents = [
        m.get("content")
        for m in prompt
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    assert user_contents[-1] == CONTINUE_TOPIC
    assert WALK_TOPIC in _projection_text(db, user.id)


def test_b5_current_topic_priority(client, db):
    user = _user(db, "MemPriority")
    grant_memory_consent(db, user.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    captured: dict = {}
    with _patch_gpt("Breakfast can include oats, fruit, and protein.", captured):
        resp = client.post(
            "/interact/chat",
            json={"message": NEW_TOPIC},
            headers=_auth(user.id),
        )
    assert resp.status_code == 200, resp.text
    prompt = captured.get("input") or []
    user_contents = [
        m.get("content")
        for m in prompt
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    assert user_contents[-1] == NEW_TOPIC
    assert user_contents[-1] != WALK_TOPIC


def test_b6_returning_contextual_and_generic(client, db):
    contextual = _user(db, "MemReturnYes")
    generic = _user(db, "MemReturnNo")
    grant_memory_consent(db, contextual.id, commit=True)
    now = datetime.now(timezone.utc)
    contextual.sedi_intro_completed_at = now - timedelta(days=2)
    generic.sedi_intro_completed_at = now - timedelta(days=2)
    db.commit()
    try_durable_raw_write(
        db,
        user_id=contextual.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=contextual.id,
        commit=True,
    )
    _age_last_memory(db, contextual.id, hours=13)
    yes = client.post("/interact/session/open", headers=_auth(contextual.id))
    assert yes.status_code == 200, yes.text
    yes_msg = yes.json()["message"] or ""
    assert "walking 30 minutes" in yes_msg.lower() or "walking" in yes_msg.lower()
    assert yes.json().get("first_intro") is False

    no = client.post("/interact/session/open", headers=_auth(generic.id))
    assert no.status_code == 200, no.text
    no_msg = (no.json()["message"] or "").lower()
    assert "walking 30 minutes" not in no_msg
    assert "evening" not in no_msg or "welcome" in no_msg or no_msg == ""


def test_b7_i6_fact_continuity(client, db):
    user = _user(db, "MemFact", lang="en")
    grant_memory_consent(db, user.id, commit=True)
    with _patch_gpt("I heard you. We can keep going from here."):
        resp = client.post(
            "/interact/chat",
            json={"message": "I slept well last night."},
            headers=_auth(user.id),
        )
    assert resp.status_code == 200, resp.text
    # Same extraction/candidate path ConversationBrain invokes after a governed turn.
    kc_process_message(
        db=db,
        user_id=user.id,
        text="خوابم خوب بود",
        language="fa",
        source_message_id="continuity-b7",
    )
    fact = get_readable_fact_or_none(db, user.id, "lifestyle", "sleep_quality")
    assert fact is not None
    pack_text = _projection_text(db, user.id)
    facts = list_facts_or_empty(db, user.id, domain="lifestyle")
    assert any(r.key == "sleep_quality" for r in facts)
    assert "sleep_quality" in pack_text
    revoke_memory_consent(db, user.id, commit=True)
    assert get_readable_fact_or_none(db, user.id, "lifestyle", "sleep_quality") is None
    assert list_facts_or_empty(db, user.id, domain="lifestyle") == []
    assert "sleep_quality" not in _projection_text(db, user.id)
    retained = (
        db.query(UserMemoryFact)
        .filter(UserMemoryFact.user_id == user.id, UserMemoryFact.key == "sleep_quality")
        .count()
    )
    assert retained >= 1


def test_b8_revoke_blocks_write_and_read(client, db):
    user = _user(db, "MemRevoke")
    grant_memory_consent(db, user.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    grant_memory_consent(db, user.id, commit=True)
    from backend.app.services.i6.memory_writes import write_fact

    write_fact(db, user.id, "lifestyle", "mood", "calm", commit=True)
    revoke_memory_consent(db, user.id, commit=True)
    denied = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message="After revoke this must not persist.",
        sedi_response="should-not-write",
        actor_user_id=user.id,
        commit=True,
    )
    assert denied.durable is False
    assert denied.reason == "NO_CONSENT"
    assert CurrentMemoryContextAdapter().load(db, authenticated_user_id=user.id) == []
    assert get_readable_fact_or_none(db, user.id, "lifestyle", "mood") is None
    with _patch_gpt("Generic help after revoke."):
        resp = client.post(
            "/interact/chat",
            json={"message": "After revoke this must not persist."},
            headers=_auth(user.id),
        )
    assert resp.status_code == 200, resp.text
    assert (
        db.query(Memory)
        .filter(
            Memory.user_id == user.id,
            Memory.user_message == "After revoke this must not persist.",
        )
        .count()
        == 0
    )
    yes = client.post("/interact/session/open", headers=_auth(user.id))
    assert yes.status_code == 200, yes.text
    assert "walking 30 minutes" not in (yes.json().get("message") or "").lower()


def test_opener_cooldown_blocks_contextual_within_12h(client, db):
    user = _user(db, "MemCoolIn")
    grant_memory_consent(db, user.id, commit=True)
    user.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    resp = client.post("/interact/session/open", headers=_auth(user.id))
    assert resp.status_code == 200, resp.text
    msg = (resp.json().get("message") or "").lower()
    assert "walking" not in msg
    assert resp.json().get("proactive_opener") in (None, "")


def test_opener_after_cooldown_uses_authorized_memory(client, db):
    user = _user(db, "MemCoolOut")
    grant_memory_consent(db, user.id, commit=True)
    user.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    _age_last_memory(db, user.id, hours=13)
    resp = client.post("/interact/session/open", headers=_auth(user.id))
    assert resp.status_code == 200, resp.text
    msg = (resp.json().get("message") or "").lower()
    assert "walking" in msg
    assert "continue" in msg


def test_opener_after_cooldown_revoked_no_memory(client, db):
    user = _user(db, "MemCoolRevoke")
    grant_memory_consent(db, user.id, commit=True)
    user.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    _age_last_memory(db, user.id, hours=13)
    revoke_memory_consent(db, user.id, commit=True)
    resp = client.post("/interact/session/open", headers=_auth(user.id))
    assert resp.status_code == 200, resp.text
    assert "walking" not in (resp.json().get("message") or "").lower()


def test_opener_after_cooldown_expired_no_memory(client, db):
    user = _user(db, "MemCoolExpired")
    grant_memory_consent(db, user.id, commit=True)
    user.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=user.id,
        commit=True,
    )
    written.memory.retain_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    _age_last_memory(db, user.id, hours=13)
    resp = client.post("/interact/session/open", headers=_auth(user.id))
    assert resp.status_code == 200, resp.text
    assert "walking" not in (resp.json().get("message") or "").lower()


def test_opener_after_cooldown_cross_user_no_memory(client, db):
    owner = _user(db, "MemCoolOwner")
    other = _user(db, "MemCoolOther")
    grant_memory_consent(db, owner.id, commit=True)
    grant_memory_consent(db, other.id, commit=True)
    now = datetime.now(timezone.utc)
    owner.sedi_intro_completed_at = now - timedelta(days=2)
    other.sedi_intro_completed_at = now - timedelta(days=2)
    db.commit()
    try_durable_raw_write(
        db,
        user_id=owner.id,
        user_message=WALK_TOPIC,
        sedi_response="Noted, evening walks.",
        actor_user_id=owner.id,
        commit=True,
    )
    _age_last_memory(db, owner.id, hours=13)
    resp = client.post("/interact/session/open", headers=_auth(other.id))
    assert resp.status_code == 200, resp.text
    assert "walking" not in (resp.json().get("message") or "").lower()
