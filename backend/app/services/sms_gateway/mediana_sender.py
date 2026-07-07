# app/services/sms_gateway/mediana_sender.py – Mediana OTP pattern API
import logging
import os
import re
from typing import Any, Optional

import requests

from backend.app.services.sms_gateway.base import SmsSendResult

logger = logging.getLogger(__name__)

MEDIANA_OTP_URL = "https://api.mediana.ir/sms/v1/send/otp"
TIMEOUT = 10
_IR_MOBILE_RE = re.compile(r"^09\d{9}$")


def to_iran_mobile_recipient(phone: str) -> str:
    """Normalize stored phone (+98… / 98… / 09…) to Mediana recipient format 09xxxxxxxxx."""
    s = (phone or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("+98") and len(s) >= 13:
        return "0" + s[3:]
    if s.startswith("98") and len(s) >= 12:
        return "0" + s[2:]
    return s


class MedianaSmsSender:
    def __init__(
        self,
        api_key: Optional[str] = None,
        pattern_code: Optional[str] = None,
    ):
        self.api_key = (api_key or os.environ.get("MEDIANA_API_KEY", "")).strip()
        self.pattern_code = (
            pattern_code or os.environ.get("MEDIANA_OTP_PATTERN_CODE", "")
        ).strip()

    def send_otp(self, phone: str, code: str, lang: str) -> SmsSendResult:
        del lang  # Mediana OTP pattern carries message text; lang not used here.
        if not self.api_key:
            return SmsSendResult(
                ok=False,
                provider="mediana",
                error="MEDIANA_API_KEY not set",
            )
        if not self.pattern_code:
            return SmsSendResult(
                ok=False,
                provider="mediana",
                error="MEDIANA_OTP_PATTERN_CODE not set",
            )

        recipient = to_iran_mobile_recipient(phone)
        if not _IR_MOBILE_RE.match(recipient):
            return SmsSendResult(
                ok=False,
                provider="mediana",
                error="Invalid Iranian mobile number for Mediana recipient",
            )

        payload = {
            "patternCode": self.pattern_code,
            "recipient": recipient,
            "otpCode": code,
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
        }
        try:
            r = requests.post(
                MEDIANA_OTP_URL,
                json=payload,
                headers=headers,
                timeout=TIMEOUT,
            )
            if r.status_code not in (200, 201):
                return SmsSendResult(
                    ok=False,
                    provider="mediana",
                    error=f"HTTP {r.status_code}",
                )
            data = r.json() if r.content else {}
            if not isinstance(data, dict):
                return SmsSendResult(
                    ok=False,
                    provider="mediana",
                    error="Invalid response format",
                )
            err = self._extract_error(data)
            if err:
                return SmsSendResult(ok=False, provider="mediana", error=err)
            message_id = self._extract_message_id(data)
            return SmsSendResult(
                ok=True,
                provider="mediana",
                message_id=message_id,
            )
        except requests.Timeout:
            logger.warning("Mediana OTP SMS timeout for %s", recipient[:4] + "***")
            return SmsSendResult(ok=False, provider="mediana", error="Timeout")
        except Exception as e:
            logger.warning("Mediana OTP SMS error: %s", e)
            return SmsSendResult(ok=False, provider="mediana", error=str(e))

    @staticmethod
    def _is_accepted_in_progress_message(message: str) -> bool:
        """
        Mediana may return a human-readable Persian message that indicates the request
        was accepted / queued (e.g. "در حال ساخت") without returning a bulk_id.

        This must be treated as success ONLY when there are no explicit failure indicators.
        """
        if not message:
            return False
        normalized = message.strip()
        return normalized == "در حال ساخت"

    @staticmethod
    def _has_success_indicators(data: dict[str, Any]) -> bool:
        """True when Mediana response includes delivery identifiers or explicit success flags."""
        if data.get("success") is True:
            return True

        # Accepted/queued signal via message text (no bulk_id). Only when no explicit error fields exist.
        msg = data.get("message")
        if isinstance(msg, str) and MedianaSmsSender._is_accepted_in_progress_message(msg):
            if data.get("success") is False:
                return False
            status = data.get("status")
            if isinstance(status, str) and status.strip().lower() in ("error", "failed", "fail"):
                return False
            if isinstance(data.get("error"), str) and str(data.get("error")).strip():
                return False
            if data.get("errors"):
                return False
            return True

        status = data.get("status")
        if isinstance(status, str):
            normalized = status.strip().lower()
            if normalized in ("success", "ok", "sent", "delivered", "queued"):
                return True
        if isinstance(status, int) and status in (1, 200):
            return True

        if MedianaSmsSender._extract_message_id(data) is not None:
            return True

        nested = data.get("data")
        if isinstance(nested, dict) and MedianaSmsSender._has_success_indicators(nested):
            return True

        return False

    @staticmethod
    def _extract_error(data: dict[str, Any]) -> Optional[str]:
        if MedianaSmsSender._has_success_indicators(data):
            return None

        if data.get("success") is False:
            return str(data.get("message") or data.get("error") or "Mediana request failed")

        status = data.get("status")
        if isinstance(status, str) and status.lower() in ("error", "failed", "fail"):
            return status

        for key in ("error", "errors"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if val and key == "errors":
                return str(val)

        message = data.get("message")
        if isinstance(message, str) and message.strip():
            normalized = message.strip().lower()
            if normalized not in ("ok", "success"):
                return message.strip()

        nested = data.get("data")
        if isinstance(nested, dict):
            nested_error = MedianaSmsSender._extract_error(nested)
            if nested_error:
                return nested_error

        return None

    @staticmethod
    def _extract_message_id(data: dict[str, Any]) -> Optional[str]:
        for key in ("bulk_id", "bulkId", "id", "trackingId", "messageId"):
            val = data.get(key)
            if val is not None:
                return str(val)
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ("bulk_id", "bulkId", "id", "trackingId", "messageId"):
                val = nested.get(key)
                if val is not None:
                    return str(val)
        return None
