"""JWT is required for user-facing /knowledge/* endpoints (Phase 1E-b)."""

from __future__ import annotations

import uuid

from backend.app.core.security import create_access_token
from backend.app.models import KcFactCandidate, Notification, User


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _extract_body(**overrides) -> dict:
    body = {
        "text": "دارم متفورمین می‌خورم",
        "language": "fa",
        "source_message_id": f"pytest-{uuid.uuid4().hex[:12]}",
    }
    body.update(overrides)
    return body


def test_knowledge_next_question_requires_auth(client, db):
    _create_user(db, "KcNextNoAuth")
    response = client.get("/knowledge/next_question")
    assert response.status_code == 401


def test_knowledge_extract_requires_auth(client, db):
    _create_user(db, "KcExtractNoAuth")
    response = client.post("/knowledge/extract_from_message", json=_extract_body())
    assert response.status_code == 401


def test_knowledge_apply_answer_requires_auth(client, db):
    _create_user(db, "KcApplyNoAuth")
    response = client.post(
        "/knowledge/apply_answer",
        json={"field_key": "birth_year", "answer": "1990"},
    )
    assert response.status_code == 401


def test_knowledge_next_question_works_without_user_id_query(client, db):
    u = _create_user(db, "KcNextOwner")
    response = client.get(
        "/knowledge/next_question?lang=fa",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("ok") is True
    assert body.get("data") is not None


def test_knowledge_next_question_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "KcNextLegacy")
    response = client.get(
        f"/knowledge/next_question?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_knowledge_extract_works_without_user_id_in_body(client, db):
    u = _create_user(db, "KcExtractOwner")
    response = client.post(
        "/knowledge/extract_from_message",
        json=_extract_body(),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True


def test_knowledge_extract_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "KcExtractLegacy")
    response = client.post(
        "/knowledge/extract_from_message",
        json=_extract_body(user_id=u.id + 9999),
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_knowledge_apply_answer_works_without_user_id_in_body(client, db):
    u = _create_user(db, "KcApplyOwner")
    response = client.post(
        "/knowledge/apply_answer",
        json={"field_key": "birth_year", "answer": "1990"},
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True


def test_knowledge_apply_answer_rejects_legacy_user_id_in_body(client, db):
    u = _create_user(db, "KcApplyLegacy")
    response = client.post(
        "/knowledge/apply_answer",
        json={"user_id": u.id + 9999, "field_key": "birth_year", "answer": "1990"},
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_knowledge_extract_writes_only_for_authenticated_user(client, db):
    user_a = _create_user(db, "KcExtractA")
    user_b = _create_user(db, "KcExtractB")
    source_id = f"pytest-{uuid.uuid4().hex[:12]}"

    response = client.post(
        "/knowledge/extract_from_message",
        json=_extract_body(source_message_id=source_id),
        headers=_auth_header(user_a.id),
    )
    assert response.status_code == 200

    candidates_a = (
        db.query(KcFactCandidate)
        .filter(KcFactCandidate.user_id == user_a.id)
        .count()
    )
    candidates_b = (
        db.query(KcFactCandidate)
        .filter(KcFactCandidate.user_id == user_b.id)
        .count()
    )
    assert candidates_a >= 1
    assert candidates_b == 0


def test_knowledge_next_question_notify_scoped_to_authenticated_user(client, db, monkeypatch):
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    user_a = _create_user(db, "KcNotifyA")
    user_b = _create_user(db, "KcNotifyB")

    client.post(
        "/knowledge/extract_from_message",
        json=_extract_body(),
        headers=_auth_header(user_a.id),
    )

    response = client.get(
        "/knowledge/next_question?notify=true&in_app=true",
        headers=_auth_header(user_a.id),
    )
    assert response.status_code == 200
    data = response.json().get("data") or {}
    if data.get("question_type") == "confirm_candidate":
        notif_a = db.query(Notification).filter(Notification.user_id == user_a.id).count()
        notif_b = db.query(Notification).filter(Notification.user_id == user_b.id).count()
        assert notif_a >= 1
        assert notif_b == 0
