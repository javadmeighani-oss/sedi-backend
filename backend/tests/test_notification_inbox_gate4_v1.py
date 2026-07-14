"""Gate 4 safe inbox metadata on notification list/unread (Section 14-A1)."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import Notification, User
from backend.app.services.gate4.notification_contract import (
    GATE4_CONTRACT_VERSION,
    SmartNotificationAction,
    V1_DEFAULT_ACTIONS,
    get_action_label,
)


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str, lang: str = "en") -> User:
    u = User(name=name, secret_key="test", preferred_language=lang)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _create_notification(db, user_id: int, **overrides) -> Notification:
    base = dict(
        user_id=user_id,
        type="health_alert",
        title="Health",
        body="Sensitive body with Metformin 500mg diagnosis data",
        priority="high",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
        category="health_status",
        risk_level="high",
        language="en",
        context_json=json.dumps(
            {
                "action_hint": "open_chat",
                "diagnosis": "hidden condition",
                "dosage_instructions": "10mg",
                "raw_payload": {"secret": "value"},
            }
        ),
    )
    base.update(overrides)
    n = Notification(**base)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.mark.parametrize(
    ("lang", "action", "expected_label"),
    [
        ("fa", SmartNotificationAction.ACK_THANKS.value, "متوجه شدم، ممنون"),
        ("en", SmartNotificationAction.NOT_NOW.value, "Not now"),
        ("ar", SmartNotificationAction.TALK_LATER.value, "نتحدث لاحقًا"),
        ("fa", SmartNotificationAction.OPEN_CHAT.value, "صحبت کنیم"),
    ],
)
def test_inbox_metadata_canonical_actions_localized(client, db, lang, action, expected_label):
    u = _create_user(db, f"InboxLang_{lang}", lang=lang)
    _create_notification(db, u.id, language=lang)

    response = client.get(
        f"/notifications/unread?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    meta = response.json()["data"]["notifications"][0]["gate4_metadata"]
    actions = {item["action_id"]: item["label"] for item in meta["actions"]}
    assert set(actions) == set(V1_DEFAULT_ACTIONS)
    assert actions[action] == expected_label
    assert get_action_label(action, lang) == expected_label


def test_inbox_metadata_source_notification_id_and_deeplink(client, db):
    u = _create_user(db, "InboxDeeplink")
    n = _create_notification(db, u.id, deeplink_url=None)

    response = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    meta = response.json()["data"]["notifications"][0]["gate4_metadata"]
    assert meta["notification_id"] == n.id
    assert meta["source_notification_id"] == n.id
    assert meta["deeplink_url"] == f"sedi://chat?from=notif&source_notification_id={n.id}"


def test_inbox_metadata_preserves_legacy_deeplink(client, db):
    u = _create_user(db, "InboxLegacyLink")
    legacy = "sedi://chat?from=notif&id=42"
    _create_notification(db, u.id, deeplink_url=legacy)

    response = client.get(
        f"/notifications/unread?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    meta = response.json()["data"]["notifications"][0]["gate4_metadata"]
    assert meta["deeplink_url"] == legacy


def test_inbox_metadata_excludes_context_json_and_internal_payloads(client, db):
    u = _create_user(db, "InboxPrivacy")
    _create_notification(db, u.id)

    response = client.get(
        f"/notifications/unread?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    notif = response.json()["data"]["notifications"][0]
    assert "context_json" not in notif
    assert "gate4_metadata" in notif
    meta = notif["gate4_metadata"]
    meta_serialized = json.dumps(meta)
    assert "body" not in meta
    assert "context_json" not in meta
    assert "diagnosis" not in meta_serialized
    assert "dosage" not in meta_serialized
    assert "raw_payload" not in meta_serialized
    assert meta["contract_version"] == GATE4_CONTRACT_VERSION


def test_list_and_unread_return_same_gate4_metadata_shape(client, db):
    u = _create_user(db, "InboxConsistency")
    _create_notification(db, u.id, channel="health_alert")

    list_resp = client.get(
        f"/notifications/?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    unread_resp = client.get(
        f"/notifications/unread?user_id={u.id}",
        headers=_auth_header(u.id),
    )
    list_meta = list_resp.json()["data"]["notifications"][0]["gate4_metadata"]
    unread_meta = unread_resp.json()["data"]["notifications"][0]["gate4_metadata"]
    assert list_meta == unread_meta
    assert list_resp.json()["data"]["notifications"][0]["channel"] == "health_alert"


def test_inbox_cross_user_isolation(client, db):
    user_a = _create_user(db, "InboxA")
    user_b = _create_user(db, "InboxB")
    secret = _create_notification(db, user_b.id, title="B only")

    response = client.get(
        f"/notifications/unread?user_id={user_a.id}",
        headers=_auth_header(user_a.id),
    )
    ids = [n["id"] for n in response.json()["data"]["notifications"]]
    assert secret.id not in ids
