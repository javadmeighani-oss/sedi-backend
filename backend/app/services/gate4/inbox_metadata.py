"""
Gate 4 — Safe inbox metadata for notification list/unread API responses.

Builds a privacy-safe subset of the canonical Gate 4 contract. No DB writes.
"""

from __future__ import annotations

from typing import Any

from backend.app.models import Notification
from backend.app.services.gate4.notification_context import (
    resolve_effective_category,
    resolve_effective_risk_level,
)
from backend.app.services.gate4.notification_contract import (
    build_smart_notification_metadata,
    normalize_language,
)
from backend.app.services.gate4.push_payload import build_gate4_deeplink


def _is_valid_persisted_deeplink(url: str | None) -> bool:
    if not url or not str(url).strip():
        return False
    return str(url).strip().startswith("sedi://")


def build_safe_inbox_metadata(notif: Notification) -> dict[str, Any]:
    """
    Build safe Gate 4 metadata for inbox API responses.

    Never includes notification body, context_json, raw source payloads, or PII.
    """
    category = resolve_effective_category(
        category=notif.category,
        notification_type=notif.type or "",
        context_json=notif.context_json,
    )
    risk = resolve_effective_risk_level(
        risk_level=notif.risk_level,
        priority=notif.priority or "normal",
    )
    language = normalize_language(notif.language or "en")

    deeplink = notif.deeplink_url if _is_valid_persisted_deeplink(notif.deeplink_url) else None
    if deeplink is None:
        deeplink = build_gate4_deeplink(source_notification_id=notif.id)

    full = build_smart_notification_metadata(
        notification_id=notif.id,
        category=category,
        risk=risk,
        language=language,
        source_notification_id=notif.id,
        deeplink_url=deeplink,
    )

    return {
        "contract_version": full["contract_version"],
        "notification_id": full["notification_id"],
        "source_notification_id": notif.id,
        "category": full["category"],
        "risk": full["risk"],
        "language": full["language"],
        "deeplink_url": full["deeplink_url"],
        "actions": [
            {"action_id": action["action_id"], "label": action["label"]}
            for action in full["actions"]
        ],
    }
