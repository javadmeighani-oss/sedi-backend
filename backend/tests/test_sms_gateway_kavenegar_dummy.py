# backend/tests/test_sms_gateway_kavenegar_dummy.py – Stage 25 Step 2.2 SMS gateway
import os
import pytest
from unittest.mock import patch

os.environ.setdefault("SMS_PROVIDER", "dummy")

from backend.app.services.sms_gateway import get_sms_sender, get_otp_message
from backend.app.services.sms_gateway.base import SmsSendResult
from backend.app.services.sms_gateway.dummy_sender import DummySmsSender, send_otp as dummy_send_otp
from backend.app.services.sms_gateway.kavenegar_sender import KavenegarSmsSender


def test_dummy_sender_always_succeeds_without_network():
    """Dummy provider returns ok=True and message_id=dummy; no network call."""
    result = dummy_send_otp("+989121234567", "123456", "fa")
    assert result.ok is True
    assert result.provider == "dummy"
    assert result.message_id == "dummy"
    assert result.error is None

    sender = DummySmsSender()
    result2 = sender.send_otp("+989199999999", "654321", "en")
    assert result2.ok is True
    assert result2.provider == "dummy"


def test_provider_selection_by_env_dummy(monkeypatch):
    """SMS_PROVIDER=dummy returns DummySmsSender."""
    monkeypatch.setenv("SMS_PROVIDER", "dummy")
    # Factory reads os.environ at call time
    sender = get_sms_sender()
    assert isinstance(sender, DummySmsSender)


def test_provider_selection_by_env_kavenegar(monkeypatch):
    """SMS_PROVIDER=kavenegar returns KavenegarSmsSender."""
    monkeypatch.setenv("SMS_PROVIDER", "kavenegar")
    monkeypatch.setenv("KAVENEGAR_API_KEY", "test-key")
    sender = get_sms_sender()
    assert isinstance(sender, KavenegarSmsSender)


def test_get_otp_message_lang():
    """OTP message varies by lang; fallback to fa."""
    assert "123456" in get_otp_message("123456", "en")
    assert "Sedi verification" in get_otp_message("123456", "en")
    assert "کد تایید صدی" in get_otp_message("123456", "fa")
    assert "رمز التحقق" in get_otp_message("123456", "ar")
    assert "کد تایید صدی" in get_otp_message("111", "unknown")  # fallback -> FA


def test_kavenegar_returns_error_when_api_key_missing():
    """Kavenegar sender returns ok=False when KAVENEGAR_API_KEY not set; no network call."""
    sender = KavenegarSmsSender(api_key="")
    result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert result.provider == "kavenegar"
    assert "API_KEY" in (result.error or "")
