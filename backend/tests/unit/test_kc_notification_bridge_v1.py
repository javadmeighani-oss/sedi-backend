"""
Unit tests: KC → Notification Bridge V1.
- notify=false: no send / no notification field or attempted=false.
- notify=true + confirm_candidate: send with display_* and idempotency.
- notify=true + no_question (fatigue): send NOT called.
- Notify errors are non-fatal: response ok, notification.ok=false.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.database import Base, SessionLocal, engine
from backend.app.main import app as sedi_app

_UID = 91020


def _collect_paths(routes, prefix=""):
    paths = set()
    for r in routes:
        path = getattr(r, "path", None) or ""
        if hasattr(r, "routes"):
            paths.update(_collect_paths(r.routes, prefix + path))
        elif path:
            paths.add(prefix + path)
    return paths


@pytest.fixture()
def client() -> TestClient:
    paths = _collect_paths(sedi_app.routes)
    assert "/knowledge/next_question" in paths
    return TestClient(sedi_app)


@pytest.fixture()
def db() -> Session:
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def test_user_id(db: Session) -> int:
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": _UID, "name": "KC Notify Test", "secret": "n", "lang": "fa"},
    )
    db.commit()
    return _UID


def _seed_candidate(client: TestClient, user_id: int) -> None:
    r = client.post(
        "/knowledge/extract_from_message",
        json={
            "user_id": user_id,
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": f"pytest-notify-{uuid.uuid4().hex[:12]}",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json().get("data", {}).get("created_candidates_count", 0) >= 1


def test_next_question_notify_false_does_not_send(client: TestClient, test_user_id: int, monkeypatch):
    """With seeded confirm_candidate, call next_question without notify or notify=false; no notification field or attempted=false."""
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    r = client.get(f"/knowledge/next_question?user_id={test_user_id}&lang=en")
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None
    assert data.get("question_type") == "confirm_candidate"
    assert "notification" not in data or data.get("notification", {}).get("attempted") is False


def test_next_question_notify_true_sends_for_confirm_candidate(client: TestClient, test_user_id: int, monkeypatch):
    """notify=true + confirm_candidate: send attempted with title/body from display_*, metadata includes candidate_id + idempotency."""
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    send_calls: list = []

    def _capture_send(db, user_id, data, lang):
        send_calls.append({"user_id": user_id, "data": dict(data), "lang": lang})
        return {"attempted": True, "ok": True, "notification_id": 999}

    with patch("backend.app.routers.knowledge._maybe_send_kc_notification", side_effect=_capture_send):
        r = client.get(f"/knowledge/next_question?user_id={test_user_id}&lang=en&notify=true")
    assert r.status_code == 200, r.text
    resp_data = r.json().get("data")
    assert resp_data is not None
    assert resp_data.get("question_type") == "confirm_candidate"
    assert resp_data.get("display_title") and resp_data.get("display_body")
    assert len(send_calls) == 1, "send should be called once"
    call = send_calls[0]
    assert call["user_id"] == test_user_id
    assert call["data"].get("display_title") == resp_data["display_title"]
    assert call["data"].get("display_body") == resp_data["display_body"]
    assert call["data"].get("candidate_id") is not None
    assert "notification" in resp_data
    assert resp_data["notification"].get("attempted") is True
    assert resp_data["notification"].get("ok") is True


def test_next_question_notify_true_no_question_does_not_send(client: TestClient, test_user_id: int, monkeypatch):
    """Fatigue blocks question; next_question?notify=true returns no_question; send NOT called."""
    monkeypatch.setenv("KC_DAILY_QUESTION_CAP", "0")
    send_calls: list = []

    def _capture_send(db, user_id, data, lang):
        send_calls.append(True)
        return {"attempted": True, "ok": True}

    with patch("backend.app.routers.knowledge._maybe_send_kc_notification", side_effect=_capture_send):
        r = client.get(f"/knowledge/next_question?user_id={test_user_id}&notify=true")
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data.get("status") == "no_question"
    assert data.get("reason") == "fatigue_control"
    assert "notification" not in data
    assert len(send_calls) == 0, "should not call send when no question"


def test_notify_errors_are_non_fatal(client: TestClient, test_user_id: int, monkeypatch):
    """When _maybe_send_kc_notification raises, endpoint still returns 200 with notification.ok=false."""
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    _seed_candidate(client, test_user_id)

    def _raise(_db, _user_id, _data, _lang):
        raise RuntimeError("fake send failure")

    with patch("backend.app.routers.knowledge._maybe_send_kc_notification", side_effect=_raise):
        r = client.get(f"/knowledge/next_question?user_id={test_user_id}&lang=en&notify=true")
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None
    assert data.get("question_type") == "confirm_candidate"
    assert data.get("notification", {}).get("ok") is False
    assert data.get("notification", {}).get("attempted") is True
    assert "reason" in data.get("notification", {})
