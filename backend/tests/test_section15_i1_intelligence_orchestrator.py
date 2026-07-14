"""Section 15-I1 — Connected Intelligence Orchestrator foundation tests."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.app.models import Notification, User
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.interaction import InteractionResponse
from backend.app.services.intelligence.contracts import (
    CONTRACT_VERSION,
    STAGE_ORDER,
    ReasonCode,
)
from backend.app.services.intelligence.feature_flags import (
    intelligence_orchestrator_v1_enabled,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.headers = {"Accept-Language": "en"}
    return request


@pytest.fixture
def user(db):
    u = User(name="I1 Orch User", secret_key="i1a", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user_b(db):
    u = User(name="I1 Orch User B", secret_key="i1b", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def notification_for_user(db, user):
    n = Notification(
        user_id=user.id,
        type="companion",
        title="Safe title",
        body="RAW HEALTH BODY MUST NOT ENTER CONTRACT",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
        category="health",
        risk_level="low",
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _legacy_ok(**_kwargs):
    def _gen(user_id, user_message, user_name=None, *, notification_context=None):
        return {"message": f"echo:{user_message}", "language": "en"}

    return _gen


# ---------------------------------------------------------------------------
# Feature flag defaults
# ---------------------------------------------------------------------------


def test_orchestrator_flag_default_is_false(monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    assert intelligence_orchestrator_v1_enabled() is False


def test_flag_off_uses_compatibility_mode(monkeypatch):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=None,
    )
    # structured_mode=None reads env (false) → compatibility
    result = orch.process(
        authenticated_user_id=1,
        message="hello",
        language="en",
    )
    assert result.rollout_mode == "compatibility"
    assert ReasonCode.COMPATIBILITY_GENERATOR_SELECTED.value in result.reason_codes
    assert ReasonCode.STRUCTURED_MODE_ACTIVE.value not in result.reason_codes


def test_flag_on_uses_structured_mode_without_claiming_future_capabilities(monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    orch = IntelligenceOrchestrator(legacy_generator=_legacy_ok())
    result = orch.process(
        authenticated_user_id=1,
        message="hello",
        language="en",
    )
    assert result.rollout_mode == "structured"
    assert ReasonCode.STRUCTURED_MODE_ACTIVE.value in result.reason_codes
    assert ReasonCode.COMPATIBILITY_GENERATOR_SELECTED.value in result.reason_codes
    joined = " ".join(result.reason_codes).lower()
    assert "nutrition" not in joined
    assert "weekly_kb" not in joined
    assert "durable_memory" not in joined
    assert "missing_info" not in joined


# ---------------------------------------------------------------------------
# Deterministic stages / contract
# ---------------------------------------------------------------------------


def test_deterministic_stage_order_and_safe_reason_codes():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    result = orch.process(
        authenticated_user_id=42,
        message="secret message content",
        language="en",
    )
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    allowed = {c.value for c in ReasonCode}
    for code in result.reason_codes:
        assert code in allowed
    assert result.contract_version == CONTRACT_VERSION
    assert result.request_id
    assert ReasonCode.CTX_INITIALIZED.value in result.reason_codes
    assert ReasonCode.IDENTITY_FROM_JWT.value in result.reason_codes
    assert ReasonCode.LANGUAGE_NORMALIZED.value in result.reason_codes
    assert ReasonCode.LEGACY_GENERATION_COMPLETED.value in result.reason_codes
    assert ReasonCode.RESPONSE_VALIDATED.value in result.reason_codes
    assert ReasonCode.ORCHESTRATION_COMPLETED.value in result.reason_codes


def test_trace_excludes_raw_user_message_and_user_id():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    secret = "UNIQUE_PII_TOKEN_XYZ"
    result = orch.process(
        authenticated_user_id=777001,
        message=secret,
        language="en",
    )
    blob = " ".join(result.reason_codes + list(result.stage_names) + [result.request_id])
    assert secret not in blob
    assert "777001" not in blob
    assert "UNIQUE_PII" not in blob


def test_request_id_server_generated_and_unique():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    a = orch.process(authenticated_user_id=1, message="a", language="en")
    b = orch.process(authenticated_user_id=1, message="b", language="en")
    assert a.request_id != b.request_id
    assert len(a.request_id) >= 32


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("fa", "fa"),
        ("FA", "fa"),
        ("ar", "ar"),
        ("en-US", "en"),
        ("xx", "en"),
        ("", "en"),
        ("invalid-lang", "en"),
    ],
)
def test_language_normalization(raw, expected):
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="hi",
        language=raw,
    )
    assert result.language == expected
    assert ReasonCode.LANGUAGE_NORMALIZED.value in result.reason_codes


def test_timezone_unavailable_safe_reason():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="hi",
        language="en",
        timezone="Not/ARealZone",
    )
    assert ReasonCode.TIMEZONE_UNAVAILABLE.value in result.reason_codes


def test_timezone_available_safe_reason():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="hi",
        language="en",
        timezone="Asia/Tehran",
    )
    assert ReasonCode.TIMEZONE_AVAILABLE.value in result.reason_codes


def test_notification_origin_uses_safe_ids_only():
    captured = {}

    def gen(user_id, user_message, user_name=None, *, notification_context=None):
        captured["notification_context"] = notification_context
        return {"message": "ok", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
    result = orch.process(
        authenticated_user_id=5,
        message="hi",
        language="en",
        conversation_id="c-1",
        interaction_source="notification",
        source_notification_id=99,
        notification_context={
            "category": "health",
            "body": "RAW BODY",
            "context_json": "{\"hr\": 120}",
            "risk_level": "low",
        },
    )
    assert ReasonCode.NOTIFICATION_CONTEXT_VERIFIED.value in result.reason_codes
    assert captured["notification_context"] is not None
    assert "body" not in captured["notification_context"]
    assert "context_json" not in captured["notification_context"]
    blob = " ".join(result.reason_codes + list(result.stage_names))
    assert "RAW BODY" not in blob
    assert "hr" not in blob


def test_notification_absent_reason():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    result = orch.process(authenticated_user_id=1, message="hi", language="en")
    assert ReasonCode.NOTIFICATION_CONTEXT_ABSENT.value in result.reason_codes


# ---------------------------------------------------------------------------
# Failure / no-bypass
# ---------------------------------------------------------------------------


def test_empty_generator_output_fails_safely():
    def empty_gen(*_a, **_k):
        return {"message": "   ", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=empty_gen, structured_mode=False)
    from backend.app.services.intelligence.contracts import OrchestrationError

    with pytest.raises(OrchestrationError) as exc:
        orch.process(authenticated_user_id=1, message="hi", language="en")
    assert exc.value.error_code == "empty_generation"


def test_generator_exception_does_not_invoke_second_brain_call():
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("simulated_generator_failure")

    orch = IntelligenceOrchestrator(legacy_generator=boom, structured_mode=False)
    with pytest.raises(RuntimeError):
        orch.process(authenticated_user_id=1, message="hi", language="en")
    assert calls["n"] == 1


def test_legacy_generator_invoked_exactly_once():
    calls = {"n": 0}

    def once(*_a, **_k):
        calls["n"] += 1
        return {"message": "once", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=once, structured_mode=False)
    result = orch.process(authenticated_user_id=1, message="hi", language="en")
    assert calls["n"] == 1
    assert result.message == "once"


# ---------------------------------------------------------------------------
# Concurrency / request scope
# ---------------------------------------------------------------------------


def test_two_users_do_not_share_state():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
    )
    a = orch.process(authenticated_user_id=11, message="A", language="en")
    b = orch.process(authenticated_user_id=22, message="B", language="fa")
    assert a.request_id != b.request_id
    assert a.message == "echo:A"
    assert b.message == "echo:B"
    assert a.language == "en"
    assert b.language == "fa"


def test_concurrent_requests_do_not_share_stage_traces():
    barrier = threading.Barrier(2)
    results = {}

    def worker(uid: int, msg: str):
        def gen(user_id, user_message, user_name=None, *, notification_context=None):
            barrier.wait(timeout=5)
            return {"message": f"u{user_id}:{user_message}", "language": "en"}

        local = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
        results[uid] = local.process(
            authenticated_user_id=uid,
            message=msg,
            language="en",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(worker, 101, "one")
        f2 = pool.submit(worker, 202, "two")
        f1.result(timeout=10)
        f2.result(timeout=10)

    assert results[101].request_id != results[202].request_id
    assert results[101].message == "u101:one"
    assert results[202].message == "u202:two"
    assert results[101].stage_names == results[202].stage_names


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_chat_path_invokes_orchestrator_and_preserves_message(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    from backend.app.routers.interact import chat
    from backend.app.services.intelligence.contracts import OrchestrationResult

    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator"
    ) as OrchCls:
        instance = OrchCls.return_value
        instance.process.return_value = OrchestrationResult(
            message="canonical reply",
            language="en",
            request_id="req-test",
            contract_version=CONTRACT_VERSION,
            rollout_mode="compatibility",
            reason_codes=(ReasonCode.ORCHESTRATION_COMPLETED.value,),
            stage_names=tuple(s.value for s in STAGE_ORDER),
            detected_name=None,
        )
        payload = ChatRequest(message="hello there")
        resp = asyncio.run(chat(mock_request, payload, db, user))
        assert isinstance(resp, InteractionResponse)
        assert resp.message == "canonical reply"
        assert resp.user_id == user.id
        assert resp.language == "en"
        assert isinstance(resp.timestamp, datetime)
        OrchCls.assert_called_once()
        instance.process.assert_called_once()
        kwargs = instance.process.call_args.kwargs
        assert kwargs["authenticated_user_id"] == user.id
        assert kwargs["message"] == "hello there"
        mock_process.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_router_does_not_call_brain_directly_outside_orchestrator(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    """End-to-end through real orchestrator: brain called exactly once via adapter."""
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_process.return_value = {"message": "via brain", "language": "en"}
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="ping")
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert resp.message == "via brain"
    assert mock_process.call_count == 1
    # Authenticated identity from JWT user, not body
    assert mock_process.call_args.args[0] == user.id


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_caller_user_id_cannot_replace_jwt_identity(
    mock_cmd, mock_reminder, mock_process, db, user, user_b, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_process.return_value = {"message": "ok", "language": "en"}
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="hi", user_id=user_b.id)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(mock_request, payload, db, user))
    assert exc.value.status_code == 403
    mock_process.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={
        "created": False,
        "reason": "needs_clarification",
        "clarification_message": "Please include a date and time for your reminder.",
    },
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_reminder_short_circuit_still_bypasses_orchestrator_generation(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    from backend.app.routers.interact import chat

    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process"
    ) as mock_orch:
        payload = ChatRequest(message="remind me to call the doctor")
        resp = asyncio.run(chat(mock_request, payload, db, user))
        assert resp.message == "Please include a date and time for your reminder."
        mock_process.assert_not_called()
        mock_orch.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
def test_settings_short_circuit_still_bypasses_orchestrator(
    mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    override = MagicMock()
    override.assistant_message = "Timezone updated."
    from backend.app.routers.interact import chat

    with patch(
        "backend.app.services.chat_commands.detect_and_handle_user_settings_command",
        return_value=override,
    ), patch(
        "backend.app.core.conversation.memory.ConversationMemory.save_conversation",
        return_value=None,
    ), patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process"
    ) as mock_orch:
        payload = ChatRequest(message="set timezone Asia/Tehran")
        resp = asyncio.run(chat(mock_request, payload, db, user))
        assert resp.message == "Timezone updated."
        mock_process.assert_not_called()
        mock_orch.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_flag_off_still_invokes_orchestrator_compatibility(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "false")
    mock_process.return_value = {"message": "compat", "language": "en"}
    from backend.app.routers.interact import chat

    assert intelligence_orchestrator_v1_enabled() is False
    payload = ChatRequest(message="hello")
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert resp.message == "compat"
    # Flag OFF still routes through orchestrator → legacy generator exactly once.
    assert mock_process.call_count == 1


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_generator_exception_no_direct_brain_fallback(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_process.side_effect = RuntimeError("boom")
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="hello")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(mock_request, payload, db, user))
    # Outer router maps non-GPT RuntimeError to 500 (or 502 if GPT-classified).
    assert exc.value.status_code in (500, 502)
    assert mock_process.call_count == 1


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_notification_continuation_single_event_and_safe_context(
    mock_cmd, mock_reminder, mock_process, db, user, notification_for_user, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_process.return_value = {"message": "Continuing", "language": "en"}
    from backend.app.models import InteractionEvent
    from backend.app.routers.interact import chat

    payload = ChatRequest(
        message="let's talk",
        source_notification_id=notification_for_user.id,
        conversation_id="c-42",
        interaction_source="notification",
    )
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert resp.message == "Continuing"
    assert resp.continued_from_notification is True
    assert resp.source_notification_id == notification_for_user.id
    assert mock_process.call_count == 1
    nctx = mock_process.call_args.kwargs.get("notification_context") or {}
    assert "body" not in nctx
    assert "RAW HEALTH" not in str(nctx)
    events = (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.event_type == "chat_message",
        )
        .all()
    )
    assert len(events) == 1


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command", return_value=None)
def test_empty_brain_output_does_not_return_empty_success(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request, monkeypatch
):
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    mock_process.return_value = {"message": "", "language": "en"}
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="hello")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat(mock_request, payload, db, user))
    assert exc.value.status_code == 500
    assert mock_process.call_count == 1


def test_no_external_network_in_unit_orchestration(monkeypatch):
    """Injected generator only — prove no ConversationBrain construction."""
    monkeypatch.delenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", raising=False)
    with patch(
        "backend.app.services.intelligence.orchestrator.ConversationBrain"
    ) as Brain:
        orch = IntelligenceOrchestrator(
            legacy_generator=_legacy_ok(),
            structured_mode=False,
        )
        orch.process(authenticated_user_id=1, message="hi", language="en")
        Brain.assert_not_called()
