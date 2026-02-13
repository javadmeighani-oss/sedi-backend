# app/services/sms_gateway – Provider-agnostic SMS
from backend.app.services.sms_gateway.base import (
    SmsSendResult,
    SmsSender,
    get_otp_message,
)
from backend.app.services.sms_gateway.factory import get_sms_sender

__all__ = [
    "SmsSendResult",
    "SmsSender",
    "get_otp_message",
    "get_sms_sender",
]
