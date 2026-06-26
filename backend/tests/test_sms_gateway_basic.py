# backend/tests/test_sms_gateway_basic.py – SMS gateway factory (no network)
import pytest

from backend.app.services.sms_gateway import get_otp_message, get_sms_sender
from backend.app.services.sms_gateway.dummy_sender import DummySmsSender
from backend.app.services.sms_gateway.mediana_sender import MedianaSmsSender
from backend.app.services.sms_gateway.unsupported_sender import UnsupportedSmsSender


def test_get_otp_message_variants():
    """EN / FA / AR and fallback to FA."""
    assert "Sedi verification code:" in get_otp_message("123456", "en")
    assert "123456" in get_otp_message("123456", "en")
    assert "کد تایید صدی:" in get_otp_message("123456", "fa")
    assert "123456" in get_otp_message("123456", "fa")
    assert "رمز التحقق من صدي:" in get_otp_message("123456", "ar")
    assert "123456" in get_otp_message("123456", "ar")
    assert "کد تایید صدی:" in get_otp_message("123456", "fr")
    assert "کد تایید صدی:" in get_otp_message("123456", "")
    assert "کد تایید صدی:" in get_otp_message("123456", "en-US")


def test_factory_unknown_returns_unsupported_when_sms_enabled(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "unknown-provider")
    monkeypatch.setenv("SMS_DISABLED", "false")
    sender = get_sms_sender()
    assert isinstance(sender, UnsupportedSmsSender)


def test_factory_legacy_kavenegar_returns_unsupported_when_sms_enabled(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "kavenegar")
    monkeypatch.setenv("SMS_DISABLED", "false")
    sender = get_sms_sender()
    assert isinstance(sender, UnsupportedSmsSender)
    result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert "not supported" in (result.error or "").lower()


def test_factory_unknown_returns_dummy_when_sms_disabled(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "kavenegar")
    monkeypatch.setenv("SMS_DISABLED", "true")
    sender = get_sms_sender()
    assert isinstance(sender, DummySmsSender)


def test_factory_default_is_mediana(monkeypatch):
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    monkeypatch.setenv("SMS_DISABLED", "false")
    sender = get_sms_sender()
    assert isinstance(sender, MedianaSmsSender)
