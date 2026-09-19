"""Shared OTP helpers for backend tests after LOGIN/REGISTRATION split.

LOGIN never creates users. Tests that need a fresh authenticated user must
register via purpose=REGISTRATION.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from backend.app.services import auth_otp_service as svc


def issue_access_token(
    client: Any,
    db: Any,
    monkeypatch: Any,
    phone: str,
    *,
    code: str = "123456",
) -> str:
    """Create account via REGISTRATION OTP and return access_token."""
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value=code):
        ok, err, _ = svc.request_otp(
            db, phone, purpose=svc.OTP_PURPOSE_REGISTRATION
        )
        assert ok, err
    body = client.post(
        "/auth/verify_otp",
        json={"phone": phone, "code": code, "purpose": "REGISTRATION"},
    ).json()
    assert body.get("ok") is True, body
    token = (body.get("data") or {}).get("access_token")
    assert token, body
    return token
