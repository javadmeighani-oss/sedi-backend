"""Section 15-I4 — Deterministic safety/risk engine, router bypass, orchestrator, brain tests.

WRITE-ONLY package: tests are authored here; execution is not authorized in this package.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models import Notification, User
from backend.app.schemas.chat import ChatRequest
from backend.app.schemas.interaction import InteractionResponse
from backend.app.services.gate3 import emergency_templates as gate3_templates
from backend.app.services.intelligence.contracts import (
    STAGE_ORDER,
    OrchestrationError,
    PostGenerationSafetyStatus,
    ReasonCode,
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
    SafetyConstraints,
    StageName,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.safety_risk import (
    REGISTRY_VERSION,
    assess_safety_risk,
    assess_safety_risk_safe,
    build_safety_response,
    list_template_strings,
    requires_terminal_safety_response,
    structured_caution_constraints,
    validate_generated_response,
)


_PROHIBITED_EMERGENCY_NUMBER_RE = re.compile(
    r"(?:\b115\b)|(?:۱۱۵)|(?:911)|(?:999)|(?:112)",
)


def _legacy_ok():
    def _gen(
        user_id,
        user_message,
        user_name=None,
        *,
        notification_context=None,
        structured_context_projection=None,
        structured_preferred_name=None,
        use_structured_context=False,
        use_intelligence_safety=False,
        safety_constraints=None,
        **_kwargs,
    ):
        return {"message": f"echo:{user_message}", "language": "en"}

    return _gen


def _stub_assembler():
    from backend.app.services.intelligence.context_types import (
        CompatibilityProjection,
        ContextSnapshot,
        ContextSection,
    )

    class _Stub:
        def assemble(
            self,
            db,
            *,
            authenticated_user_id,
            request_id,
            notification_context=None,
            source_notification_id=None,
        ):
            return ContextSnapshot(
                request_id=request_id,
                owner_user_id=authenticated_user_id,
                sections={
                    n: ContextSection(name=n, empty_reason="no_data")  # type: ignore[arg-type]
                    for n in ("profile", "lifestyle", "health", "memory", "notification")
                },
                items=[],
                preferred_name=None,
                conflict_count=0,
                truncated_count=0,
                reason_codes=(ReasonCode.CONTEXT_ASSEMBLED.value,),
                adapter_order=("profile", "lifestyle", "health", "memory", "notification"),
            )

        def build_compatibility_projection(self, snapshot):
            return CompatibilityProjection(
                text="[STRUCTURED_CONTEXT]",
                item_count=0,
                char_count=len("[STRUCTURED_CONTEXT]"),
                truncated=False,
                excluded_conflict_count=0,
                preferred_name=None,
            )

    return _Stub()


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.headers = {"Accept-Language": "en"}
    return request


@pytest.fixture
def user(db):
    u = User(name="I4 Safety User", secret_key="i4a", preferred_language="en")
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
        body="RAW HEALTH BODY MUST NOT ENTER SAFETY ASSESSMENT",
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


# A. Classifier


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("I have severe chest pain right now", "en"),
        ("درد قفسه سینه شدید دارم", "fa"),
        ("لدي الم في الصدر شديد", "ar"),
    ],
)
def test_classifier_medical_emergency_fa_ar_en(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.EMERGENCY
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert a.domain is RiskDomain.MEDICAL_EMERGENCY
    assert a.rule_id.startswith("i4.rule.")
    assert msg not in a.rule_id
    assert a.registry_version == REGISTRY_VERSION


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("I want to kill myself", "en"),
        ("میخوام خودکشی میکنم", "fa"),
        ("ساقتل نفسي", "ar"),
    ],
)
def test_classifier_self_harm_crisis_fa_ar_en(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("I overdosed on pills just now", "en"),
        ("زیادی قرص خوردم و اوردوز کردم", "fa"),
        ("تناولت جرعة زائدة من الحبوب", "ar"),
    ],
)
def test_classifier_overdose_fa_ar_en(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.OVERDOSE_MEDICATION


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("I am having anaphylaxis and severe allergic reaction", "en"),
        ("شوک آلرژیک دارم الان", "fa"),
        ("لدي تفاعل تحسسي شديد وحساسية مفرطة", "ar"),
    ],
)
def test_classifier_severe_allergy_fa_ar_en(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SEVERE_ALLERGY


@pytest.mark.parametrize(
    "msg",
    [
        "What are the symptoms of a heart attack?",
        "What does overdose mean?",
        "Explain severe allergy.",
        "علائم حمله قلبی چیست؟",
        "ما معنى الجرعة الزائدة؟",
    ],
)
def test_classifier_informational_negatives_none(msg):
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


def test_classifier_denial_and_conceptual():
    denied = assess_safety_risk(
        message="I am not suicidal and I do not want to kill myself, just asking definitions",
        language="en",
    )
    assert denied.level is RiskLevel.NONE or denied.domain is not RiskDomain.SELF_HARM_CRISIS
    info = assess_safety_risk(message="what is suicide", language="en")
    assert info.level is RiskLevel.NONE


def test_cannot_breathe_not_suppressed():
    a = assess_safety_risk(message="I cannot breathe", language="en")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.MEDICAL_EMERGENCY


def test_boundary_substring_cases():
    assert assess_safety_risk(message="chartpainhelper notes", language="en").level is RiskLevel.NONE
    assert (
        assess_safety_risk(message="please help chest pain now", language="en").level
        is RiskLevel.EMERGENCY
    )


def test_rule_ids_contain_no_raw_fragments():
    secret = "UNIQUE_FRAGMENT_XYZ_9911"
    a = assess_safety_risk(message=f"I have chest pain and {secret}", language="en")
    blob = " ".join([a.rule_id, a.domain.value, a.level.value, a.action.value])
    assert secret not in blob
    assert "chest pain" not in blob


def test_classifier_failure_maps_to_fail_closed_not_risk_level():
    with patch(
        "backend.app.services.intelligence.safety_risk.assess_safety_risk",
        side_effect=RuntimeError("x"),
    ):
        closed = assess_safety_risk_safe(message="hi", language="en")
    assert closed.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert closed.level is RiskLevel.NONE
    assert closed.rule_id == "i4.rule.classifier_failed.v1"


# B. Router bypass


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command")
def test_emergency_before_reminder_side_effect(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request
):
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="I cannot breathe and need help")
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert isinstance(resp, InteractionResponse)
    assert "emergency" in resp.message.lower()
    mock_reminder.assert_not_called()
    mock_cmd.assert_not_called()
    mock_process.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command")
def test_emergency_before_settings_handler(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request
):
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="I want to kill myself")
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert resp.detected_name is None
    mock_cmd.assert_not_called()
    mock_process.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch(
    "backend.app.services.chat_commands.detect_and_handle_user_settings_command",
    return_value=None,
)
def test_emergency_before_notification_event_write(
    mock_cmd, mock_reminder, mock_process, db, user, notification_for_user, mock_request
):
    from backend.app.models import InteractionEvent
    from backend.app.routers.interact import chat

    payload = ChatRequest(
        message="severe allergic reaction anaphylaxis now",
        source_notification_id=notification_for_user.id,
        conversation_id="c-em",
        interaction_source="notification",
    )
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert isinstance(resp, InteractionResponse)
    events = (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.event_type == "chat_message",
        )
        .all()
    )
    assert len(events) == 0
    mock_process.assert_not_called()


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch(
    "backend.app.services.chat_commands.detect_and_handle_user_settings_command",
    return_value=None,
)
def test_normal_reminder_and_settings_unchanged(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request
):
    mock_process.return_value = {"message": "normal-ok", "language": "en"}
    from backend.app.routers.interact import chat

    payload = ChatRequest(message="remind me nothing urgent hello")
    resp = asyncio.run(chat(mock_request, payload, db, user))
    assert resp.message == "normal-ok"
    mock_reminder.assert_called_once()
    mock_cmd.assert_called_once()
    mock_process.assert_called_once()


@patch(
    "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder",
    return_value={"created": False, "reason": "ok"},
)
@patch(
    "backend.app.services.chat_commands.detect_and_handle_user_settings_command",
    return_value=None,
)
def test_safety_engine_exactly_once_on_normal_path(
    mock_cmd, mock_reminder, db, user, mock_request
):
    calls = {"n": 0}

    def counting_assess(*, message, language):
        calls["n"] += 1
        return assess_safety_risk_safe(message=message, language=language)

    with patch(
        "backend.app.services.intelligence.orchestrator.assess_safety_risk_safe",
        side_effect=counting_assess,
    ), patch(
        "backend.app.core.conversation.brain.ConversationBrain.process_message",
        return_value={"message": "ok", "language": "en"},
    ):
        from backend.app.routers.interact import chat

        payload = ChatRequest(message="hello there")
        asyncio.run(chat(mock_request, payload, db, user))
    assert calls["n"] == 1


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command")
def test_classifier_failure_fixed_response_no_side_effect(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request
):
    closed = RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.NONE,
        action=SafetyAction.FAIL_CLOSED_RESPONSE,
        domain=RiskDomain.NONE,
        rule_id="i4.rule.classifier_failed.v1",
        language="en",
    )
    with patch(
        "backend.app.services.intelligence.orchestrator.assess_safety_risk_safe",
        return_value=closed,
    ):
        from backend.app.routers.interact import chat

        payload = ChatRequest(message="hello")
        resp = asyncio.run(chat(mock_request, payload, db, user))
    assert isinstance(resp, InteractionResponse)
    assert resp.message
    mock_reminder.assert_not_called()
    mock_cmd.assert_not_called()
    mock_process.assert_not_called()


def test_public_interaction_response_shape_unchanged_emergency(db, user, mock_request):
    from backend.app.routers.interact import chat

    with patch(
        "backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder"
    ), patch(
        "backend.app.services.chat_commands.detect_and_handle_user_settings_command"
    ), patch("backend.app.core.conversation.brain.ConversationBrain.process_message"):
        payload = ChatRequest(message="I have chest pain")
        resp = asyncio.run(chat(mock_request, payload, db, user))
    fields = set(InteractionResponse.model_fields.keys())
    assert set(resp.model_dump().keys()) <= fields
    assert "risk_level" not in resp.model_dump()


# C. Orchestrator


def test_compatibility_emergency_generator_zero():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "nope", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
    result = orch.process(
        authenticated_user_id=1, message="I cannot breathe", language="en"
    )
    assert calls["n"] == 0
    assert ReasonCode.GENERATOR_SKIPPED_FOR_SAFETY.value in result.reason_codes
    assert ReasonCode.SAFETY_RISK_EMERGENCY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    assert result.detected_name is None
    assert ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED.value in result.reason_codes


def test_structured_emergency_generator_zero():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "nope", "language": "en"}

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=_stub_assembler(),
    )
    result = orch.process(
        authenticated_user_id=1,
        message="I overdosed on pills just now",
        language="en",
    )
    assert calls["n"] == 0
    assert ReasonCode.CONTEXT_ASSEMBLY_SKIPPED_SAFETY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_none_ready_generator_one():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "ready", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
    result = orch.process(
        authenticated_user_id=1, message="hello friend", language="en"
    )
    assert calls["n"] == 1
    assert ReasonCode.SAFETY_RISK_NONE.value in result.reason_codes
    assert ReasonCode.SAFETY_RESPONSE_NOT_REQUIRED.value in result.reason_codes


def test_structured_caution_generator_one_with_fixed_constraints():
    seen = {"constraints": None}

    def gen(*_a, **_k):
        seen["constraints"] = _k.get("safety_constraints")
        return {"message": "caution-ok", "language": "en"}

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=_stub_assembler(),
    )
    result = orch.process(
        authenticated_user_id=1,
        message="Should I change my dose tonight?",
        language="en",
    )
    assert result.message == "caution-ok"
    assert ReasonCode.SAFETY_RISK_CAUTION.value in result.reason_codes
    cons = seen["constraints"]
    assert cons is not None
    assert cons.policy_mode == "structured_caution"
    assert cons.disclaimer_required is True


def test_clarification_remains_generator_zero():
    calls = {"n": 0}

    def gen(*_a, **_k):
        calls["n"] += 1
        return {"message": "nope", "language": "en"}

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=_stub_assembler(),
    )
    result = orch.process(
        authenticated_user_id=1,
        message="Create a personal meal plan for me",
        language="en",
    )
    assert calls["n"] == 0
    assert ReasonCode.GENERATOR_SKIPPED_FOR_CLARIFICATION.value in result.reason_codes


def test_precomputed_assessment_avoids_second_classification():
    assess_calls = {"n": 0}

    def counting(*, message, language):
        assess_calls["n"] += 1
        return assess_safety_risk_safe(message=message, language=language)

    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
        safety_assessor=counting,
    )
    pre = assess_safety_risk_safe(message="hello", language="en")
    orch.process(
        authenticated_user_id=1,
        message="hello",
        language="en",
        precomputed_assessment=pre,
    )
    assert assess_calls["n"] == 0


def test_direct_orchestrator_classifies_exactly_once():
    assess_calls = {"n": 0}

    def counting(*, message, language):
        assess_calls["n"] += 1
        return assess_safety_risk_safe(message=message, language=language)

    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
        safety_assessor=counting,
    )
    orch.process(authenticated_user_id=1, message="hello", language="en")
    assert assess_calls["n"] == 1


def test_full_canonical_order_on_completed_responses():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(), structured_mode=False
    )
    result = orch.process(authenticated_user_id=1, message="hi", language="en")
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_strict_prefix_trace_on_real_failure():
    """Capture real emitted stages via spy — not only STAGE_ORDER[:n] theory."""
    from backend.app.services.intelligence.contracts import IntelligenceContext

    def boom_intent(*_a, **_k):
        raise RuntimeError("intent boom")

    emitted: list[tuple[str, str]] = []
    original = IntelligenceContext.append_stage

    def spy(self, stage, status, reason_code, *, duration_ms=None):
        emitted.append((stage.value, status))
        return original(self, stage, status, reason_code, duration_ms=duration_ms)

    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=True,
        context_assembler=_stub_assembler(),
        intent_resolver=boom_intent,
    )
    with patch.object(IntelligenceContext, "append_stage", spy):
        with pytest.raises(OrchestrationError) as exc:
            orch.process(authenticated_user_id=1, message="hello", language="en")
    assert exc.value.reason_code is ReasonCode.INTENT_RESOLUTION_FAILED
    expected_prefix = [
        (StageName.INITIALIZE_REQUEST.value, "ok"),
        (StageName.RESOLVE_SAFE_IDENTITY.value, "ok"),
        (StageName.RESOLVE_LOCALE_CONTEXT.value, "ok"),
        (StageName.RESOLVE_CONVERSATION_ORIGIN.value, "ok"),
        (StageName.ASSESS_SAFETY_RISK.value, "ok"),
        (StageName.ASSEMBLE_AUTHORIZED_CONTEXT.value, "ok"),
        (StageName.RESOLVE_INTENT.value, "failed"),
    ]
    assert emitted == expected_prefix
    # Must be strict prefix of canonical order.
    order = [s.value for s in STAGE_ORDER]
    assert [n for n, _ in emitted] == order[: len(emitted)]
    assert emitted[-1][1] == "failed"
    # No stages after failure.
    assert StageName.COMPLETE.value not in [n for n, _ in emitted]


def test_enum_only_privacy_safe_trace():
    secret = "PII_TOKEN_I4_SECRET"
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(), structured_mode=False
    )
    result = orch.process(
        authenticated_user_id=424242,
        message=f"I have chest pain {secret}",
        language="en",
    )
    blob = " ".join(result.reason_codes) + " ".join(result.stage_names) + result.request_id
    assert secret not in blob
    assert "424242" not in blob
    assert "chest pain" not in blob
    allowed = {c.value for c in ReasonCode}
    for code in result.reason_codes:
        assert code in allowed


def test_connected_readiness_marker_and_production_not_ready():
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=True,
        context_assembler=_stub_assembler(),
    )
    result = orch.process(authenticated_user_id=1, message="hello", language="en")
    assert ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED.value in result.reason_codes
    assert (
        ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_NOT_CONNECTED.value
        not in result.reason_codes
    )
    assert ReasonCode.STRUCTURED_MODE_NOT_PRODUCTION_READY.value in result.reason_codes


# D. Brain


def test_product_ownership_skips_legacy_gate3_pre_post():
    from backend.app.core.conversation import brain as brain_mod

    calls = {"pre": 0, "post": 0, "gpt": 0}

    def fake_pre(msg, lang):
        calls["pre"] += 1
        return "EMERGENCY_TEMPLATE"

    def fake_post(text, lang):
        calls["post"] += 1
        return "POST_REPLACED"

    class FakeCompletion:
        output_text = " generated ok "

    class FakeResponses:
        @staticmethod
        def create(**_k):
            calls["gpt"] += 1
            return FakeCompletion()

    class FakeClient:
        responses = FakeResponses()

    user = MagicMock()
    user.id = 1
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(
        brain_mod, "_gate3_check_emergency_short_circuit", fake_pre
    ), patch.object(
        brain_mod, "_gate3_validate_assistant_response", fake_post
    ), patch(
        "backend.app.core.conversation.prompts.client", FakeClient()
    ), patch(
        "backend.app.core.conversation.brain.get_stage",
        return_value=MagicMock(value="active"),
    ), patch(
        "backend.app.core.conversation.brain.transition_stage",
        side_effect=lambda s, *_a, **_k: s,
    ), patch(
        "backend.app.core.conversation.memory.ConversationMemory"
    ) as Mem, patch(
        "backend.app.core.conversation.prompts.build_system_prompt_with_context",
        return_value="sys",
    ), patch(
        "backend.app.core.conversation.persona_policy_v1.PersonaPolicyV1.resolve_language",
        return_value="en",
    ):
        Mem.return_value.get_conversation_count.return_value = 0
        Mem.return_value.get_recent_messages.return_value = []
        Mem.return_value.save_conversation.return_value = None
        b = brain_mod.ConversationBrain(db, language="en")
        out = b.process_message(1, "I cannot breathe", use_intelligence_safety=True)
    assert calls["pre"] == 0
    assert calls["post"] == 0
    assert calls["gpt"] == 1
    assert "generated ok" in out["message"]


def test_direct_brain_default_preserves_legacy_safety():
    from backend.app.core.conversation import brain as brain_mod

    calls = {"pre": 0, "gpt": 0}

    def fake_pre(msg, lang):
        calls["pre"] += 1
        return "LEGACY_EMERGENCY"

    class FakeClient:
        class responses:
            @staticmethod
            def create(**_k):
                calls["gpt"] += 1
                raise AssertionError("GPT must not run when legacy emergency fires")

    user = MagicMock()
    user.id = 1
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    with patch.object(
        brain_mod, "_gate3_check_emergency_short_circuit", fake_pre
    ), patch(
        "backend.app.core.conversation.prompts.client", FakeClient()
    ), patch(
        "backend.app.core.conversation.brain.get_stage",
        return_value=MagicMock(value="active"),
    ), patch(
        "backend.app.core.conversation.brain.transition_stage",
        side_effect=lambda s, *_a, **_k: s,
    ), patch(
        "backend.app.core.conversation.memory.ConversationMemory"
    ) as Mem, patch(
        "backend.app.core.conversation.prompts.build_system_prompt_with_context",
        return_value="sys",
    ), patch(
        "backend.app.core.conversation.persona_policy_v1.PersonaPolicyV1.resolve_language",
        return_value="en",
    ):
        Mem.return_value.get_conversation_count.return_value = 0
        Mem.return_value.get_recent_messages.return_value = []
        Mem.return_value.save_conversation.return_value = None
        b = brain_mod.ConversationBrain(db, language="en")
        out = b.process_message(1, "I cannot breathe")
    assert calls["pre"] == 1
    assert calls["gpt"] == 0
    assert out["message"] == "LEGACY_EMERGENCY"


# E. Validator / templates


def test_safe_generated_output_unchanged():
    text = "Here is gentle supportive information."
    result = validate_generated_response(text=text, language="en")
    assert result.status is PostGenerationSafetyStatus.SAFE
    assert result.message == text


def test_violation_replaced_without_regeneration():
    with patch(
        "backend.app.services.gate3.safety_validator.validate_response_text",
        return_value=(False, "unsafe_generation"),
    ):
        result = validate_generated_response(text="bad", language="en")
    assert result.status is PostGenerationSafetyStatus.REPLACED
    assert result.violation_code == "unsafe_generation"
    assert "clinician" in result.message.lower() or "emergency" in result.message.lower()


def test_validator_exception_fail_closed():
    with patch(
        "backend.app.services.gate3.safety_validator.validate_response_text",
        side_effect=RuntimeError("validator boom"),
    ):
        result = validate_generated_response(text="x", language="en")
    assert result.status is PostGenerationSafetyStatus.FAILED_CLOSED


def test_no_hardcoded_emergency_numbers_in_scoped_templates():
    texts = list(list_template_strings())
    for lang_block in gate3_templates.TEMPLATES.values():
        texts.extend(lang_block.values())
    joined = "\n".join(texts)
    assert _PROHIBITED_EMERGENCY_NUMBER_RE.search(joined) is None
    assert "۱۱۵" not in joined


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_fa_ar_en_templates_present(lang):
    for level, action, domain, rule in (
        (
            RiskLevel.EMERGENCY,
            SafetyAction.RETURN_EMERGENCY_RESPONSE,
            RiskDomain.MEDICAL_EMERGENCY,
            "i4.rule.emergency.medical.v1",
        ),
        (
            RiskLevel.EMERGENCY,
            SafetyAction.RETURN_EMERGENCY_RESPONSE,
            RiskDomain.SELF_HARM_CRISIS,
            "i4.rule.emergency.self_harm.v1",
        ),
        (
            RiskLevel.HIGH,
            SafetyAction.RETURN_HIGH_RESPONSE,
            RiskDomain.MEDICAL_EMERGENCY,
            "i4.rule.high.urgent_clinic.v1",
        ),
        (
            RiskLevel.NONE,
            SafetyAction.FAIL_CLOSED_RESPONSE,
            RiskDomain.NONE,
            "i4.rule.classifier_failed.v1",
        ),
    ):
        a = RiskAssessment(
            registry_version=REGISTRY_VERSION,
            level=level,
            action=action,
            domain=domain,
            rule_id=rule,
            language=lang,  # type: ignore[arg-type]
        )
        assert build_safety_response(a).localized_message.strip()
    with patch(
        "backend.app.services.gate3.safety_validator.validate_response_text",
        side_effect=RuntimeError("x"),
    ):
        assert validate_generated_response(
            text="x", language=lang  # type: ignore[arg-type]
        ).message.strip()


# F. Isolation


def test_i4_engine_has_no_db_session_rag_ucs_access():
    import backend.app.services.intelligence.safety_risk as mod

    src = inspect.getsource(mod)
    assert "UserContextService" not in src
    assert "rag_retrieve" not in src
    assert "sqlalchemy" not in src.lower()
    assert "print(" not in src


def test_no_global_cross_user_state():
    a1 = assess_safety_risk(message="I cannot breathe", language="en")
    a2 = assess_safety_risk(message="hello", language="en")
    assert a1.level is RiskLevel.EMERGENCY
    assert a2.level is RiskLevel.NONE


def test_notification_body_not_consumed_by_safety():
    sig = inspect.signature(assess_safety_risk)
    assert "notification" not in sig.parameters
    assert "body" not in sig.parameters


def test_injected_assessor_exception_fail_closed_via_safe_seam():
    with patch(
        "backend.app.services.intelligence.safety_risk.assess_safety_risk",
        side_effect=RuntimeError("inject"),
    ):
        a = assess_safety_risk_safe(message="anything", language="fa")
    assert a.action is SafetyAction.FAIL_CLOSED_RESPONSE
    assert requires_terminal_safety_response(a)


def test_structured_caution_constraints_fixed_no_user_values():
    c = structured_caution_constraints()
    assert isinstance(c, SafetyConstraints)
    assert c.policy_mode == "structured_caution"


# ---------------------------------------------------------------------------
# Fix1 — Mixed signals / legacy parity / caution compat / fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("What are the symptoms of a heart attack?", "en"),
        ("علائم سکته قلبی چیست؟", "fa"),
        ("ما اعراض السكتة؟", "ar"),
    ],
)
def test_fix1_informational_only_none(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("What are the symptoms of a heart attack? I cannot breathe.", "en"),
        ("علائم سکته قلبی چیست؟ نمی‌توانم نفس بکشم", "fa"),
        ("ما اعراض السكتة؟ لا استطيع التنفس", "ar"),
    ],
)
def test_fix1_informational_plus_current_emergency_terminal(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.MEDICAL_EMERGENCY
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert requires_terminal_safety_response(a)


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("I am not suicidal.", "en"),
        ("I do not want to die.", "en"),
        ("قصد خودکشی ندارم", "fa"),
        ("لا اريد الانتحار", "ar"),
    ],
)
def test_fix1_denial_only_none(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


@pytest.mark.parametrize(
    "msg,lang",
    [
        ("I am not suicidal, but now I want to die.", "en"),
        ("گفتم قصد خودکشی ندارم، اما الان می‌خواهم بمیرم", "fa"),
        ("قلت لست انتحاريا لكن الان اريد ان اموت", "ar"),
    ],
)
def test_fix1_denial_then_current_self_harm_terminal(msg, lang):
    a = assess_safety_risk(message=msg, language=lang)
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert requires_terminal_safety_response(a)


@pytest.mark.parametrize(
    "msg",
    [
        "I am suicidal",
        "hanging myself right now",
        "cut my wrist",
        "poisoning myself with pills",
        "I cannot move my legs suddenly",
        "slurred speech and weakness",
        "severe headache sudden",
        "دیگه نفس نمیکشم",
        "فلج شدم",
    ],
)
def test_fix1_legacy_material_emergency_or_high(msg):
    a = assess_safety_risk(message=msg, language="en" if msg.isascii() else "fa")
    assert a.level in (RiskLevel.EMERGENCY, RiskLevel.HIGH)
    assert requires_terminal_safety_response(a)
    assert a.rule_id.startswith("i4.rule.")
    assert msg not in a.rule_id


@pytest.mark.parametrize("msg", ["I am pregnant", "an elderly person", "my child"])
def test_fix1_demographic_alone_non_terminal(msg):
    a = assess_safety_risk(message=msg, language="en")
    assert a.action not in (
        SafetyAction.RETURN_HIGH_RESPONSE,
        SafetyAction.RETURN_EMERGENCY_RESPONSE,
    )


def test_fix1_compatibility_caution_constraint_once_and_legacy_skipped():
    seen = {"constraints": None, "n": 0}

    def gen(*_a, **_k):
        seen["n"] += 1
        seen["constraints"] = _k.get("safety_constraints")
        return {"message": "caution-ok", "language": "en"}

    orch = IntelligenceOrchestrator(legacy_generator=gen, structured_mode=False)
    result = orch.process(
        authenticated_user_id=1,
        message="Should I change my dose tonight?",
        language="en",
    )
    assert result.message == "caution-ok"
    assert seen["n"] == 1
    assert seen["constraints"] is not None
    assert seen["constraints"].policy_mode == "structured_caution"
    assert ReasonCode.SAFETY_RISK_CAUTION.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]


def test_fix1_structured_caution_constraint_exactly_once():
    seen = {"constraints": None, "n": 0}

    def gen(*_a, **_k):
        seen["n"] += 1
        seen["constraints"] = _k.get("safety_constraints")
        return {"message": "ok", "language": "en"}

    orch = IntelligenceOrchestrator(
        legacy_generator=gen,
        structured_mode=True,
        context_assembler=_stub_assembler(),
    )
    orch.process(
        authenticated_user_id=1,
        message="Should I change my dose tonight?",
        language="en",
    )
    assert seen["n"] == 1
    assert seen["constraints"].policy_mode == "structured_caution"


@patch("backend.app.core.conversation.brain.ConversationBrain.process_message")
@patch("backend.app.services.gate4.user_chat_reminder.create_user_chat_reminder")
@patch("backend.app.services.chat_commands.detect_and_handle_user_settings_command")
def test_fix1_injected_assessor_raises_at_router_fixed_response(
    mock_cmd, mock_reminder, mock_process, db, user, mock_request
):
    from backend.app.routers.interact import chat

    def boom(*, message, language):
        raise RuntimeError("ASSESSOR_SECRET_TRACE_SHOULD_NOT_LEAK")

    with patch(
        "backend.app.services.intelligence.orchestrator.assess_safety_risk_safe",
        boom,
    ):
        payload = ChatRequest(message="hello there")
        resp = asyncio.run(chat(mock_request, payload, db, user))
    assert isinstance(resp, InteractionResponse)
    assert resp.message
    assert "ASSESSOR_SECRET" not in resp.message
    mock_reminder.assert_not_called()
    mock_cmd.assert_not_called()
    mock_process.assert_not_called()


def test_fix1_injected_assessor_raises_direct_orchestrator_fixed():
    def boom(*, message, language):
        raise RuntimeError("ORCH_ASSESSOR_SECRET")

    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
        safety_assessor=boom,
    )
    result = orch.process(authenticated_user_id=1, message="hello", language="en")
    assert result.safety_action == SafetyAction.FAIL_CLOSED_RESPONSE.value
    assert ReasonCode.SAFETY_CLASSIFIER_FAILED_CLOSED.value in result.reason_codes
    assert ReasonCode.GENERATOR_SKIPPED_FOR_SAFETY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    assert "ORCH_ASSESSOR_SECRET" not in result.message
    blob = " ".join(result.reason_codes) + " ".join(result.stage_names)
    assert "ORCH_ASSESSOR_SECRET" not in blob


def test_fix1_builder_raises_distinct_reason_and_fixed_response():
    def boom_builder(_assessment):
        raise RuntimeError("BUILDER_SECRET_TEXT")

    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(),
        structured_mode=False,
        safety_response_builder=boom_builder,
    )
    result = orch.process(
        authenticated_user_id=1,
        message="I cannot breathe",
        language="en",
    )
    assert ReasonCode.SAFETY_RESPONSE_BUILD_FAILED_CLOSED.value in result.reason_codes
    assert ReasonCode.GENERATOR_SKIPPED_FOR_SAFETY.value in result.reason_codes
    assert list(result.stage_names) == [s.value for s in STAGE_ORDER]
    assert "BUILDER_SECRET" not in result.message
    assert "BUILDER_SECRET" not in " ".join(result.reason_codes)


def test_fix1_privacy_no_raw_normalized_or_exception_in_trace():
    secret = "RAW_FRAGMENT_SHOULD_NOT_APPEAR"
    orch = IntelligenceOrchestrator(
        legacy_generator=_legacy_ok(), structured_mode=False
    )
    result = orch.process(
        authenticated_user_id=90909,
        message=f"I cannot breathe {secret}",
        language="en",
    )
    blob = " ".join(result.reason_codes) + " ".join(result.stage_names) + result.request_id
    assert secret not in blob
    assert "cannot breathe" not in blob
    assert "90909" not in blob
    assert result.safety_rule_id is not None
    assert secret not in (result.safety_rule_id or "")


# ---------------------------------------------------------------------------
# Fix2 — Apostrophe fold / conceptual self-harm / Persian current intent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "I can't breathe",
        "I can’t breathe",  # U+2019
        "I can‘t breathe",  # U+2018
        "I canʼt breathe",  # U+02BC
        "I cant breathe",
    ],
)
def test_fix2_apostrophe_cant_breathe_emergency(msg):
    from backend.app.services.intelligence.safety_risk import normalize_safety_text

    norm = normalize_safety_text(msg)
    assert "cant breathe" in norm
    assert "can t breathe" not in norm
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.MEDICAL_EMERGENCY
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert requires_terminal_safety_response(a)
    assert msg not in a.rule_id
    assert "'" not in a.rule_id


@pytest.mark.parametrize(
    "msg",
    [
        "I can't move",
        "I can't move my legs",
        "I can’t move suddenly",
        "I cant move",
    ],
)
def test_fix2_apostrophe_cant_move_emergency(msg):
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.MEDICAL_EMERGENCY
    assert requires_terminal_safety_response(a)


@pytest.mark.parametrize(
    "msg",
    [
        "I don't want to die.",
        "I don’t want to die.",
        "I don‘t want to die.",  # U+2018
        "I donʼt want to die.",  # U+02BC
        "I dont want to die.",
        "don't want to die",
        "I don't want to kill myself",
        "I don't kill myself",
        "I dont kill myself",
        "do not kill myself",
    ],
)
def test_fix2_apostrophe_dont_want_to_die_none(msg):
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


def test_fix2_im_suicidal_emergency_via_fold():
    """I'm → im; bare suicidal still matches as current crisis."""
    from backend.app.services.intelligence.safety_risk import normalize_safety_text

    msg = "I'm suicidal"
    assert "im suicidal" in normalize_safety_text(msg)
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS


