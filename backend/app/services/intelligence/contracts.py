"""Section 15-I1/I3 — versioned internal intelligence context and result contracts.

Internal-only. Not a public API response. No chain-of-thought. No PII in traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional, Sequence
from uuid import uuid4

CONTRACT_VERSION = "sedi.intelligence.context.v1"

LanguageCode = Literal["fa", "ar", "en"]
RolloutMode = Literal["compatibility", "structured"]
StageStatus = Literal["ok", "failed", "skipped"]
IdentitySource = Literal["jwt_server"]


class StageName(str, Enum):
    INITIALIZE_REQUEST = "initialize_request"
    RESOLVE_SAFE_IDENTITY = "resolve_safe_identity"
    RESOLVE_LOCALE_CONTEXT = "resolve_locale_context"
    RESOLVE_CONVERSATION_ORIGIN = "resolve_conversation_origin"
    ASSESS_SAFETY_RISK = "assess_safety_risk"
    ASSEMBLE_AUTHORIZED_CONTEXT = "assemble_authorized_context"
    RESOLVE_INTENT = "resolve_intent"
    EVALUATE_INFORMATION_READINESS = "evaluate_information_readiness"
    BUILD_CLARIFICATION_RESPONSE = "build_clarification_response"
    BUILD_SAFETY_RESPONSE = "build_safety_response"
    PREPARE_COMPATIBILITY_GENERATION = "prepare_compatibility_generation"
    GENERATE_WITH_LEGACY_BRAIN = "generate_with_legacy_brain"
    VALIDATE_GENERATION_RESULT = "validate_generation_result"
    COMPLETE = "complete"


class ReasonCode(str, Enum):
    CTX_INITIALIZED = "CTX_INITIALIZED"
    IDENTITY_FROM_JWT = "IDENTITY_FROM_JWT"
    LANGUAGE_NORMALIZED = "LANGUAGE_NORMALIZED"
    TIMEZONE_AVAILABLE = "TIMEZONE_AVAILABLE"
    TIMEZONE_UNAVAILABLE = "TIMEZONE_UNAVAILABLE"
    NOTIFICATION_CONTEXT_VERIFIED = "NOTIFICATION_CONTEXT_VERIFIED"
    NOTIFICATION_CONTEXT_ABSENT = "NOTIFICATION_CONTEXT_ABSENT"
    CONTEXT_ASSEMBLY_SKIPPED_COMPATIBILITY = "CONTEXT_ASSEMBLY_SKIPPED_COMPATIBILITY"
    CONTEXT_ASSEMBLED = "CONTEXT_ASSEMBLED"
    CONTEXT_SECTION_EMPTY = "CONTEXT_SECTION_EMPTY"
    CONTEXT_CONFLICT_DETECTED = "CONTEXT_CONFLICT_DETECTED"
    CONTEXT_BUDGET_TRUNCATED = "CONTEXT_BUDGET_TRUNCATED"
    CONTEXT_ASSEMBLY_FAILED = "CONTEXT_ASSEMBLY_FAILED"
    # I3 compatibility skips
    INTENT_RESOLUTION_SKIPPED_COMPATIBILITY = "INTENT_RESOLUTION_SKIPPED_COMPATIBILITY"
    READINESS_EVALUATION_SKIPPED_COMPATIBILITY = (
        "READINESS_EVALUATION_SKIPPED_COMPATIBILITY"
    )
    CLARIFICATION_SKIPPED_COMPATIBILITY = "CLARIFICATION_SKIPPED_COMPATIBILITY"
    # I3 resolve / readiness / clarification
    INTENT_RESOLVED = "INTENT_RESOLVED"
    INTENT_RESOLUTION_FAILED = "INTENT_RESOLUTION_FAILED"
    READINESS_READY = "READINESS_READY"
    READINESS_NEEDS_CLARIFICATION = "READINESS_NEEDS_CLARIFICATION"
    READINESS_NEEDS_CONFIRMATION = "READINESS_NEEDS_CONFIRMATION"
    READINESS_BLOCKED_CONFLICT = "READINESS_BLOCKED_CONFLICT"
    READINESS_BLOCKED_DENIED = "READINESS_BLOCKED_DENIED"
    READINESS_BLOCKED_STALE = "READINESS_BLOCKED_STALE"
    READINESS_UNAVAILABLE = "READINESS_UNAVAILABLE"
    READINESS_EVALUATION_FAILED = "READINESS_EVALUATION_FAILED"
    CLARIFICATION_PREPARED = "CLARIFICATION_PREPARED"
    CLARIFICATION_NOT_REQUIRED = "CLARIFICATION_NOT_REQUIRED"
    CLARIFICATION_FAILED = "CLARIFICATION_FAILED"
    GENERATOR_SKIPPED_FOR_CLARIFICATION = "GENERATOR_SKIPPED_FOR_CLARIFICATION"
    CLARIFICATION_RESPONSE_VALIDATED = "CLARIFICATION_RESPONSE_VALIDATED"
    PREPARE_GENERATION_SKIPPED_CLARIFICATION = (
        "PREPARE_GENERATION_SKIPPED_CLARIFICATION"
    )
    COMPATIBILITY_GENERATOR_SELECTED = "COMPATIBILITY_GENERATOR_SELECTED"
    STRUCTURED_MODE_ACTIVE = "STRUCTURED_MODE_ACTIVE"
    CONTEXT_ADAPTERS_CONNECTED = "CONTEXT_ADAPTERS_CONNECTED"
    GOVERNED_KB_NOT_CONNECTED = "GOVERNED_KB_NOT_CONNECTED"
    GATE3_CARE_SNIPPETS_NOT_CONNECTED = "GATE3_CARE_SNIPPETS_NOT_CONNECTED"
    # Retained for enum history / negative assertions; no longer a structured readiness claim.
    MISSING_INFORMATION_ENGINE_NOT_CONNECTED = "MISSING_INFORMATION_ENGINE_NOT_CONNECTED"
    MISSING_INFORMATION_ENGINE_CONNECTED = "MISSING_INFORMATION_ENGINE_CONNECTED"
    # Retained for enum history / negative assertions; I4 wires CONNECTED.
    ADVANCED_SAFETY_RISK_ENGINE_NOT_CONNECTED = (
        "ADVANCED_SAFETY_RISK_ENGINE_NOT_CONNECTED"
    )
    ADVANCED_SAFETY_RISK_ENGINE_CONNECTED = "ADVANCED_SAFETY_RISK_ENGINE_CONNECTED"
    CONSENT_AWARE_MEMORY_WRITES_NOT_CONNECTED = "CONSENT_AWARE_MEMORY_WRITES_NOT_CONNECTED"
    SEMANTIC_SUMMARIES_NOT_CONNECTED = "SEMANTIC_SUMMARIES_NOT_CONNECTED"
    STRUCTURED_MODE_NOT_PRODUCTION_READY = "STRUCTURED_MODE_NOT_PRODUCTION_READY"
    LEGACY_GENERATION_COMPLETED = "LEGACY_GENERATION_COMPLETED"
    RESPONSE_VALIDATED = "RESPONSE_VALIDATED"
    ORCHESTRATION_COMPLETED = "ORCHESTRATION_COMPLETED"
    EMPTY_GENERATION_REJECTED = "EMPTY_GENERATION_REJECTED"
    GENERATION_FAILED = "GENERATION_FAILED"
    # I4 safety
    SAFETY_RISK_NONE = "SAFETY_RISK_NONE"
    SAFETY_RISK_CAUTION = "SAFETY_RISK_CAUTION"
    SAFETY_RISK_HIGH = "SAFETY_RISK_HIGH"
    SAFETY_RISK_EMERGENCY = "SAFETY_RISK_EMERGENCY"
    SAFETY_CLASSIFIER_FAILED_CLOSED = "SAFETY_CLASSIFIER_FAILED_CLOSED"
    SAFETY_RESPONSE_PREPARED = "SAFETY_RESPONSE_PREPARED"
    SAFETY_RESPONSE_BUILD_FAILED_CLOSED = "SAFETY_RESPONSE_BUILD_FAILED_CLOSED"
    SAFETY_RESPONSE_NOT_REQUIRED = "SAFETY_RESPONSE_NOT_REQUIRED"
    GENERATOR_SKIPPED_FOR_SAFETY = "GENERATOR_SKIPPED_FOR_SAFETY"
    PREPARE_GENERATION_SKIPPED_SAFETY = "PREPARE_GENERATION_SKIPPED_SAFETY"
    SAFETY_POST_VALIDATION_OK = "SAFETY_POST_VALIDATION_OK"
    SAFETY_POST_VALIDATION_REPLACED = "SAFETY_POST_VALIDATION_REPLACED"
    SAFETY_POST_VALIDATION_FAILED_CLOSED = "SAFETY_POST_VALIDATION_FAILED_CLOSED"
    # Skips when safety short-circuits remaining I2/I3 stages
    CONTEXT_ASSEMBLY_SKIPPED_SAFETY = "CONTEXT_ASSEMBLY_SKIPPED_SAFETY"
    INTENT_RESOLUTION_SKIPPED_SAFETY = "INTENT_RESOLUTION_SKIPPED_SAFETY"
    READINESS_EVALUATION_SKIPPED_SAFETY = "READINESS_EVALUATION_SKIPPED_SAFETY"
    CLARIFICATION_SKIPPED_SAFETY = "CLARIFICATION_SKIPPED_SAFETY"


STRUCTURED_READINESS_REASON_CODES: tuple[ReasonCode, ...] = (
    ReasonCode.CONTEXT_ADAPTERS_CONNECTED,
    ReasonCode.GOVERNED_KB_NOT_CONNECTED,
    ReasonCode.GATE3_CARE_SNIPPETS_NOT_CONNECTED,
    ReasonCode.MISSING_INFORMATION_ENGINE_CONNECTED,
    ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED,
    ReasonCode.CONSENT_AWARE_MEMORY_WRITES_NOT_CONNECTED,
    ReasonCode.SEMANTIC_SUMMARIES_NOT_CONNECTED,
    ReasonCode.STRUCTURED_MODE_NOT_PRODUCTION_READY,
)


STAGE_ORDER: tuple[StageName, ...] = (
    # Failure-trace invariant:
    # - Successful completions record every stage in STAGE_ORDER exactly once.
    # - Fail-closed exceptions remain a strict prefix ending at the failed stage.
    # - High/emergency completed paths skip middle stages but still finish validate/complete.
    StageName.INITIALIZE_REQUEST,
    StageName.RESOLVE_SAFE_IDENTITY,
    StageName.RESOLVE_LOCALE_CONTEXT,
    StageName.RESOLVE_CONVERSATION_ORIGIN,
    StageName.ASSESS_SAFETY_RISK,
    StageName.ASSEMBLE_AUTHORIZED_CONTEXT,
    StageName.RESOLVE_INTENT,
    StageName.EVALUATE_INFORMATION_READINESS,
    StageName.BUILD_CLARIFICATION_RESPONSE,
    StageName.BUILD_SAFETY_RESPONSE,
    StageName.PREPARE_COMPATIBILITY_GENERATION,
    StageName.GENERATE_WITH_LEGACY_BRAIN,
    StageName.VALIDATE_GENERATION_RESULT,
    StageName.COMPLETE,
)


class RiskLevel(str, Enum):
    NONE = "none"
    CAUTION = "caution"
    HIGH = "high"
    EMERGENCY = "emergency"


class SafetyAction(str, Enum):
    CONTINUE = "continue"
    CONTINUE_WITH_CONSTRAINTS = "continue_with_constraints"
    RETURN_HIGH_RESPONSE = "return_high_response"
    RETURN_EMERGENCY_RESPONSE = "return_emergency_response"
    FAIL_CLOSED_RESPONSE = "fail_closed_response"


class RiskDomain(str, Enum):
    NONE = "none"
    MEDICAL_EMERGENCY = "medical_emergency"
    SELF_HARM_CRISIS = "self_harm_crisis"
    OVERDOSE_MEDICATION = "overdose_medication"
    SEVERE_ALLERGY = "severe_allergy"
    GENERAL = "general"


class PostGenerationSafetyStatus(str, Enum):
    SAFE = "safe"
    REPLACED = "replaced"
    FAILED_CLOSED = "failed_closed"


class IntentId(str, Enum):
    GENERAL = "general"
    HEALTH = "health"
    SYMPTOM = "symptom"
    MEDICATION = "medication"
    VITALS = "vitals"
    NUTRITION = "nutrition"
    SLEEP = "sleep"
    ACTIVITY = "activity"
    REMINDER = "reminder"
    NOTIFICATION_FOLLOW_UP = "notification_follow_up"


class RequestKind(str, Enum):
    INFORMATIONAL = "informational"
    PERSONALIZED_PLAN = "personalized_plan"
    ACTION = "action"
    FOLLOW_UP = "follow_up"


class IntentConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    FALLBACK = "fallback"


class FactRequirementStatus(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFLICTED = "conflicted"
    DENIED = "denied"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class ReadinessStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED_CONFLICT = "blocked_conflict"
    BLOCKED_DENIED = "blocked_denied"
    BLOCKED_STALE = "blocked_stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class IntentResult:
    """Safe intent classification metadata — never raw messages or fact values."""

    registry_version: str
    intent_id: IntentId
    request_kind: RequestKind
    confidence_band: IntentConfidenceBand
    rule_id: str


@dataclass(frozen=True)
class FactRequirementOutcome:
    """Per-requirement status using stable keys only (no values)."""

    requirement_id: str
    canonical_key: str
    status: FactRequirementStatus
    priority: int


@dataclass(frozen=True)
class ClarificationResult:
    """Localized clarifier identifiers + user-facing question (no stored values)."""

    question_id: str
    target_key: str
    template_id: str
    localized_message: str


@dataclass(frozen=True)
class ReadinessResult:
    status: ReadinessStatus
    intent_id: IntentId
    request_kind: RequestKind
    outcomes: tuple[FactRequirementOutcome, ...]
    missing_fact_keys: tuple[str, ...]
    clarification: Optional[ClarificationResult] = None


@dataclass(frozen=True)
class RiskAssessment:
    """Safe risk metadata — never raw message, fragments, or health values."""

    registry_version: str
    level: RiskLevel
    action: SafetyAction
    domain: RiskDomain
    rule_id: str
    language: LanguageCode


@dataclass(frozen=True)
class SafetyResponse:
    """Fixed localized safety wording (no fact interpolation)."""

    template_id: str
    localized_message: str


@dataclass(frozen=True)
class PostGenerationSafetyResult:
    """Internal-only post-generation safety outcome (message not for traces)."""

    status: PostGenerationSafetyStatus
    violation_code: Optional[str]
    message: str


@dataclass(frozen=True)
class StageRecord:
    stage: StageName
    status: StageStatus
    reason_code: ReasonCode
    duration_ms: Optional[float] = None


@dataclass
class AuthenticatedIdentity:
    """Server-authenticated identity. Never accept from request payload as truth."""

    user_id: int
    identity_source: IdentitySource = "jwt_server"


@dataclass
class ConversationOrigin:
    conversation_id: Optional[str] = None
    message_role: Literal["user"] = "user"
    continuity_source: Literal[
        "chat", "notification", "device", "system", "unknown"
    ] = "unknown"


@dataclass
class LocaleContext:
    language: LanguageCode
    timezone: Optional[str] = None
    timezone_fallback_reason: Optional[ReasonCode] = None


@dataclass
class NotificationOrigin:
    """Safe server-owned notification identifiers only (no body / health content)."""

    source_notification_id: int
    conversation_id: Optional[str] = None
    interaction_source: Optional[str] = None


@dataclass
class SafetyConstraints:
    policy_mode: Literal["compatibility_generation", "structured_caution"] = (
        "compatibility_generation"
    )
    no_diagnosis_or_dose_invention: bool = True
    no_unsupported_user_fact_invention: bool = True
    no_unsafe_logging: bool = True
    disclaimer_required: bool = False
    no_medication_start_stop: bool = True


@dataclass
class IntelligenceContext:
    """Request-scoped internal contract. Do not log identity or request content."""

    contract_version: str
    request_id: str
    created_at: datetime
    identity: AuthenticatedIdentity
    conversation: ConversationOrigin
    locale: LocaleContext
    notification: Optional[NotificationOrigin]
    safety: SafetyConstraints
    rollout_mode: RolloutMode
    stage_trace: list[StageRecord] = field(default_factory=list)

    def append_stage(
        self,
        stage: StageName,
        status: StageStatus,
        reason_code: ReasonCode,
        *,
        duration_ms: Optional[float] = None,
    ) -> None:
        self.stage_trace.append(
            StageRecord(
                stage=stage,
                status=status,
                reason_code=reason_code,
                duration_ms=duration_ms,
            )
        )

    def reason_codes(self) -> list[str]:
        return [record.reason_code.value for record in self.stage_trace]

    def stage_names(self) -> list[str]:
        return [record.stage.value for record in self.stage_trace]


@dataclass(frozen=True)
class OrchestrationResult:
    message: str
    language: LanguageCode
    request_id: str
    contract_version: str
    rollout_mode: RolloutMode
    reason_codes: tuple[str, ...]
    stage_names: tuple[str, ...]
    detected_name: Optional[str] = None
    error_code: Optional[str] = None
    # Internal I3 metadata (not exposed by public_brain_dict)
    intent_id: Optional[str] = None
    request_kind: Optional[str] = None
    readiness_status: Optional[str] = None
    missing_fact_keys: tuple[str, ...] = ()
    clarification_question_id: Optional[str] = None
    # Internal I4 metadata (not exposed by public_brain_dict)
    risk_level: Optional[str] = None
    safety_action: Optional[str] = None
    risk_domain: Optional[str] = None
    safety_rule_id: Optional[str] = None

    def public_brain_dict(self) -> dict[str, Any]:
        """Map to the legacy router-compatible generation dict."""
        out: dict[str, Any] = {
            "message": self.message,
            "language": self.language,
        }
        if self.detected_name is not None:
            out["detected_name"] = self.detected_name
        return out


class OrchestrationError(Exception):
    """Safe orchestrator failure with a reason code (no raw user content)."""

    def __init__(self, error_code: str, *, reason_code: Optional[ReasonCode] = None):
        self.error_code = error_code
        self.reason_code = reason_code
        super().__init__(error_code)


def new_request_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_empty_context(
    *,
    authenticated_user_id: int,
    language: LanguageCode,
    rollout_mode: RolloutMode,
) -> IntelligenceContext:
    return IntelligenceContext(
        contract_version=CONTRACT_VERSION,
        request_id=new_request_id(),
        created_at=utc_now(),
        identity=AuthenticatedIdentity(user_id=authenticated_user_id),
        conversation=ConversationOrigin(),
        locale=LocaleContext(language=language),
        notification=None,
        safety=SafetyConstraints(),
        rollout_mode=rollout_mode,
        stage_trace=[],
    )


def assert_trace_is_safe(trace: Sequence[StageRecord]) -> None:
    """Static-friendly guard used by tests: only enums, no free-form payloads."""
    for record in trace:
        if not isinstance(record.stage, StageName):
            raise AssertionError("unsafe_stage")
        if not isinstance(record.reason_code, ReasonCode):
            raise AssertionError("unsafe_reason")
