# app/services/sms_gateway/factory.py
import os
from typing import cast

from backend.app.services.sms_gateway.base import SmsSender
from backend.app.services.sms_gateway.dummy_sender import DummySmsSender
from backend.app.services.sms_gateway.kavenegar_sender import KavenegarSmsSender


def get_sms_sender() -> SmsSender:
    """Read env SMS_PROVIDER (default kavenegar). Unknown -> DummySmsSender."""
    provider = (os.environ.get("SMS_PROVIDER") or "kavenegar").strip().lower()
    if provider == "kavenegar":
        return cast(SmsSender, KavenegarSmsSender())
    if provider == "dummy":
        return cast(SmsSender, DummySmsSender())
    return cast(SmsSender, DummySmsSender())
