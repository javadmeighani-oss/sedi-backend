# app/services/sms_gateway/factory.py
import os
from typing import cast

from backend.app.services.sms_gateway.base import SmsSender
from backend.app.services.sms_gateway.dummy_sender import DummySmsSender
from backend.app.services.sms_gateway.mediana_sender import MedianaSmsSender
from backend.app.services.sms_gateway.unsupported_sender import UnsupportedSmsSender


def _sms_disabled() -> bool:
    return os.environ.get("SMS_DISABLED", "").strip().lower() in ("1", "true", "yes")


def get_sms_sender() -> SmsSender:
    """Read env SMS_PROVIDER (default mediana). Legacy/unknown fail unless SMS_DISABLED."""
    provider = (os.environ.get("SMS_PROVIDER") or "mediana").strip().lower()
    if provider == "mediana":
        return cast(SmsSender, MedianaSmsSender())
    if provider == "dummy":
        return cast(SmsSender, DummySmsSender())
    if _sms_disabled():
        return cast(SmsSender, DummySmsSender())
    return cast(SmsSender, UnsupportedSmsSender(provider))
