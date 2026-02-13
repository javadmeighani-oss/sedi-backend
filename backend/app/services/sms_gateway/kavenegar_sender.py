# app/services/sms_gateway/kavenegar_sender.py – Kavenegar REST API
import os
import logging
from typing import Optional

import requests

from backend.app.services.sms_gateway.base import SmsSendResult, get_otp_message

logger = logging.getLogger(__name__)

KAVENEGAR_BASE = "https://api.kavenegar.com/v1"
TIMEOUT = 10


class KavenegarSmsSender:
    def __init__(
        self,
        api_key: Optional[str] = None,
        sender: Optional[str] = None,
    ):
        self.api_key = (api_key or os.environ.get("KAVENEGAR_API_KEY", "")).strip()
        self.sender = (sender or os.environ.get("KAVENEGAR_SENDER", "")).strip() or None

    def send_otp(self, phone: str, code: str, lang: str) -> SmsSendResult:
        if not self.api_key:
            return SmsSendResult(
                ok=False,
                provider="kavenegar",
                error="KAVENEGAR_API_KEY not set",
            )
        message = get_otp_message(code, lang)
        url = f"{KAVENEGAR_BASE}/{self.api_key}/sms/send.json"
        params = {"receptor": phone, "message": message}
        if self.sender:
            params["sender"] = self.sender
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            if r.status_code != 200:
                return SmsSendResult(
                    ok=False,
                    provider="kavenegar",
                    error=f"HTTP {r.status_code}",
                )
            data = r.json()
            if not isinstance(data, dict):
                return SmsSendResult(
                    ok=False,
                    provider="kavenegar",
                    error="Invalid response format",
                )
            ret = data.get("return") or {}
            if ret.get("status") != 200:
                return SmsSendResult(
                    ok=False,
                    provider="kavenegar",
                    error=ret.get("message") or str(ret),
                )
            message_id = None
            entries = data.get("entries") or []
            if entries and isinstance(entries[0], dict):
                mid = entries[0].get("messageid")
                message_id = str(mid) if mid is not None else None
            return SmsSendResult(
                ok=True,
                provider="kavenegar",
                message_id=message_id,
            )
        except requests.Timeout:
            logger.warning("Kavenegar SMS timeout for %s", phone)
            return SmsSendResult(ok=False, provider="kavenegar", error="Timeout")
        except Exception as e:
            logger.warning("Kavenegar SMS error: %s", e)
            return SmsSendResult(ok=False, provider="kavenegar", error=str(e))
