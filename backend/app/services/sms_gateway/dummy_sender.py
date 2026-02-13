# app/services/sms_gateway/dummy_sender.py
from backend.app.services.sms_gateway.base import SmsSendResult


def send_otp(phone: str, code: str, lang: str) -> SmsSendResult:
    """Standalone dummy send (no network)."""
    return SmsSendResult(ok=True, provider="dummy", message_id="dummy")


class DummySmsSender:
    def send_otp(self, phone: str, code: str, lang: str) -> SmsSendResult:
        return send_otp(phone, code, lang)
