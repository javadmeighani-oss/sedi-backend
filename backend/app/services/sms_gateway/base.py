# app/services/sms_gateway/base.py – Provider-agnostic SMS interface
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class SmsSendResult:
    ok: bool
    provider: str
    message_id: Optional[str] = None
    error: Optional[str] = None


class SmsSender(Protocol):
    def send_otp(self, phone: str, code: str, lang: str) -> SmsSendResult:
        ...


def get_otp_message(code: str, lang: str) -> str:
    """EN: startswith('en'), AR: startswith('ar'), else FA (default)."""
    if not lang:
        lang = "fa"
    lang = (lang or "").strip().lower()
    if lang.startswith("en"):
        return f"Sedi verification code: {code}"
    if lang.startswith("ar"):
        return f"رمز التحقق من صدي: {code}"
    return f"کد تایید صدی: {code}"