def test_fix2_quoted_want_to_die_does_not_glue_tokens():
    from backend.app.services.intelligence.safety_risk import normalize_safety_text

    # Quotes remain separators; words must not fuse across quote boundaries.
    norm = normalize_safety_text('He said "want to die" yesterday')
    assert norm == "he said want to die yesterday"
    a = assess_safety_risk(message='What does "want to die" mean?', language="en")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


def test_fix3_single_quoted_want_to_die_definition_none():
    from backend.app.services.intelligence.safety_risk import normalize_safety_text

    msg = "What does 'want to die' mean?"
    assert normalize_safety_text(msg) == "what does want to die mean"
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


def test_fix3_curly_im_suicidal_now_emergency():
    from backend.app.services.intelligence.safety_risk import normalize_safety_text

    msg = "I’m suicidal now"  # U+2019
    assert normalize_safety_text(msg) == "im suicidal now"
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert requires_terminal_safety_response(a)


@pytest.mark.parametrize(
    "msg",
    [
        "What does want to die mean?",
        "What does wanting to die mean?",
        "What does suicidal mean?",
        "What does suicide mean?",
        "Define want to die.",
        "Meaning of want to die.",
    ],
)
def test_fix2_conceptual_self_harm_definition_only_none(msg):
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


@pytest.mark.parametrize(
    "msg",
    [
        "What does want to die mean? Now I want to die.",
        "What does suicide mean? I am suicidal now.",
        "What does wanting to die mean? I want to die today.",
    ],
)
def test_fix2_conceptual_plus_later_current_self_harm_emergency(msg):
    a = assess_safety_risk(message=msg, language="en")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert requires_terminal_safety_response(a)


