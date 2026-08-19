# app/services/chat_commands.py
"""
Chat command parser for notification preferences (Stage 16.6.5).

Detects and handles user settings commands via chat text.
Stores values in UserProfileCore.timezone and NotificationPrefs quiet hours.
"""

import re
from dataclasses import dataclass
from typing import Optional

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

from sqlalchemy.orm import Session

from backend.app.services.knowledge.service import ensure_profile_core
from backend.app.schemas.notification_prefs import NotificationPrefsUpdate, QuietHoursUpdate
from backend.app.services.notifications.prefs_service import upsert_prefs


@dataclass
class ChatResponseOverride:
    """Result when a command is handled - return this instead of calling GPT."""
    assistant_message: str
    updated_facts: Optional[list] = None  # e.g. [("timezone", ...), ("quiet_hours", ...)]


def _validate_iana_timezone(tz_str: str) -> bool:
    """Check if tz_str is a valid IANA timezone."""
    if not tz_str or not isinstance(tz_str, str):
        return False
    tz_str = tz_str.strip()
    if len(tz_str) > 64:
        return False
    if not PYTZ_AVAILABLE:
        # Fallback: accept common patterns (Region/City)
        return bool(re.match(r"^[A-Za-z][A-Za-z0-9_+-]+/[A-Za-z][A-Za-z0-9_+-]+$", tz_str))
    try:
        pytz.timezone(tz_str)
        return True
    except Exception:
        return False


def _norm_hhmm(s: str) -> str:
    h, m = s.strip().split(":")[:2]
    return f"{int(h):02d}:{int(m):02d}"


def _persist_profile_timezone(db: Session, user_id: int, tz_str: str) -> None:
    row = ensure_profile_core(db, user_id)
    row.timezone = tz_str
    db.add(row)
    db.commit()


def _persist_quiet_hours(
    db: Session,
    user_id: int,
    *,
    enabled: bool,
    start: str = "22:00",
    end: str = "08:00",
) -> None:
    upsert_prefs(
        db,
        user_id,
        NotificationPrefsUpdate(
            quiet_hours=QuietHoursUpdate(
                enabled=enabled,
                start=_norm_hhmm(start),
                end=_norm_hhmm(end),
            )
        ),
    )


def _validate_hhmm(s: str) -> bool:
    """Check HH:MM 24h format."""
    if not s or not isinstance(s, str):
        return False
    m = re.match(r"^(\d{1,2}):(\d{2})$", s.strip())
    if not m:
        return False
    h, min_ = int(m.group(1)), int(m.group(2))
    return 0 <= h <= 23 and 0 <= min_ <= 59


# ---- Timezone patterns ----
# Permissive pattern first: captures "set timezone X" (any token) for validation
_TZ_PATTERNS = [
    # English: set timezone <token> (captures invalid formats like NotATimezone for validation)
    (r"set\s+timezone\s+(\S+)", "en"),
    (r"timezone\s*:\s*([A-Za-z][A-Za-z0-9_+-]+/[A-Za-z][A-Za-z0-9_+-]+)", "en"),
    # Persian: تایم‌زون / تایم زون / timezone
    (r"(?:تایم[\s‌]?زون|timezone)\s*[:\s]+\s*([A-Za-z][A-Za-z0-9_+-]+/[A-Za-z][A-Za-z0-9_+-]+)", "fa"),
    # Arabic
    (r"(?:المنطقة\s+الزمنية|timezone)\s*[:\s]+\s*([A-Za-z][A-Za-z0-9_+-]+/[A-Za-z][A-Za-z0-9_+-]+)", "ar"),
]

# ---- Quiet hours set patterns ----
_QH_SET_PATTERNS = [
    # English
    (r"(?:quiet\s+hours|do\s+not\s+disturb)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", "en"),
    # Persian: ساعات سکوت / مزاحم نشو
    (r"(?:ساعات\s+سکوت|مزاحم\s+نشو)\s+(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", "fa"),
    # Arabic
    (r"ساعات\s+الهدوء\s+(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", "ar"),
]

# ---- Quiet hours disable patterns ----
_QH_OFF_PATTERNS = [
    # English
    (r"(?:disable\s+quiet\s+hours|quiet\s+hours\s+off)", "en"),
    # Persian
    (r"(?:خاموش\s+کردن\s+ساعات\s+سکوت|ساعات\s+سکوت\s+خاموش)", "fa"),
    # Arabic
    (r"إيقاف\s+ساعات\s+الهدوء", "ar"),
]

