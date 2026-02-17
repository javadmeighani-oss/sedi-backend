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


def _normalize_lang(lang: str | None) -> str:
    """Tests expect 'en-US' to fallback to FA (not treated as EN). Only en, fa, ar exact."""
    if lang in ("en", "fa", "ar"):
        return lang
    return "fa"


def get_otp_message(code: str, lang: str | None) -> str:
    """EN/AR/FA by _normalize_lang (en-US -> fa)."""
    l = _normalize_lang(lang)
    if l == "en":
        return f"Sedi verification code: {code}"
    if l == "ar":
        return f"رمز التحقق من صدي: {code}"
    return f"کد تایید صدی: {code}"
