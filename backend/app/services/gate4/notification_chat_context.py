"""
Gate 4-C — Safe notification context for chat restoration.

Builds an internal-only dict for ConversationBrain. Never returned to clients.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from backend.app.models import Notification
from backend.app.services.gate4.notification_context import (
    resolve_effective_category,
    resolve_effective_risk_level,
    sanitize_notification_context,
)

_MAX_SUMMARY_CHARS = 200


def build_safe_chat_context(notification: Notification) -> dict[str, Any]:
    """
    Build sanitized notification context for internal GPT prompt injection.

    Never includes raw context_json, PII, diagnosis, dosage, or medication-change data.
    """
    parsed_context: Optional[Mapping[str, Any]] = None
    if notification.context_json:
        try:
            loaded = json.loads(notification.context_json)
            if isinstance(loaded, dict):
                parsed_context = loaded
        except (json.JSONDecodeError, TypeError):
            parsed_context = None

    context_hints = sanitize_notification_context(parsed_context) or {}

    category = resolve_effective_category(
        category=notification.category,
        notification_type=notification.type or "",
        context_json=notification.context_json,
    )
    risk_level = resolve_effective_risk_level(
        risk_level=notification.risk_level,
        priority=notification.priority or "normal",
    )

    title = (notification.title or "").strip()[:_MAX_SUMMARY_CHARS]
    body = (notification.body or "").strip()[:_MAX_SUMMARY_CHARS]

    result: dict[str, Any] = {
        "category": category,
        "risk_level": risk_level,
    }

    if notification.template_key:
        result["template_key"] = str(notification.template_key)[:100]
    if notification.source_type:
        result["source_type"] = str(notification.source_type)[:64]
    if notification.source_id:
        result["source_id"] = str(notification.source_id)[:255]
    if context_hints:
        result["context_hints"] = context_hints
    if title:
        result["notification_title"] = title
    if body:
        result["notification_summary"] = body

    return result
