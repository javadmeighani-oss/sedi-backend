# app/services/sms_gateway – Provider-agnostic SMS (patch target: backend.app.services.sms_gateway)
import os
from backend.app.services.sms_gateway.base import (
    SmsSendResult,
    SmsSender,
    _normalize_lang,
    get_otp_message,
)
from backend.app.services.sms_gateway.factory import get_sms_sender


def send_otp(phone: str, code: str, lang: str | None) -> bool:
    """Gate: if SMS_DISABLED=true -> do NOT call provider."""
    if os.environ.get("SMS_DISABLED", "").lower() in ("1", "true", "yes", "on"):
        return False
    sender = get_sms_sender()
    result = sender.send_otp(phone, code, (lang or "fa")[:10])
    return getattr(result, "ok", bool(result))


__all__ = [
    "SmsSendResult",
    "SmsSender",
    "_normalize_lang",
    "get_otp_message",
    "get_sms_sender",
    "send_otp",
]
