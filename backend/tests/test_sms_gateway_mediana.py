# backend/tests/test_sms_gateway_mediana.py – Mediana OTP SMS gateway
import pytest
from unittest.mock import MagicMock, patch

from backend.app.services.sms_gateway import get_sms_sender
from backend.app.services.sms_gateway.mediana_sender import (
    MedianaSmsSender,
    to_iran_mobile_recipient,
)


def test_to_iran_mobile_recipient_normalizes_e164():
    assert to_iran_mobile_recipient("+989121234567") == "09121234567"
    assert to_iran_mobile_recipient("989121234567") == "09121234567"
    assert to_iran_mobile_recipient("09121234567") == "09121234567"


def test_provider_selection_by_env_mediana(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "mediana")
    monkeypatch.setenv("MEDIANA_API_KEY", "test-key")
    monkeypatch.setenv("MEDIANA_OTP_PATTERN_CODE", "test-pattern")
    sender = get_sms_sender()
    assert isinstance(sender, MedianaSmsSender)


def test_mediana_returns_error_when_api_key_missing():
    sender = MedianaSmsSender(api_key="", pattern_code="test-pattern")
    result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert result.provider == "mediana"
    assert "API_KEY" in (result.error or "")


def test_mediana_returns_error_when_pattern_code_missing():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="")
    result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert result.provider == "mediana"
    assert "PATTERN" in (result.error or "")


def test_mediana_returns_error_for_invalid_recipient():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    result = sender.send_otp("12345", "123456", "fa")
    assert result.ok is False
    assert "Invalid Iranian mobile" in (result.error or "")


def test_mediana_send_otp_success():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"bulk_id":"track-1"}'
    mock_response.json.return_value = {"bulk_id": "track-1"}
    with patch("requests.post", return_value=mock_response) as mock_post:
        result = sender.send_otp("+989121234567", "123456", "fa")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["patternCode"] == "test-pattern"
        assert call_kwargs["json"]["recipient"] == "09121234567"
        assert call_kwargs["json"]["otpCode"] == "123456"
        assert call_kwargs["headers"]["X-API-KEY"] == "test-key"
    assert result.ok is True
    assert result.provider == "mediana"
    assert result.message_id == "track-1"


def test_mediana_send_otp_http_error():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.content = b'{"message":"unauthorized"}'
    mock_response.json.return_value = {"message": "unauthorized"}
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert "401" in (result.error or "")
