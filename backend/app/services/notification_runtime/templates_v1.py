# backend.app.services.notification_runtime.templates_v1
"""
Notifications V1 templates registry (code-controlled).

Templates are versioned and include FA + EN texts. Contract-compatible type/priority.
Dedup key format: {template_key}:{user_id}:{YYYY-MM-DD}.
"""

from typing import Any, Dict, List, Optional

# Backend payload type (NotificationPayload); contract uses type + priority
BACKEND_TYPE_COMPANION = "connection_ping"
BACKEND_TYPE_HEALTH = "health_alert"

DEFAULT_ACTIONS_JSON = '[{"id":"like","type":"LIKE"},{"id":"dislike","type":"DISLIKE"},{"id":"open_chat","type":"OPEN_CHAT"}]'

TEMPLATES_V1: List[Dict[str, Any]] = [
    {
        "key": "companion_daily_checkin_v1",
        "version": 1,
        "channel": "companion",
        "type": BACKEND_TYPE_COMPANION,
        "priority": "normal",
        "texts": {
            "fa": {
                "title": "سلام",
                "message": "یک لحظه سراغت اومدم؛ امروز حالت چطوره؟ 🌿",
            },
            "en": {
                "title": "Hello",
                "message": "Just checking in — how are you feeling today? 🌿",
            },
        },
        "actions_json": DEFAULT_ACTIONS_JSON,
        "meta": {"tone_version": 1, "template_key": "companion_daily_checkin_v1"},
    },
    {
        "key": "companion_encourage_move_v1",
        "version": 1,
        "channel": "companion",
        "type": BACKEND_TYPE_COMPANION,
        "priority": "normal",
        "texts": {
            "fa": {
                "title": "تحرک",
                "message": "یه قدم کوچیک بردار؛ بدنت ممنون میشه. 💚",
            },
            "en": {
                "title": "Move a little",
                "message": "Take a small step; your body will thank you. 💚",
            },
        },
        "actions_json": DEFAULT_ACTIONS_JSON,
        "meta": {"tone_version": 1, "template_key": "companion_encourage_move_v1"},
    },
    {
        "key": "companion_breathing_break_v1",
        "version": 1,
        "channel": "companion",
        "type": BACKEND_TYPE_COMPANION,
        "priority": "normal",
        "texts": {
            "fa": {
                "title": "وقت نفس",
                "message": "یه دقیقه نفس عمیق بکش؛ آروم میشی. 🌬",
            },
            "en": {
                "title": "Breathing break",
                "message": "Take a minute to breathe deeply; you'll feel calmer. 🌬",
            },
        },
        "actions_json": DEFAULT_ACTIONS_JSON,
        "meta": {"tone_version": 1, "template_key": "companion_breathing_break_v1"},
    },
    {
        "key": "health_alert_generic_v1",
        "version": 1,
        "channel": "health_alert",
        "type": BACKEND_TYPE_HEALTH,
        "priority": "high",
        "texts": {
            "fa": {
                "title": "هشدار سلامت",
                "message": "یک قرائت غیرمعمول ثبت شد. برای بررسی، صدی رو باز کن.",
            },
            "en": {
                "title": "Health Alert",
                "message": "An unusual reading was detected. Open Sedi to review.",
            },
        },
        "actions_json": DEFAULT_ACTIONS_JSON,
        "meta": {"tone_version": 1, "template_key": "health_alert_generic_v1"},
    },
]


def get_template_v1(key: str) -> Optional[Dict[str, Any]]:
    """Return template dict by key or None."""
    for t in TEMPLATES_V1:
        if t.get("key") == key:
            return dict(t)
    return None


def list_templates_v1() -> List[Dict[str, Any]]:
    """Return list of templates with key, version, channel, type, priority (no full texts)."""
    out: List[Dict[str, Any]] = []
    for t in TEMPLATES_V1:
        out.append({
            "key": t.get("key"),
            "version": t.get("version"),
            "channel": t.get("channel"),
            "type": t.get("type"),
            "priority": t.get("priority"),
        })
    return out


def validate_templates_v1() -> List[str]:
    """
    Validate all templates. Returns list of error messages; empty list if valid.
    Raises nothing; callers may raise if errors non-empty.
    """
    errors: List[str] = []
    required = ("key", "version", "channel", "type", "priority", "texts")
    for t in TEMPLATES_V1:
        if not isinstance(t, dict):
            errors.append(f"Template is not a dict: {t!r}")
            continue
        for r in required:
            if r not in t:
                errors.append(f"Template {t.get('key', '?')} missing field: {r}")
        if "texts" in t and isinstance(t["texts"], dict):
            for lang, block in t["texts"].items():
                if not isinstance(block, dict):
                    errors.append(f"Template {t.get('key')} texts.{lang} is not a dict")
                else:
                    if "message" not in block and "body" not in block:
                        errors.append(f"Template {t.get('key')} texts.{lang} missing message/body")
                    if "title" not in block:
                        errors.append(f"Template {t.get('key')} texts.{lang} missing title")
    return errors
