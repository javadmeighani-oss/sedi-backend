"""Section 15-I1 — versioned internal intelligence context and result contracts.

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
    COMPATIBILITY_GENERATOR_SELECTED = "COMPATIBILITY_GENERATOR_SELECTED"
    STRUCTURED_MODE_ACTIVE = "STRUCTURED_MODE_ACTIVE"
    LEGACY_GENERATION_COMPLETED = "LEGACY_GENERATION_COMPLETED"
    RESPONSE_VALIDATED = "RESPONSE_VALIDATED"
    ORCHESTRATION_COMPLETED = "ORCHESTRATION_COMPLETED"
    EMPTY_GENERATION_REJECTED = "EMPTY_GENERATION_REJECTED"
    GENERATION_FAILED = "GENERATION_FAILED"


STAGE_ORDER: tuple[StageName, ...] = (
    StageName.INITIALIZE_REQUEST,
    StageName.RESOLVE_SAFE_IDENTITY,
    StageName.RESOLVE_LOCALE_CONTEXT,
    StageName.RESOLVE_CONVERSATION_ORIGIN,
    StageName.PREPARE_COMPATIBILITY_GENERATION,
    StageName.GENERATE_WITH_LEGACY_BRAIN,
    StageName.VALIDATE_GENERATION_RESULT,
    StageName.COMPLETE,
)


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
    policy_mode: Literal["compatibility_generation"] = "compatibility_generation"
    no_diagnosis_or_dose_invention: bool = True
    no_unsupported_user_fact_invention: bool = True
    no_unsafe_logging: bool = True


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
