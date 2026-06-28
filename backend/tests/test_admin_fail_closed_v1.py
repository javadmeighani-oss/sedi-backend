"""Admin routes must fail closed when ADMIN_TOKEN is unset (Phase 1F)."""

from __future__ import annotations

from datetime import datetime

from backend.app.models import Notification, User

_TEST_ADMIN_TOKEN = "test-admin-fail-closed-v1"


def _admin_header(token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    return {"X-Admin-Token": token}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# -------------------- ai_core admin --------------------


def test_ai_core_admin_unset_admin_token_returns_403(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    response = client.get("/ai_core/admin/rag_metrics")
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"


def test_ai_core_admin_missing_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get("/ai_core/admin/rag_metrics")
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_ai_core_admin_wrong_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get(
        "/ai_core/admin/rag_metrics",
        headers=_admin_header("wrong-admin-token"),
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_ai_core_admin_valid_token_allows_read_only_route(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get(
        "/ai_core/admin/rag_metrics",
        headers=_admin_header(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert "data" in payload


# -------------------- notifications admin --------------------


def test_notifications_admin_unset_admin_token_returns_403(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    response = client.get("/notifications/admin/health")
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"


def test_notifications_admin_missing_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get("/notifications/admin/health")
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_notifications_admin_wrong_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get(
        "/notifications/admin/health",
        headers=_admin_header("wrong-admin-token"),
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_notifications_admin_valid_token_allows_read_only_route(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.get(
        "/notifications/admin/health",
        headers=_admin_header(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("ok") is True
    assert "data" in payload


# -------------------- deliver_pending --------------------


def test_deliver_pending_unset_admin_token_returns_403(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    response = client.post("/notifications/deliver_pending?limit=10")
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"


def test_deliver_pending_missing_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.post("/notifications/deliver_pending?limit=10")
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_deliver_pending_wrong_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    response = client.post(
        "/notifications/deliver_pending?limit=10",
        headers=_admin_header("wrong-admin-token"),
    )
    assert response.status_code == 401
    assert response.json().get("detail") == "Admin token required"


def test_deliver_pending_valid_token_processes_outbox(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    u = _create_user(db, "DeliverPendingAdmin")
    notif = Notification(
        user_id=u.id,
        type="health_alert",
        title="Admin deliver",
        body="Body",
        priority="high",
        is_sent=False,
        dedupe_key="test:admin-fail-closed:deliver",
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()

    response = client.post(
        "/notifications/deliver_pending?limit=10",
        headers=_admin_header(),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("data", {}).get("sent_count") == 1
    db.refresh(notif)
    assert notif.is_sent is True