def test_fix2_repeated_want_to_die_second_occurrence_survives():
    a = assess_safety_risk(
        message="What does want to die mean? Now I want to die.",
        language="en",
    )
    assert a.rule_id == "i4.rule.emergency.self_harm.v1"
    assert a.level is RiskLevel.EMERGENCY


@pytest.mark.parametrize(
    "msg",
    [
        "می‌خواهم خودکشی کنم",
        "میخواهم خودکشی کنم",
        "میخوام خودکشی کنم",
        "خودکشی کنم",
    ],
)
def test_fix2_persian_current_self_harm_emergency(msg):
    a = assess_safety_risk(message=msg, language="fa")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert a.rule_id == "i4.rule.emergency.self_harm.v1"
    assert requires_terminal_safety_response(a)


@pytest.mark.parametrize(
    "msg",
    [
        "نمی‌خواهم خودکشی کنم",
        "نمیخواهم خودکشی کنم",
        "نمیخوام خودکشی کنم",
        "قصد خودکشی ندارم",
        "خودکشی چیست؟",
    ],
)
def test_fix2_persian_self_harm_negative_or_conceptual_none(msg):
    a = assess_safety_risk(message=msg, language="fa")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


def test_fix2_persian_conceptual_plus_current_intent_emergency():
    a = assess_safety_risk(
        message="خودکشی چیست؟ الان می‌خواهم خودکشی کنم",
        language="fa",
    )
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert a.rule_id == "i4.rule.emergency.self_harm.v1"
    assert requires_terminal_safety_response(a)


