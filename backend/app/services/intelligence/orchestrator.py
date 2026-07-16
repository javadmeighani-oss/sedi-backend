"""Section 15-I1/I3/I4 — Connected Intelligence Orchestrator.

Always invoked by POST /interact/chat for the normal generation path.
Flag OFF = compatibility mode; flag ON = structured mode.
I3 intent/readiness runs only in structured mode after successful I2 assembly.
I4 safety precheck runs in both modes (never skipped for compatibility).
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping, Optional, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.app.core.conversation.brain import ConversationBrain
from backend.app.services.i18n.locale import DEFAULT_LANG, normalize_lang
from backend.app.services.intelligence.contracts import (
    CONTRACT_VERSION,
    STAGE_ORDER,
    STRUCTURED_READINESS_REASON_CODES,
    ConversationOrigin,
    IntentResult,
    LanguageCode,
    NotificationOrigin,
    OrchestrationError,
    OrchestrationResult,
    PostGenerationSafetyStatus,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RiskAssessment,
    RiskLevel,
    SafetyAction,
    SafetyConstraints,
    SafetyResponse,
    StageName,
    build_empty_context,
)
from backend.app.services.intelligence.feature_flags import (
    intelligence_orchestrator_v1_enabled,
)
from backend.app.services.intelligence.intent_registry import (
    resolve_intent_safe,
)
from backend.app.services.intelligence.missing_information import (
    MissingInformationError,
    evaluate_readiness,
)
from backend.app.services.intelligence.safety_risk import (
    assess_safety_risk_safe,
    build_fail_closed_response,
    build_safety_response_safe,
    fail_closed_assessment,
    requires_terminal_safety_response,
    structured_caution_constraints,
    validate_generated_response,
)

LegacyGenerator = Callable[..., Dict[str, Any]]
AssessFn = Callable[..., RiskAssessment]
BuildSafetyFn = Callable[..., SafetyResponse]
ValidateFn = Callable[..., Any]


class LegacyGeneratorProtocol(Protocol):
    def __call__(
        self,
        user_id: int,
        user_message: str,
        user_name: Optional[str] = None,
        *,
        notification_context: Optional[dict] = None,
        structured_context_projection: Optional[str] = None,
        structured_preferred_name: Optional[str] = None,
        use_structured_context: bool = False,
        use_intelligence_safety: bool = False,
        safety_constraints: Optional[SafetyConstraints] = None,
    ) -> Dict[str, Any]:
        ...


def _default_legacy_generator(
    db: Session,
    language: str,
) -> LegacyGenerator:
    def _generate(
        user_id: int,
        user_message: str,
        user_name: Optional[str] = None,
        *,
        notification_context: Optional[dict] = None,
        structured_context_projection: Optional[str] = None,
        structured_preferred_name: Optional[str] = None,
        use_structured_context: bool = False,
        use_intelligence_safety: bool = True,
        safety_constraints: Optional[SafetyConstraints] = None,
    ) -> Dict[str, Any]:
        brain = ConversationBrain(db, language=language)
        return brain.process_message(
            user_id,
            user_message,
            user_name,
            notification_context=notification_context,
            structured_context_projection=structured_context_projection,
            structured_preferred_name=structured_preferred_name,
            use_structured_context=use_structured_context,
            use_intelligence_safety=True,
            safety_constraints=safety_constraints,
        )

    return _generate


def _normalize_language_code(raw: Optional[str]) -> LanguageCode:
    normalized = normalize_lang(raw)
    if normalized in ("fa", "ar", "en"):
        return normalized  # type: ignore[return-value]
    return DEFAULT_LANG  # type: ignore[return-value]


def _safe_timezone(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    trimmed = str(raw).strip()
    if not trimmed:
        return None
    try:
        ZoneInfo(trimmed)
    except ZoneInfoNotFoundError:
        return None
    except Exception:
        return None
    return trimmed


def _lookup_user_timezone(db: Optional[Session], user_id: int) -> Optional[str]:
    if db is None:
        return None
    try:
        from backend.app.models import UserProfileCore

        profile = (
            db.query(UserProfileCore)
            .filter(UserProfileCore.user_id == user_id)
            .first()
        )
        if profile is None:
            return None
        return _safe_timezone(getattr(profile, "timezone", None))
    except Exception:
        return None


def _continuity_source(
    interaction_source: Optional[str],
) -> str:
    if interaction_source in ("chat", "notification", "device", "system"):
        return interaction_source
    return "unknown"


_READINESS_REASON = {
    ReadinessStatus.READY: ReasonCode.READINESS_READY,
    ReadinessStatus.NEEDS_CLARIFICATION: ReasonCode.READINESS_NEEDS_CLARIFICATION,
    ReadinessStatus.NEEDS_CONFIRMATION: ReasonCode.READINESS_NEEDS_CONFIRMATION,
    ReadinessStatus.BLOCKED_CONFLICT: ReasonCode.READINESS_BLOCKED_CONFLICT,
    ReadinessStatus.BLOCKED_DENIED: ReasonCode.READINESS_BLOCKED_DENIED,
    ReadinessStatus.BLOCKED_STALE: ReasonCode.READINESS_BLOCKED_STALE,
    ReadinessStatus.UNAVAILABLE: ReasonCode.READINESS_UNAVAILABLE,
}


_BANNED_NOTIF_KEYS = frozenset(
    {"body", "raw_body", "context_json", "health", "dose", "dosage", "notification_body"}
)

_ASSESS_REASON = {
    RiskLevel.NONE: ReasonCode.SAFETY_RISK_NONE,
    RiskLevel.CAUTION: ReasonCode.SAFETY_RISK_CAUTION,
    RiskLevel.HIGH: ReasonCode.SAFETY_RISK_HIGH,
    RiskLevel.EMERGENCY: ReasonCode.SAFETY_RISK_EMERGENCY,
}


def _assessment_reason(assessment: RiskAssessment) -> ReasonCode:
    if assessment.action is SafetyAction.FAIL_CLOSED_RESPONSE:
        return ReasonCode.SAFETY_CLASSIFIER_FAILED_CLOSED
    return _ASSESS_REASON.get(assessment.level, ReasonCode.SAFETY_RISK_NONE)


def _post_validation_reason(status: PostGenerationSafetyStatus) -> ReasonCode:
    if status is PostGenerationSafetyStatus.SAFE:
        return ReasonCode.SAFETY_POST_VALIDATION_OK
    if status is PostGenerationSafetyStatus.REPLACED:
        return ReasonCode.SAFETY_POST_VALIDATION_REPLACED
    return ReasonCode.SAFETY_POST_VALIDATION_FAILED_CLOSED


class IntelligenceOrchestrator:
    """Stateless gateway: each process() builds a fresh request-scoped context."""

    def __init__(
        self,
        *,
        db: Optional[Session] = None,
        legacy_generator: Optional[LegacyGenerator] = None,
        structured_mode: Optional[bool] = None,
        context_assembler: Optional[Any] = None,
        intent_resolver: Optional[Callable[..., IntentResult]] = None,
        missing_information_engine: Optional[Callable[..., ReadinessResult]] = None,
        safety_assessor: Optional[AssessFn] = None,
        safety_response_builder: Optional[BuildSafetyFn] = None,
        safety_validator: Optional[ValidateFn] = None,
    ) -> None:
        self._db = db
        self._legacy_generator = legacy_generator
        self._structured_mode_override = structured_mode
        self._context_assembler = context_assembler
        self._intent_resolver = intent_resolver or resolve_intent_safe
        self._missing_information_engine = (
            missing_information_engine or evaluate_readiness
        )
        self._safety_assessor = safety_assessor or assess_safety_risk_safe
        self._safety_response_builder = (
            safety_response_builder or build_safety_response_safe
        )
        self._safety_validator = safety_validator or validate_generated_response

    def _rollout_mode(self):
        if self._structured_mode_override is not None:
            return "structured" if self._structured_mode_override else "compatibility"
        return (
            "structured"
            if intelligence_orchestrator_v1_enabled()
            else "compatibility"
        )

    def precheck_safety_risk(
        self,
        *,
        message: str,
        language: str,
    ) -> RiskAssessment:
        """Pure I4 precheck for router bypass closure (no stage trace).

        Any injected assessor Exception becomes FAIL_CLOSED — never raises.
        """
        lang = _normalize_language_code(language)
        try:
            return self._safety_assessor(message=message, language=lang)
        except Exception:
            return fail_closed_assessment(language=lang)

    def process(
        self,
        *,
        authenticated_user_id: int,
        message: str,
        language: str,
        conversation_id: Optional[str] = None,
        interaction_source: Optional[str] = None,
        source_notification_id: Optional[int] = None,
        notification_context: Optional[Mapping[str, Any]] = None,
        timezone: Optional[str] = None,
        precomputed_assessment: Optional[RiskAssessment] = None,
    ) -> OrchestrationResult:
        """
        Run deterministic I1/I3/I4 stages then legacy generation at most once.

        ``message`` and ``notification_context`` are generation-only inputs and
        never enter stage traces. Authenticated identity must come from the
        JWT/server caller — never from a caller-controlled user_id field.

        Failure-trace invariant: completed responses traverse all of
        ``STAGE_ORDER``; fail-closed paths stop at the failed stage and record
        only a strict prefix of ``STAGE_ORDER`` (no post-failure stages).
        High/emergency completed paths skip middle stages but still finish
        validate/complete.
        """
        if not isinstance(authenticated_user_id, int) or authenticated_user_id <= 0:
            raise OrchestrationError("invalid_authenticated_identity")

        rollout_mode = self._rollout_mode()
        lang = _normalize_language_code(language)
        ctx = build_empty_context(
            authenticated_user_id=authenticated_user_id,
            language=lang,
            rollout_mode=rollout_mode,
        )
        extra_reason_codes: list[str] = []

        # 1) initialize_request
        t0 = time.perf_counter()
        ctx.append_stage(
            StageName.INITIALIZE_REQUEST,
            "ok",
            ReasonCode.CTX_INITIALIZED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        # 2) resolve_safe_identity
        t0 = time.perf_counter()
        ctx.append_stage(
            StageName.RESOLVE_SAFE_IDENTITY,
            "ok",
            ReasonCode.IDENTITY_FROM_JWT,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        # 3) resolve_locale_context
        t0 = time.perf_counter()
        tz = _safe_timezone(timezone)
        if tz is None:
            tz = _lookup_user_timezone(self._db, authenticated_user_id)
        if tz is not None:
            ctx.locale.timezone = tz
            ctx.locale.timezone_fallback_reason = None
            extra_reason_codes.append(ReasonCode.TIMEZONE_AVAILABLE.value)
        else:
            ctx.locale.timezone = None
            ctx.locale.timezone_fallback_reason = ReasonCode.TIMEZONE_UNAVAILABLE
            extra_reason_codes.append(ReasonCode.TIMEZONE_UNAVAILABLE.value)
        ctx.locale.language = lang
        ctx.append_stage(
            StageName.RESOLVE_LOCALE_CONTEXT,
            "ok",
            ReasonCode.LANGUAGE_NORMALIZED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        # 4) resolve_conversation_origin
        t0 = time.perf_counter()
        ctx.conversation = ConversationOrigin(
            conversation_id=conversation_id,
            message_role="user",
            continuity_source=_continuity_source(interaction_source),  # type: ignore[arg-type]
        )
        if source_notification_id is not None:
            ctx.notification = NotificationOrigin(
                source_notification_id=source_notification_id,
                conversation_id=conversation_id,
                interaction_source=interaction_source,
            )
            notif_reason = ReasonCode.NOTIFICATION_CONTEXT_VERIFIED
        else:
            ctx.notification = None
            notif_reason = ReasonCode.NOTIFICATION_CONTEXT_ABSENT

        generation_notification_context: Optional[dict] = None
        if notification_context:
            generation_notification_context = {
                k: v
                for k, v in dict(notification_context).items()
                if k not in _BANNED_NOTIF_KEYS
            }

        ctx.append_stage(
            StageName.RESOLVE_CONVERSATION_ORIGIN,
            "ok",
            notif_reason,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        # 5) assess_safety_risk (both modes; reuse precomputed when provided)
        t0 = time.perf_counter()
        try:
            if precomputed_assessment is not None:
                assessment = precomputed_assessment
            else:
                assessment = self._safety_assessor(message=message, language=lang)
        except Exception:
            assessment = fail_closed_assessment(language=lang)
        assess_reason = _assessment_reason(assessment)
        ctx.append_stage(
            StageName.ASSESS_SAFETY_RISK,
            "ok",
            assess_reason,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
        terminal_safety = requires_terminal_safety_response(assessment)
        skip_generator = False
        safety_message: Optional[str] = None
        clarification_message: Optional[str] = None
        intent_meta: Optional[IntentResult] = None
        readiness_meta: Optional[ReadinessResult] = None
        structured_projection: Optional[str] = None
        structured_preferred_name: Optional[str] = None
        use_structured_context = False
        snapshot = None
        caution_constraints: Optional[SafetyConstraints] = None

        # Fix1 A04: CAUTION constraints in both structured and compatibility.
        if assessment.action is SafetyAction.CONTINUE_WITH_CONSTRAINTS:
            caution_constraints = structured_caution_constraints()
            ctx.safety = caution_constraints

        if terminal_safety:
            # CONNECTED marker even when assembly is skipped for safety.
            if (
                ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED.value
                not in extra_reason_codes
            ):
                extra_reason_codes.append(
                    ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED.value
                )
            # Skip assemble / I3 / clarification
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.ASSEMBLE_AUTHORIZED_CONTEXT,
                "skipped",
                ReasonCode.CONTEXT_ASSEMBLY_SKIPPED_SAFETY,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.RESOLVE_INTENT,
                "skipped",
                ReasonCode.INTENT_RESOLUTION_SKIPPED_SAFETY,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.EVALUATE_INFORMATION_READINESS,
                "skipped",
                ReasonCode.READINESS_EVALUATION_SKIPPED_SAFETY,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.BUILD_CLARIFICATION_RESPONSE,
                "skipped",
                ReasonCode.CLARIFICATION_SKIPPED_SAFETY,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

            # build_safety_response — builder Exception → trusted fixed fallback (no gen)
            t0 = time.perf_counter()
            builder_failed = False
            try:
                safety_resp = self._safety_response_builder(assessment)
                safety_message = safety_resp.localized_message
                if not isinstance(safety_message, str) or not safety_message.strip():
                    raise ValueError("empty_safety_response")
            except Exception:
                safety_resp = build_fail_closed_response(language=lang)
                safety_message = safety_resp.localized_message
                builder_failed = True
            skip_generator = True
            ctx.append_stage(
                StageName.BUILD_SAFETY_RESPONSE,
                "ok",
                (
                    ReasonCode.SAFETY_RESPONSE_BUILD_FAILED_CLOSED
                    if builder_failed
                    else ReasonCode.SAFETY_RESPONSE_PREPARED
                ),
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        else:
            # 6) assemble_authorized_context
            t0 = time.perf_counter()
            if rollout_mode == "structured":
                if self._db is None and self._context_assembler is None:
                    ctx.append_stage(
                        StageName.ASSEMBLE_AUTHORIZED_CONTEXT,
                        "failed",
                        ReasonCode.CONTEXT_ASSEMBLY_FAILED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                    raise OrchestrationError(
                        "context_assembly_failed",
                        reason_code=ReasonCode.CONTEXT_ASSEMBLY_FAILED,
                    )
                try:
                    from backend.app.services.intelligence.assembler import (
                        AuthorizedContextAssembler,
                    )

                    assembler = self._context_assembler or AuthorizedContextAssembler()
                    snapshot = assembler.assemble(
                        self._db,
                        authenticated_user_id=authenticated_user_id,
                        request_id=ctx.request_id,
                        notification_context=generation_notification_context,
                        source_notification_id=source_notification_id,
                    )
                    projection = assembler.build_compatibility_projection(snapshot)
                    structured_projection = projection.text
                    structured_preferred_name = projection.preferred_name
                    use_structured_context = True
                    for code in snapshot.reason_codes:
                        if code not in extra_reason_codes:
                            extra_reason_codes.append(code)
                    if (
                        projection.truncated
                        and ReasonCode.CONTEXT_BUDGET_TRUNCATED.value
                        not in extra_reason_codes
                    ):
                        extra_reason_codes.append(
                            ReasonCode.CONTEXT_BUDGET_TRUNCATED.value
                        )
                    for readiness in STRUCTURED_READINESS_REASON_CODES:
                        if readiness.value not in extra_reason_codes:
                            extra_reason_codes.append(readiness.value)
                    ctx.append_stage(
                        StageName.ASSEMBLE_AUTHORIZED_CONTEXT,
                        "ok",
                        ReasonCode.CONTEXT_ASSEMBLED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                except OrchestrationError:
                    raise
                except Exception:
                    ctx.append_stage(
                        StageName.ASSEMBLE_AUTHORIZED_CONTEXT,
                        "failed",
                        ReasonCode.CONTEXT_ASSEMBLY_FAILED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                    raise OrchestrationError(
                        "context_assembly_failed",
                        reason_code=ReasonCode.CONTEXT_ASSEMBLY_FAILED,
                    )
            else:
                ctx.append_stage(
                    StageName.ASSEMBLE_AUTHORIZED_CONTEXT,
                    "skipped",
                    ReasonCode.CONTEXT_ASSEMBLY_SKIPPED_COMPATIBILITY,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )

            # 7–9) I3 stages
            if rollout_mode != "structured":
                t0 = time.perf_counter()
                ctx.append_stage(
                    StageName.RESOLVE_INTENT,
                    "skipped",
                    ReasonCode.INTENT_RESOLUTION_SKIPPED_COMPATIBILITY,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                t0 = time.perf_counter()
                ctx.append_stage(
                    StageName.EVALUATE_INFORMATION_READINESS,
                    "skipped",
                    ReasonCode.READINESS_EVALUATION_SKIPPED_COMPATIBILITY,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                t0 = time.perf_counter()
                ctx.append_stage(
                    StageName.BUILD_CLARIFICATION_RESPONSE,
                    "skipped",
                    ReasonCode.CLARIFICATION_SKIPPED_COMPATIBILITY,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
            else:
                t0 = time.perf_counter()
                try:
                    intent_meta = self._intent_resolver(
                        message=message,
                        language=lang,
                        has_verified_notification_origin=ctx.notification is not None,
                    )
                    ctx.append_stage(
                        StageName.RESOLVE_INTENT,
                        "ok",
                        ReasonCode.INTENT_RESOLVED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                except Exception:
                    ctx.append_stage(
                        StageName.RESOLVE_INTENT,
                        "failed",
                        ReasonCode.INTENT_RESOLUTION_FAILED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                    raise OrchestrationError(
                        "intent_resolution_failed",
                        reason_code=ReasonCode.INTENT_RESOLUTION_FAILED,
                    )

                t0 = time.perf_counter()
                try:
                    if snapshot is None:
                        raise MissingInformationError("missing_snapshot")
                    readiness_meta = self._missing_information_engine(
                        snapshot=snapshot,
                        intent=intent_meta,
                        authenticated_user_id=authenticated_user_id,
                        language=lang,
                    )
                    ctx.append_stage(
                        StageName.EVALUATE_INFORMATION_READINESS,
                        "ok",
                        _READINESS_REASON[readiness_meta.status],
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                except OrchestrationError:
                    raise
                except Exception:
                    ctx.append_stage(
                        StageName.EVALUATE_INFORMATION_READINESS,
                        "failed",
                        ReasonCode.READINESS_EVALUATION_FAILED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                    raise OrchestrationError(
                        "readiness_evaluation_failed",
                        reason_code=ReasonCode.READINESS_EVALUATION_FAILED,
                    )

                t0 = time.perf_counter()
                if readiness_meta.status is ReadinessStatus.READY:
                    ctx.append_stage(
                        StageName.BUILD_CLARIFICATION_RESPONSE,
                        "skipped",
                        ReasonCode.CLARIFICATION_NOT_REQUIRED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                else:
                    try:
                        if readiness_meta.clarification is None:
                            raise MissingInformationError("missing_clarification")
                        clarification_message = (
                            readiness_meta.clarification.localized_message
                        )
                        if (
                            not isinstance(clarification_message, str)
                            or not clarification_message.strip()
                        ):
                            raise MissingInformationError("empty_clarification")
                        skip_generator = True
                        ctx.append_stage(
                            StageName.BUILD_CLARIFICATION_RESPONSE,
                            "ok",
                            ReasonCode.CLARIFICATION_PREPARED,
                            duration_ms=(time.perf_counter() - t0) * 1000.0,
                        )
                    except Exception:
                        ctx.append_stage(
                            StageName.BUILD_CLARIFICATION_RESPONSE,
                            "failed",
                            ReasonCode.CLARIFICATION_FAILED,
                            duration_ms=(time.perf_counter() - t0) * 1000.0,
                        )
                        raise OrchestrationError(
                            "clarification_failed",
                            reason_code=ReasonCode.CLARIFICATION_FAILED,
                        )

            # build_safety_response not required on non-terminal path
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.BUILD_SAFETY_RESPONSE,
                "skipped",
                ReasonCode.SAFETY_RESPONSE_NOT_REQUIRED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Compatibility path still asserts CONNECTED via assess; structured via readiness tuple.
        if rollout_mode == "compatibility":
            if (
                ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED.value
                not in extra_reason_codes
            ):
                extra_reason_codes.append(
                    ReasonCode.ADVANCED_SAFETY_RISK_ENGINE_CONNECTED.value
                )

        # prepare
        t0 = time.perf_counter()
        if skip_generator and terminal_safety:
            ctx.append_stage(
                StageName.PREPARE_COMPATIBILITY_GENERATION,
                "skipped",
                ReasonCode.PREPARE_GENERATION_SKIPPED_SAFETY,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        elif skip_generator:
            ctx.append_stage(
                StageName.PREPARE_COMPATIBILITY_GENERATION,
                "skipped",
                ReasonCode.PREPARE_GENERATION_SKIPPED_CLARIFICATION,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        else:
            if rollout_mode == "structured":
                extra_reason_codes.append(ReasonCode.STRUCTURED_MODE_ACTIVE.value)
            ctx.append_stage(
                StageName.PREPARE_COMPATIBILITY_GENERATION,
                "ok",
                ReasonCode.COMPATIBILITY_GENERATOR_SELECTED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        out_message: str
        detected_name: Optional[str] = None
        out_language = ctx.locale.language
        post_val_status: Optional[PostGenerationSafetyStatus] = None

        if skip_generator and terminal_safety:
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.GENERATE_WITH_LEGACY_BRAIN,
                "skipped",
                ReasonCode.GENERATOR_SKIPPED_FOR_SAFETY,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            out_message = safety_message or ""
            detected_name = None
            t0 = time.perf_counter()
            if not out_message.strip():
                ctx.append_stage(
                    StageName.VALIDATE_GENERATION_RESULT,
                    "failed",
                    ReasonCode.EMPTY_GENERATION_REJECTED,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                raise OrchestrationError(
                    "empty_generation",
                    reason_code=ReasonCode.EMPTY_GENERATION_REJECTED,
                )
            validated = self._safety_validator(text=out_message, language=lang)
            out_message = validated.message
            post_val_status = validated.status
            ctx.append_stage(
                StageName.VALIDATE_GENERATION_RESULT,
                "ok",
                ReasonCode.RESPONSE_VALIDATED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            extra_reason_codes.append(_post_validation_reason(post_val_status).value)
        elif skip_generator:
            t0 = time.perf_counter()
            ctx.append_stage(
                StageName.GENERATE_WITH_LEGACY_BRAIN,
                "skipped",
                ReasonCode.GENERATOR_SKIPPED_FOR_CLARIFICATION,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            out_message = clarification_message or ""
            t0 = time.perf_counter()
            if not out_message.strip():
                ctx.append_stage(
                    StageName.VALIDATE_GENERATION_RESULT,
                    "failed",
                    ReasonCode.EMPTY_GENERATION_REJECTED,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                raise OrchestrationError(
                    "empty_generation",
                    reason_code=ReasonCode.EMPTY_GENERATION_REJECTED,
                )
            ctx.append_stage(
                StageName.VALIDATE_GENERATION_RESULT,
                "ok",
                ReasonCode.CLARIFICATION_RESPONSE_VALIDATED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        else:
            generator = self._legacy_generator
            if generator is None:
                if self._db is None:
                    raise OrchestrationError("missing_db_for_legacy_generator")
                generator = _default_legacy_generator(self._db, lang)

            t0 = time.perf_counter()
            try:
                raw = generator(
                    authenticated_user_id,
                    message,
                    None,
                    notification_context=(
                        None
                        if use_structured_context
                        else generation_notification_context
                    ),
                    structured_context_projection=structured_projection,
                    structured_preferred_name=structured_preferred_name,
                    use_structured_context=use_structured_context,
                    use_intelligence_safety=True,
                    safety_constraints=caution_constraints,
                )
            except Exception:
                ctx.append_stage(
                    StageName.GENERATE_WITH_LEGACY_BRAIN,
                    "failed",
                    ReasonCode.GENERATION_FAILED,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                raise

            ctx.append_stage(
                StageName.GENERATE_WITH_LEGACY_BRAIN,
                "ok",
                ReasonCode.LEGACY_GENERATION_COMPLETED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

            t0 = time.perf_counter()
            if not isinstance(raw, dict):
                ctx.append_stage(
                    StageName.VALIDATE_GENERATION_RESULT,
                    "failed",
                    ReasonCode.EMPTY_GENERATION_REJECTED,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                raise OrchestrationError(
                    "empty_generation",
                    reason_code=ReasonCode.EMPTY_GENERATION_REJECTED,
                )
            gen_message = raw.get("message")
            if not isinstance(gen_message, str) or not gen_message.strip():
                ctx.append_stage(
                    StageName.VALIDATE_GENERATION_RESULT,
                    "failed",
                    ReasonCode.EMPTY_GENERATION_REJECTED,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
                raise OrchestrationError(
                    "empty_generation",
                    reason_code=ReasonCode.EMPTY_GENERATION_REJECTED,
                )
            validated = self._safety_validator(text=gen_message, language=lang)
            out_message = validated.message
            post_val_status = validated.status
            detected_name = raw.get("detected_name")
            if detected_name is not None and not isinstance(detected_name, str):
                detected_name = None
            ctx.append_stage(
                StageName.VALIDATE_GENERATION_RESULT,
                "ok",
                ReasonCode.RESPONSE_VALIDATED,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
            extra_reason_codes.append(_post_validation_reason(post_val_status).value)

        # complete
        t0 = time.perf_counter()
        ctx.append_stage(
            StageName.COMPLETE,
            "ok",
            ReasonCode.ORCHESTRATION_COMPLETED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        stage_reasons = ctx.reason_codes()
        reason_codes: list[str] = []
        extras_to_place = list(extra_reason_codes)
        for code in stage_reasons:
            reason_codes.append(code)
            if code == ReasonCode.LANGUAGE_NORMALIZED.value and extras_to_place:
                tz_extras = [
                    c
                    for c in extras_to_place
                    if c
                    in (
                        ReasonCode.TIMEZONE_AVAILABLE.value,
                        ReasonCode.TIMEZONE_UNAVAILABLE.value,
                    )
                ]
                other_extras = [c for c in extras_to_place if c not in tz_extras]
                reason_codes.extend(tz_extras)
                extras_to_place = other_extras
        reason_codes.extend(extras_to_place)

        names = ctx.stage_names()
        expected = [s.value for s in STAGE_ORDER]
        if names != expected:
            raise OrchestrationError("invalid_stage_order")

        return OrchestrationResult(
            message=out_message.strip(),
            language=out_language,
            request_id=ctx.request_id,
            contract_version=CONTRACT_VERSION,
            rollout_mode=rollout_mode,
            reason_codes=tuple(reason_codes),
            stage_names=tuple(names),
            detected_name=detected_name,
            intent_id=intent_meta.intent_id.value if intent_meta else None,
            request_kind=intent_meta.request_kind.value if intent_meta else None,
            readiness_status=readiness_meta.status.value if readiness_meta else None,
            missing_fact_keys=(
                readiness_meta.missing_fact_keys if readiness_meta else ()
            ),
            clarification_question_id=(
                readiness_meta.clarification.question_id
                if readiness_meta and readiness_meta.clarification
                else None
            ),
            risk_level=assessment.level.value,
            safety_action=assessment.action.value,
            risk_domain=assessment.domain.value,
            safety_rule_id=assessment.rule_id,
        )
