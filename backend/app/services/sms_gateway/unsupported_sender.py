# app/services/sms_gateway/unsupported_sender.py – retired/unknown SMS providers
from backend.app.services.sms_gateway.base import SmsSendResult


class UnsupportedSmsSender:
    def __init__(self, provider: str):
        self.provider_name = (provider or "unknown").strip().lower() or "unknown"

    def send_otp(self, phone: str, code: str, lang: str) -> SmsSendResult:
        del phone, code, lang
        return SmsSendResult(
            ok=False,
            provider=self.provider_name,
            error=(
                f"SMS_PROVIDER '{self.provider_name}' is not supported; "
                "use 'mediana' or set SMS_DISABLED=true for dev"
            ),
        )
