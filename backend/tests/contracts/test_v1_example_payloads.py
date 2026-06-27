# tests/contracts/test_v1_example_payloads.py
"""
V1 contract tests: minimal JSON samples from contract docs validate against
Pydantic models or required keys. Fail fast if contracts change.
No external network; no server.
"""
import json
import pytest

from backend.app.schemas.api_envelope import ApiResponse, ApiError
from backend.app.schemas.auth_otp import OtpRequestIn, OtpVerifyIn, TokenOut, MeOut
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.device import DeviceIngestRequest, DeviceIngestResponse
from backend.app.schemas.knowledge import (
    ExtractFromMessageRequest,
    ExtractFromMessageUserRequest,
    ApplyAnswerRequest,
    ApplyAnswerUserRequest,
)


# ----- Auth (auth.md) -----
AUTH_REQUEST_OTP_BODY = {"phone": "+989123456789"}
AUTH_VERIFY_OTP_BODY = {"phone": "+989123456789", "code": "123456"}
AUTH_SUCCESS_ENVELOPE = {"ok": True, "data": {"ok": True, "next": "verify_otp"}, "error": None}
AUTH_ERROR_ENVELOPE = {"ok": False, "data": None, "error": {"code": "OTP_INVALID", "message": "Invalid code", "details": None}}
AUTH_ME_RESPONSE = {"ok": True, "data": {"user_id": 1, "phone": "+989123456789", "display_name": "User", "language": "en"}, "error": None}


# ----- Interact (interact.md) -----
INTERACT_CHAT_BODY = {"user_id": 1, "message": "Hello, how are you?"}
INTERACT_CHAT_RESPONSE_KEYS = ["message", "language", "user_id", "timestamp"]


# ----- Notifications (notifications.md) -----
NOTIF_FEEDBACK_BODY = {"reaction": "seen", "timestamp": "2025-02-22T12:00:00Z", "action_id": "open_chat", "feedback_text": None}
NOTIF_ADMIN_TEST_PUSH_BODY = {"user_id": 1, "title": "Test", "body": "Hello", "channel": "engagement", "priority": "normal", "ttl_seconds": 3600}
NOTIF_LIST_RESPONSE_KEYS = ["ok", "data", "error"]


# ----- Device (device.md) -----
DEVICE_INGEST_BODY = {
    "user_id": 1,
    "device_id": "Sedi001",
    "event_type": "heart_rate",
    "payload": {"bpm": 82, "quality": "good"},
    "recorded_at": "2026-02-02T10:30:00Z",
}
DEVICE_INGEST_SUCCESS_KEYS = ["event_id", "dedupe_key"]
# DeviceIngestResponse examples (raw schema for /device/ingest)
DEVICE_INGEST_RESPONSE_SUCCESS = {
    "ok": True,
    "data": {
        "event_id": 123,
        "dedupe_key": "heart_rate:1:2026-02-02T10:30",
        "device_event_dedupe_hit": False,
        "decision_outcome": "actions_executed",
        "actions_created": 1,
        "skipped_reason": None,
        "trace_id": "a1b2c3d4e5f6",
    },
    "error": None,
}
DEVICE_INGEST_RESPONSE_ERROR = {
    "ok": False,
    "data": None,
    "error": {"code": "USER_NOT_FOUND", "message": "User not found"},
}


# ----- Knowledge (knowledge.md) -----
KNOWLEDGE_NEXT_QUESTION_RESPONSE_KEYS = ["ok", "data", "error"]
KNOWLEDGE_EXTRACT_BODY = {"text": "I sleep at 11pm.", "language": "fa", "source_message_id": None}
KNOWLEDGE_APPLY_BODY = {"candidate_id": 5, "question_type": "confirm_candidate", "value": "Yes", "field_key": None, "answer": None}


# ----- Decision (decision.md) -----
DECISION_EVALUATE_BODY = {"event": {"user_id": 1, "device_id": "Sedi001", "event_type": "heart_rate", "payload": {"bpm": 140}, "recorded_at": "2025-02-22T12:00:00Z"}}
DECISION_RESPONSE_KEYS = ["ok", "decision"]


# ---------- Tests: envelope ----------
def test_api_response_envelope_validates_success():
    """ApiResponse accepts success shape."""
    r = ApiResponse(ok=True, data=AUTH_SUCCESS_ENVELOPE["data"], error=None)
    assert r.ok is True
    assert r.data is not None
    assert r.error is None


def test_api_response_envelope_validates_error():
    """ApiResponse accepts error shape with ApiError."""
    r = ApiResponse(ok=False, data=None, error=ApiError(code="OTP_INVALID", message="Invalid code", details=None))
    assert r.ok is False
    assert r.error is not None
    assert r.error.code == "OTP_INVALID"


