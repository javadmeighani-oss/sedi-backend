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


def test_mediana_send_otp_success_with_non_ok_message_text():
    """Mediana may return bulk_id plus a human-readable message on success."""
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"bulk_id":"track-2","message":"OTP sent successfully"}'
    mock_response.json.return_value = {
        "bulk_id": "track-2",
        "message": "OTP sent successfully",
    }
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is True
    assert result.message_id == "track-2"


def test_mediana_send_otp_success_with_persian_success_message():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"bulkId":"track-3","message":"\\u0639\\u0645\\u0644\\u06cc\\u0627\\u062a \\u0645\\u0648\\u0641\\u0642"}'
    mock_response.json.return_value = {
        "bulkId": "track-3",
        "message": "عملیات موفق",
    }
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is True
    assert result.message_id == "track-3"


def test_mediana_send_otp_success_with_nested_data_payload():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"data":{"bulk_id":"track-4","message":"queued"}}'
    mock_response.json.return_value = {
        "data": {"bulk_id": "track-4", "message": "queued"},
    }
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is True
    assert result.message_id == "track-4"


def test_mediana_send_otp_failure_when_message_without_success_indicators():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"message":"invalid pattern code"}'
    mock_response.json.return_value = {"message": "invalid pattern code"}
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert "invalid pattern code" in (result.error or "")


def test_mediana_send_otp_failure_when_success_false():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"success":false,"message":"provider rejected"}'
    mock_response.json.return_value = {"success": False, "message": "provider rejected"}
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
    assert "provider rejected" in (result.error or "")


def test_mediana_send_otp_success_when_message_is_in_progress_without_bulk_id():
    """
    Regression: production logs show Mediana may return a message like "در حال ساخت"
    while the OTP SMS is still delivered. Treat this as accepted/queued success
    only when no explicit error fields exist.
    """
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"message":"\\u062f\\u0631 \\u062d\\u0627\\u0644 \\u0633\\u0627\\u062e\\u062a"}'
    mock_response.json.return_value = {"message": "در حال ساخت"}
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is True
    assert result.provider == "mediana"


def test_mediana_in_progress_message_still_fails_when_success_false():
    sender = MedianaSmsSender(api_key="test-key", pattern_code="test-pattern")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b'{"success":false,"message":"\\u062f\\u0631 \\u062d\\u0627\\u0644 \\u0633\\u0627\\u062e\\u062a"}'
    mock_response.json.return_value = {"success": False, "message": "در حال ساخت"}
    with patch("requests.post", return_value=mock_response):
        result = sender.send_otp("+989121234567", "123456", "fa")
    assert result.ok is False
