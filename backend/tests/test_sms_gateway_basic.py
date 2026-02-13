# backend/tests/test_sms_gateway_basic.py – SMS gateway (no network)
import os
import pytest
from unittest.mock import patch

from backend.app.services.sms_gateway import get_otp_message, get_sms_sender
from backend.app.services.sms_gateway.base import SmsSendResult
from backend.app.services.sms_gateway.dummy_sender import DummySmsSender
from backend.app.services.sms_gateway.kavenegar_sender import KavenegarSmsSender


def test_get_otp_message_variants():
    """EN / FA / AR and fallback to FA."""
    assert "Sedi verification code:" in get_otp_message("123456", "en")
    assert "123456" in get_otp_message("123456", "en")
    assert "کد تایید صدی:" in get_otp_message("123456", "fa")
    assert "123456" in get_otp_message("123456", "fa")
    assert "رمز التحقق من صدي:" in get_otp_message("123456", "ar")
    assert "123456" in get_otp_message("123456", "ar")
    # fallback (unknown lang) -> FA
    assert "کد تایید صدی:" in get_otp_message("123456", "fr")
    assert "کد تایید صدی:" in get_otp_message("123456", "")
    assert "کد تایید صدی:" in get_otp_message("123456", "en-US")


def test_factory_unknown_falls_back_to_dummy(monkeypatch):
    """Unknown SMS_PROVIDER returns DummySmsSender."""
    monkeypatch.setenv("SMS_PROVIDER", "unknown")
    sender = get_sms_sender()
    assert isinstance(sender, DummySmsSender)


def test_kavenegar_missing_api_key_returns_error():
    """Missing KAVENEGAR_API_KEY returns ok=False; no HTTP call."""
    sender = KavenegarSmsSender(api_key="")
    with patch("requests.get") as mock_get:
        result = sender.send_otp("+989121234567", "123456", "fa")
        mock_get.assert_not_called()
    assert result.ok is False
    assert result.provider == "kavenegar"
    assert "API_KEY" in (result.error or "")