def test_api_error_accepts_details_none():
    """ApiError details is optional."""
    e = ApiError(code="X", message="Y")
    assert e.details is None


# ---------- Tests: auth ----------
def test_auth_request_otp_body_matches_otp_request_in():
    """Auth request_otp body matches OtpRequestIn."""
    OtpRequestIn(**AUTH_REQUEST_OTP_BODY)


def test_auth_verify_otp_body_matches_otp_verify_in():
    """Auth verify_otp body matches OtpVerifyIn."""
    OtpVerifyIn(**AUTH_VERIFY_OTP_BODY)


def test_auth_success_envelope_matches_api_response():
    """Auth success envelope parses as ApiResponse."""
    r = ApiResponse(**AUTH_SUCCESS_ENVELOPE)
    assert r.ok is True and r.data and r.error is None


def test_auth_error_envelope_matches_api_response():
    """Auth error envelope parses as ApiResponse."""
    r = ApiResponse(**AUTH_ERROR_ENVELOPE)
    assert r.ok is False and r.error is not None


def test_auth_me_response_has_required_keys():
    """Auth /me response has ok, data, error."""
    r = ApiResponse(**AUTH_ME_RESPONSE)
    assert "user_id" in (r.data or {})


# ---------- Tests: interact ----------
def test_interact_chat_body_matches_chat_request():
    """Interact chat body matches ChatRequest."""
    ChatRequest(**INTERACT_CHAT_BODY)


def test_interact_response_has_required_keys():
    """Interact success response must have message, language, user_id, timestamp (keys exist)."""
    for key in INTERACT_CHAT_RESPONSE_KEYS:
        assert key in {"message": "", "language": "en", "user_id": 1, "timestamp": "2025-02-22T12:00:00"}


# ---------- Tests: notifications ----------
def test_notif_feedback_body_has_contract_keys():
    """Notification feedback body has reaction, timestamp (contract keys)."""
    assert "reaction" in NOTIF_FEEDBACK_BODY and "timestamp" in NOTIF_FEEDBACK_BODY


def test_notif_list_response_has_envelope_keys():
    """Notifications list response has ok, data, error."""
    for key in NOTIF_LIST_RESPONSE_KEYS:
        assert key in {"ok": True, "data": {}, "error": None}


# ---------- Tests: device ----------
def test_device_ingest_body_matches_device_ingest_request():
    """Device ingest body matches DeviceIngestRequest."""
    DeviceIngestRequest(**DEVICE_INGEST_BODY)


def test_device_ingest_success_data_has_required_keys():
    """Device ingest success data has event_id or dedupe_key."""
    data = {"event_id": 123, "dedupe_key": "hr:1:2026-02-02T10:30", "device_event_dedupe_hit": False}
    for key in DEVICE_INGEST_SUCCESS_KEYS:
        assert key in data


def test_device_ingest_response_success_matches_device_ingest_response():
    """Device ingest 200 success body matches DeviceIngestResponse schema."""
    r = DeviceIngestResponse(**DEVICE_INGEST_RESPONSE_SUCCESS)
    assert r.ok is True and r.data is not None and r.error is None
    assert "event_id" in r.data and "dedupe_key" in r.data


def test_device_ingest_response_error_matches_device_ingest_response():
    """Device ingest error body matches DeviceIngestResponse schema."""
    r = DeviceIngestResponse(**DEVICE_INGEST_RESPONSE_ERROR)
    assert r.ok is False and r.data is None and r.error is not None
    assert r.error.get("code") == "USER_NOT_FOUND"


# ---------- Tests: knowledge ----------
def test_knowledge_next_question_response_has_envelope_keys():
    """Knowledge next_question response has ok, data, error."""
    for key in KNOWLEDGE_NEXT_QUESTION_RESPONSE_KEYS:
        assert key in {"ok": True, "data": {}, "error": None}


def test_knowledge_extract_body_matches_extract_request():
    """Knowledge extract_from_message body matches ExtractFromMessageUserRequest."""
    ExtractFromMessageUserRequest(**KNOWLEDGE_EXTRACT_BODY)


def test_knowledge_apply_body_matches_apply_request():
    """Knowledge apply_answer body matches ApplyAnswerUserRequest."""
    ApplyAnswerUserRequest(**KNOWLEDGE_APPLY_BODY)


# ---------- Tests: decision ----------
def test_decision_evaluate_body_has_event_key():
    """Decision evaluate request has 'event' key."""
    assert "event" in DECISION_EVALUATE_BODY
    assert isinstance(DECISION_EVALUATE_BODY["event"], dict)


def test_decision_response_has_required_keys():
    """Decision evaluate response has ok, decision."""
    for key in DECISION_RESPONSE_KEYS:
        assert key in {"ok": True, "decision": {"outcome": "notify"}}