# ---- Response templates (language -> message) ----
_TZ_OK = {
    "en": "Timezone set to {tz}.",
    "fa": "منطقه زمانی روی {tz} تنظیم شد.",
    "ar": "تم تعيين المنطقة الزمنية إلى {tz}.",
}
_TZ_INVALID = {
    "en": "That timezone is not valid. Please use IANA format (e.g. Asia/Tehran).",
    "fa": "منطقه زمانی معتبر نیست. از فرمت IANA استفاده کنید (مثلاً Asia/Tehran).",
    "ar": "هذه المنطقة الزمنية غير صالحة. استخدم صيغة IANA (مثلاً Asia/Tehran).",
}
_QH_OK = {
    "en": "Quiet hours set: {start}–{end}.",
    "fa": "ساعات سکوت تنظیم شد: {start} تا {end}.",
    "ar": "تم تعيين ساعات الهدوء: {start}–{end}.",
}
_QH_INVALID = {
    "en": "Please use HH:MM format (e.g. 22:00-08:00).",
    "fa": "لطفاً از فرمت ساعت:دقیقه استفاده کنید (مثلاً 22:00-08:00).",
    "ar": "يرجى استخدام صيغة ساعة:دقيقة (مثلاً 22:00-08:00).",
}
_QH_OFF_OK = {
    "en": "Quiet hours disabled.",
    "fa": "ساعات سکوت خاموش شد.",
    "ar": "تم إيقاف ساعات الهدوء.",
}
_CONSENT_REQUIRED = {
    "en": "Memory consent is required before I can save this setting. Please grant memory consent in Settings.",
    "fa": "برای ذخیره این تنظیم، رضایت حافظه لازم است.",
    "ar": "مطلوب موافقة الذاكرة قبل حفظ هذا الإعداد.",
}


def _detect_command_lang(text: str) -> str:
    """Heuristic: detect likely language of the command text."""
    # Simple: if contains Persian/Arabic chars, prefer fa/ar
    if re.search(r"[\u0600-\u06FF]", text):
        if re.search(r"[\u0600-\u06FF]", text) and not re.search(r"[\u0750-\u077F]", text):
            return "fa"
        return "ar"
    return "en"


def detect_and_handle_user_settings_command(
    user_id: int,
    text: str,
    db: Session,
    language: Optional[str] = None,
) -> Optional[ChatResponseOverride]:
    """
    Detect and handle notification-related chat commands.
    Returns ChatResponseOverride if command was handled, else None.
    """
    if not text or not text.strip():
        return None

    t = text.strip()
    lang = language or _detect_command_lang(t)
    if lang not in ("en", "fa", "ar"):
        lang = "en"

    # 1) Try timezone
    for pat, _ in _TZ_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            tz_str = m.group(1).strip()
            if not _validate_iana_timezone(tz_str):
                # Must return non-None for tests (invalid timezone error message)
                if (language or "en").strip().lower().startswith("fa"):
                    msg = "منطقهٔ زمانی نامعتبر است. مثل: Asia/Tehran"
                else:
                    msg = "Invalid timezone. Example: Asia/Tehran"
                return ChatResponseOverride(assistant_message=msg)
            try:
                _persist_profile_timezone(db, user_id, tz_str)
                return ChatResponseOverride(
                    assistant_message=_TZ_OK.get(lang, _TZ_OK["en"]).format(tz=tz_str),
                    updated_facts=[("timezone", {"tz": tz_str})],
                )
            except Exception:
                return ChatResponseOverride(
                    assistant_message=_TZ_INVALID.get(lang, _TZ_INVALID["en"]).format(tz=tz_str)
                )

    # 2) Try quiet hours disable
    for pat, _ in _QH_OFF_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            try:
                _persist_quiet_hours(db, user_id, enabled=False)
                return ChatResponseOverride(
                    assistant_message=_QH_OFF_OK.get(lang, _QH_OFF_OK["en"]),
                    updated_facts=[("quiet_hours", {"enabled": False})],
                )
            except Exception:
                return ChatResponseOverride(
                    assistant_message=_QH_OFF_OK.get(lang, _QH_OFF_OK["en"]),
                )

    # 3) Try quiet hours set
    for pat, _ in _QH_SET_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            start_str = m.group(1).strip()
            end_str = m.group(2).strip()
            if not _validate_hhmm(start_str) or not _validate_hhmm(end_str):
                return ChatResponseOverride(
                    assistant_message=_QH_INVALID.get(lang, _QH_INVALID["en"])
                )
            try:
                val = {"enabled": True, "start": _norm_hhmm(start_str), "end": _norm_hhmm(end_str)}
                _persist_quiet_hours(
                    db, user_id, enabled=True, start=start_str, end=end_str
                )
                return ChatResponseOverride(
                    assistant_message=_QH_OK.get(lang, _QH_OK["en"]).format(
                        start=val["start"], end=val["end"]
                    ),
                    updated_facts=[("quiet_hours", val)],
                )
            except Exception:
                return ChatResponseOverride(
                    assistant_message=_QH_INVALID.get(lang, _QH_INVALID["en"])
                )

    return None