def test_fix2_result_enum_only_no_raw_or_normalized_payload():
    msg = "I can't breathe and UNIQUE_NORM_SECRET_4421"
    a = assess_safety_risk(message=msg, language="en")
    blob = " ".join(
        [
            a.rule_id,
            a.domain.value,
            a.level.value,
            a.action.value,
            a.registry_version,
        ]
    )
    assert "UNIQUE_NORM_SECRET_4421" not in blob
    assert "can't" not in blob
    assert "cant breathe" not in blob
    assert a.level is RiskLevel.EMERGENCY


# ---------------------------------------------------------------------------
# Fix3 — Persian past-denial / exact regression completion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "نمی‌خواستم خودکشی کنم",
        "نمیخواستم خودکشی کنم",
        "قصد نداشتم خودکشی کنم",
        "قصد خودکشی نداشتم",
    ],
)
def test_fix3_persian_past_denial_only_none(msg):
    a = assess_safety_risk(message=msg, language="fa")
    assert a.level is RiskLevel.NONE
    assert a.action is SafetyAction.CONTINUE


@pytest.mark.parametrize(
    "msg",
    [
        "قبلاً نمی‌خواستم خودکشی کنم، اما الان می‌خواهم خودکشی کنم",
        "قبلاً قصد خودکشی نداشتم، اما الان میخواهم خودکشی کنم",
    ],
)
def test_fix3_persian_past_denial_plus_current_intent_emergency(msg):
    a = assess_safety_risk(message=msg, language="fa")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert a.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    assert a.rule_id == "i4.rule.emergency.self_harm.v1"
    assert requires_terminal_safety_response(a)


def test_fix3_persian_current_intent_alone_emergency():
    a = assess_safety_risk(message="می‌خواهم خودکشی کنم", language="fa")
    assert a.level is RiskLevel.EMERGENCY
    assert a.domain is RiskDomain.SELF_HARM_CRISIS
    assert a.rule_id == "i4.rule.emergency.self_harm.v1"
    assert requires_terminal_safety_response(a)
