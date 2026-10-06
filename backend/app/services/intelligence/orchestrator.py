"""Section 15-I1/I3/I4 — Connected Intelligence Orchestrator.

Always invoked by POST /interact/chat for the normal generation path.
Flag OFF = compatibility mode; flag ON = structured mode.
I3 intent/readiness runs only in structured mode after successful I2 assembly.
I4 safety precheck runs in both modes (never skipped for compatibility).
"""

from __future__ import annotations

import inspect
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
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    LanguageCode,
    NotificationOrigin,
    OrchestrationError,
    OrchestrationResult,
    PostGenerationSafetyStatus,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RequestKind,
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

# Intent IDs that already encode health/lifestyle knowledge demand (I3).
_GOVERNED_KNOWLEDGE_INTENT_IDS = frozenset(
    {
        IntentId.HEALTH,
        IntentId.SYMPTOM,
        IntentId.MEDICATION,
        IntentId.VITALS,
        IntentId.NUTRITION,
        IntentId.SLEEP,
        IntentId.ACTIVITY,
    }
)


def allow_governed_knowledge_decision(
    *,
    terminal_safety: bool,
    message: str,
    language: str,
    intent: Optional[IntentResult],
    interaction_need: Optional[Any],
) -> bool:
    """I1 decision using existing I3/I4/Gate3 signals only — no new taxonomy.

    Brain must not re-decide; this boolean is authoritative for structured I5.
    """
    if terminal_safety:
        return False

    from backend.app.services.gate3.medical_intent import (
        is_medical_care_intent,
        is_mental_wellbeing_intent,
    )
    from backend.app.services.intelligence.psychological_interaction import (
        InteractionNeed,
    )

    intent_id = intent.intent_id if intent is not None else None
    request_kind = intent.request_kind if intent is not None else None
    if intent_id in (IntentId.REMINDER, IntentId.NOTIFICATION_FOLLOW_UP):
        return False

    factual_intent = intent_id in _GOVERNED_KNOWLEDGE_INTENT_IDS
    medical = is_medical_care_intent(message or "", language or "en")
    wellbeing = is_mental_wellbeing_intent(message or "", language or "en")
    informational = request_kind is RequestKind.INFORMATIONAL

    need = interaction_need
    if need is InteractionNeed.BE_HEARD:
        # Pure emotional listen: suppress. Explicit factual/evidence via I3 intent: allow.
        return bool(factual_intent and informational)

    # Non-BE_HEARD: existing medical/wellbeing classifiers or knowledge intents.
    if factual_intent or medical or wellbeing:
        return True
    return False


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
        relationship_guidance: Optional[str] = None,
        skip_generic_kc_extraction: bool = False,
        allow_governed_knowledge: bool = False,
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
        relationship_guidance: Optional[str] = None,
        skip_generic_kc_extraction: bool = False,
        allow_governed_knowledge: bool = False,
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
            relationship_guidance=relationship_guidance,
            skip_generic_kc_extraction=skip_generic_kc_extraction,
            allow_governed_knowledge=allow_governed_knowledge,
        )

    return _generate


def _generator_accepts_kwarg(generator: Callable[..., Any], name: str) -> bool:
    """Inspect callable once; never retry after an execution-time TypeError."""
    try:
        sig = inspect.signature(generator)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if name in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def _generator_accepts_relationship_guidance(generator: Callable[..., Any]) -> bool:
    return _generator_accepts_kwarg(generator, "relationship_guidance")


def _apply_discovery_fatigue_response(
    db: Optional[Session],
    *,
    user_id: int,
    message: str,
    language: LanguageCode,
    allow_binding: bool,
    classification: Optional[Any] = None,
) -> Any:
    """CR-03.2: one-shot relationship discovery binding + fatigue consume.

    When allow_binding is False (compat/terminal/caution), marker is still consumed with
    no fact write and no skip/reject streak update.
    Returns DiscoveryClassification when available.
    """
    if db is None:
        return None
    try:
        from backend.app.services.i6.relationship_discovery import (
            process_relationship_discovery_answer,
        )

        return process_relationship_discovery_answer(
            db,
            user_id=user_id,
            message=message,
            language=language,
            allow_binding=allow_binding,
            classification=classification,
        )
    except Exception:
        # Discovery binding is best-effort; never fail the chat path.
        return None


def _fatigue_permits_discovery(
    db: Optional[Session], user_id: int, *, invited: bool = False
) -> bool:
    """Q4 — RD-scoped fatigue (not generic KC check_can_ask)."""
    if db is None:
        return False
    try:
        from datetime import datetime, timezone

        from backend.app.services.knowledge.kc_fatigue_policy import (
            check_can_ask_relationship_discovery,
        )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed, _reason, _next, _snap = check_can_ask_relationship_discovery(
            db, user_id, now, invited=invited
        )
        return bool(allowed)
    except Exception:
        return False


def _mark_relationship_discovery_asked(
    db: Optional[Session],
    *,
    user_id: int,
    target_key: str,
    invited: bool = False,
    companion_key: Optional[str] = None,
) -> None:
    if db is None or not target_key:
        return
    try:
        from datetime import datetime, timezone

        from backend.app.services.i6.relationship_discovery import (
            format_relationship_discovery_marker,
        )
        from backend.app.services.knowledge.kc_fatigue_policy import mark_asked

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        mark_asked(
            db,
            user_id,
            now,
            format_relationship_discovery_marker(
                target_key, invited=invited, companion_key=companion_key
            ),
        )
    except Exception:
        return


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
        discovery_classification = None

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

            # CR-03.3: classify pending discovery reply BEFORE I3 resolve/readiness.
            # Request-local only; I3 applies contextual policy via disposition hint.
            try:
                from backend.app.services.i6.relationship_discovery import (
                    DiscoveryDisposition,
                    classify_discovery_reply,
                    peek_relationship_discovery_marker,
                    peek_relationship_discovery_targets,
                )

                pending_targets, _pending_invited = peek_relationship_discovery_targets(
                    self._db, authenticated_user_id
                )
                # Legacy single-marker compat when multi-target peek is empty.
                if not pending_targets:
                    legacy_target = peek_relationship_discovery_marker(
                        self._db, authenticated_user_id
                    )
                    if legacy_target:
                        pending_targets = (legacy_target,)
                if pending_targets:
                    # Request-local aggregate for I3 hint (pair-safe).
                    clfs = [
                        classify_discovery_reply(t, message, lang)
                        for t in pending_targets
                    ]
                    if any(c.disposition is DiscoveryDisposition.SKIP for c in clfs):
                        discovery_classification = next(
                            c
                            for c in clfs
                            if c.disposition is DiscoveryDisposition.SKIP
                        )
                    elif any(
                        c.disposition is DiscoveryDisposition.UNRELATED for c in clfs
                    ):
                        discovery_classification = next(
                            c
                            for c in clfs
                            if c.disposition is DiscoveryDisposition.UNRELATED
                        )
                    elif any(
                        c.disposition is DiscoveryDisposition.ANSWER for c in clfs
                    ):
                        discovery_classification = next(
                            c
                            for c in clfs
                            if c.disposition is DiscoveryDisposition.ANSWER
                        )
                    else:
                        discovery_classification = clfs[0]
            except Exception:
                discovery_classification = None

            discovery_disposition_hint = (
                discovery_classification.disposition.value
                if discovery_classification is not None
                else None
            )

            # 7–9) I3 stages
            if rollout_mode != "structured":
                # Compatibility: full I3 skipped EXCEPT REMINDER/event request-local seam.
                # Probe intent without exposing non-REMINDER I3 identity in compatibility.
                t0 = time.perf_counter()
                try:
                    _compat_intent = self._intent_resolver(
                        message=message,
                        language=lang,
                        has_verified_notification_origin=ctx.notification is not None,
                        relationship_discovery_disposition=discovery_disposition_hint,
                    )
                except TypeError:
                    # Backward-compatible stub resolvers without the disposition kwarg.
                    try:
                        _compat_intent = self._intent_resolver(
                            message=message,
                            language=lang,
                            has_verified_notification_origin=ctx.notification is not None,
                        )
                    except Exception:
                        _compat_intent = None
                except Exception:
                    _compat_intent = None

                if (
                    _compat_intent is not None
                    and _compat_intent.intent_id is IntentId.REMINDER
                ):
                    intent_meta = _compat_intent
                    ctx.append_stage(
                        StageName.RESOLVE_INTENT,
                        "ok",
                        ReasonCode.INTENT_RESOLVED,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                    )
                    t0 = time.perf_counter()
                    from backend.app.services.intelligence.reminder_event_readiness import (
                        evaluate_reminder_event_readiness,
                    )

                    readiness_meta = evaluate_reminder_event_readiness(
                        message=message,
                        language=lang,
                        intent=intent_meta,
                        timezone_name=ctx.locale.timezone,
                    )
                    ctx.append_stage(
                        StageName.EVALUATE_INFORMATION_READINESS,
                        "ok",
                        _READINESS_REASON[readiness_meta.status],
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
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
                        clarification_message = (
                            readiness_meta.clarification.localized_message
                            if readiness_meta.clarification
                            else None
                        )
                        skip_generator = True
                        ctx.append_stage(
                            StageName.BUILD_CLARIFICATION_RESPONSE,
                            "ok",
                            ReasonCode.CLARIFICATION_PREPARED,
                            duration_ms=(time.perf_counter() - t0) * 1000.0,
                        )
                else:
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
                    try:
                        intent_meta = self._intent_resolver(
                            message=message,
                            language=lang,
                            has_verified_notification_origin=ctx.notification is not None,
                            relationship_discovery_disposition=discovery_disposition_hint,
                        )
                    except TypeError:
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
                        message=message,
                        timezone_name=ctx.locale.timezone,
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

        # CR-03.3: observe final I3 discovery-reply rule; never fabricate IntentResult.
        # Marker bind/consume happens here after readiness, using pre-resolve classification.
        discovery_reply_active = False
        continue_invited_discovery = False
        invited_exclude_keys: frozenset = frozenset()
        caution_active = assessment.action is SafetyAction.CONTINUE_WITH_CONSTRAINTS
        discovery_allow_binding = (
            rollout_mode == "structured"
            and not terminal_safety
            and not caution_active
        )
        if terminal_safety:
            try:
                from backend.app.services.i6.relationship_discovery import (
                    expire_relationship_discovery_marker_on_early_return,
                )

                expire_relationship_discovery_marker_on_early_return(
                    self._db, authenticated_user_id
                )
            except Exception:
                pass
        elif discovery_classification is not None:
            try:
                from backend.app.services.i6.relationship_discovery import (
                    DiscoveryDisposition,
                    peek_relationship_discovery_targets,
                )
                from backend.app.services.intelligence.intent_registry import (
                    DISCOVERY_REPLY_RULE_ID,
                )

                pending_keys, pending_invited = peek_relationship_discovery_targets(
                    self._db, authenticated_user_id
                )
                bind_result = None
                if (
                    intent_meta is not None
                    and intent_meta.rule_id == DISCOVERY_REPLY_RULE_ID
                ):
                    if discovery_allow_binding:
                        discovery_reply_active = True
                        bind_result = _apply_discovery_fatigue_response(
                            self._db,
                            user_id=authenticated_user_id,
                            message=message,
                            language=lang,
                            allow_binding=True,
                            classification=discovery_classification,
                        )
                        extra_reason_codes.append("I3_RELATIONSHIP_DISCOVERY_REPLY")
                    else:
                        bind_result = _apply_discovery_fatigue_response(
                            self._db,
                            user_id=authenticated_user_id,
                            message=message,
                            language=lang,
                            allow_binding=False,
                            classification=discovery_classification,
                        )
                else:
                    # Stale/unrelated marker: consume one-shot, no fact; preserve routing.
                    bind_result = _apply_discovery_fatigue_response(
                        self._db,
                        user_id=authenticated_user_id,
                        message=message,
                        language=lang,
                        allow_binding=False,
                        classification=discovery_classification,
                    )
                    if (
                        discovery_classification.disposition
                        is DiscoveryDisposition.UNRELATED
                    ):
                        extra_reason_codes.append("I6_DISCOVERY_MARKER_UNRELATED")
                    else:
                        extra_reason_codes.append("I6_DISCOVERY_MARKER_STALE")

                # Q4: invited ANSWER may immediately schedule next invited missing target.
                answered = (
                    bind_result is not None
                    and getattr(bind_result, "disposition", None)
                    is DiscoveryDisposition.ANSWER
                )
                if pending_invited and answered and discovery_allow_binding:
                    continue_invited_discovery = True
                    # Exclude all keys from this marker same-turn (answered + unanswered).
                    marker_keys = tuple(
                        getattr(bind_result, "marker_keys", None) or pending_keys or ()
                    )
                    invited_exclude_keys = frozenset(marker_keys)
            except Exception:
                pass

        # I5 care-navigation — ONE canonical path via care_navigation_directory facade.
        # DIRECTORY_HIT → structured response; DIRECTORY_MISS → fail-safe.
        # Never fall through to LLM provider generation.
        # REMINDER/event (I3) owns schedule phrasing — do not let care-nav steal it.
        directory_message: Optional[str] = None
        care_nav_handled = False
        _reminder_owned = (
            intent_meta is not None
            and intent_meta.intent_id is IntentId.REMINDER
        )
        if (
            not terminal_safety
            and not discovery_reply_active
            and not _reminder_owned
        ):
            from backend.app.services.i5.care_navigation_directory import (
                CareNavEntity,
                STATUS_NO_VERIFIED,
                STATUS_VERIFIED,
                fail_safe_user_message,
                is_care_navigation_query,
                resolve_care_navigation,
            )

            if is_care_navigation_query(message):
                care_nav_handled = True
                try:
                    if self._db is None:
                        raise RuntimeError("care_nav_requires_db")
                    care_nav = resolve_care_navigation(
                        self._db,
                        message,
                        language=lang,
                        authenticated_user_id=authenticated_user_id,
                    )
                    if care_nav is None:
                        # Detector said care-nav; still fail-closed (no LLM invent).
                        directory_message = fail_safe_user_message(
                            CareNavEntity.SPECIALIST, lang
                        )
                        extra_reason_codes.append("CARE_NAVIGATION_FAIL_CLOSED")
                        extra_reason_codes.append("NO_VERIFIED_DIRECTORY_RESULT")
                    else:
                        directory_message = care_nav.user_message
                        extra_reason_codes.append(
                            "CARE_NAVIGATION_VERIFIED"
                            if care_nav.status == STATUS_VERIFIED
                            else "CARE_NAVIGATION_NO_VERIFIED"
                        )
                        if care_nav.status == STATUS_NO_VERIFIED:
                            extra_reason_codes.append("NO_VERIFIED_DIRECTORY_RESULT")
                except Exception:
                    directory_message = fail_safe_user_message(
                        CareNavEntity.SPECIALIST, lang
                    )
                    extra_reason_codes.append("CARE_NAVIGATION_FAIL_CLOSED")
                    extra_reason_codes.append("NO_VERIFIED_DIRECTORY_RESULT")
                skip_generator = True
                clarification_message = None

        # I8 primary-user nutrition — ONE canonical operational path.
        # READY nutrition intents → generate_operational_action(domain=nutrition, persist=True).
        # Never LLM-invent meal plans / therapeutic diets.
        nutrition_message: Optional[str] = None
        if (
            not terminal_safety
            and not discovery_reply_active
            and not care_nav_handled
            and not skip_generator
            and intent_meta is not None
            and readiness_meta is not None
            and readiness_meta.status is ReadinessStatus.READY
        ):
            from backend.app.services.i8.nutrition_primary_path import (
                execute_primary_nutrition_action,
                is_nutrition_operational_intent,
            )

            if is_nutrition_operational_intent(intent_meta.intent_id):
                try:
                    if self._db is None:
                        raise RuntimeError("nutrition_path_requires_db")
                    nutrition = execute_primary_nutrition_action(
                        self._db,
                        user_id=authenticated_user_id,
                        actor_user_id=authenticated_user_id,
                        request=message,
                        language=lang,
                        persist=True,
                        generation_mode="reactive",
                    )
                    nutrition_message = nutrition.user_message
                    extra_reason_codes.append("NUTRITION_PRIMARY_PATH")
                    extra_reason_codes.append(f"NUTRITION_STATUS_{nutrition.status}")
                    if nutrition.grounded:
                        extra_reason_codes.append("I8_NUTRITION_ACTION")
                    if nutrition.fail_safe:
                        extra_reason_codes.append("NUTRITION_FAIL_SAFE")
                    if nutrition.action_id is not None:
                        extra_reason_codes.append(
                            f"I8_NUTRITION_ACTION_ID_{nutrition.action_id}"
                        )
                except Exception:
                    nutrition_message = (
                        "I cannot create a verified nutrition action from the available context."
                        if lang == "en"
                        else "با زمینه موجود نمی‌توانم یک اقدام تغذیه‌ای تأییدشده بسازم."
                    )
                    extra_reason_codes.append("NUTRITION_PRIMARY_PATH_FAIL_CLOSED")
                skip_generator = True
                clarification_message = None

        # I8 primary-user exercise/activity — ONE canonical operational path.
        # READY ACTIVITY intents → generate_operational_action(domain=exercise, persist=True).
        # Never LLM-invent exercise medical prescriptions / clearances.
        exercise_message: Optional[str] = None
        if (
            not terminal_safety
            and not discovery_reply_active
            and not care_nav_handled
            and not skip_generator
            and intent_meta is not None
            and readiness_meta is not None
            and readiness_meta.status is ReadinessStatus.READY
        ):
            from backend.app.services.i8.exercise_primary_path import (
                execute_primary_exercise_action,
                is_activity_operational_intent,
            )

            if is_activity_operational_intent(intent_meta.intent_id):
                try:
                    if self._db is None:
                        raise RuntimeError("exercise_path_requires_db")
                    exercise = execute_primary_exercise_action(
                        self._db,
                        user_id=authenticated_user_id,
                        actor_user_id=authenticated_user_id,
                        request=message,
                        language=lang,
                        persist=True,
                        generation_mode="reactive",
                    )
                    exercise_message = exercise.user_message
                    extra_reason_codes.append("EXERCISE_PRIMARY_PATH")
                    extra_reason_codes.append(f"EXERCISE_STATUS_{exercise.status}")
                    if exercise.grounded:
                        extra_reason_codes.append("I8_EXERCISE_ACTION")
                    if exercise.fail_safe:
                        extra_reason_codes.append("EXERCISE_FAIL_SAFE")
                    if exercise.action_id is not None:
                        extra_reason_codes.append(
                            f"I8_EXERCISE_ACTION_ID_{exercise.action_id}"
                        )
                except Exception:
                    exercise_message = (
                        "I cannot create a verified activity action from the available context."
                        if lang == "en"
                        else "با زمینه موجود نمی‌توانم یک اقدام فعالیت تأییدشده بسازم."
                    )
                    extra_reason_codes.append("EXERCISE_PRIMARY_PATH_FAIL_CLOSED")
                skip_generator = True
                clarification_message = None

        # I1 dispatch: I3-READY REMINDER/event → existing UserEvent (not I8).
        # No direct Notification write; I10 scheduler consumes reminder fields.
        reminder_message: Optional[str] = None
        if (
            not terminal_safety
            and not discovery_reply_active
            and not care_nav_handled
            and intent_meta is not None
            and readiness_meta is not None
            and readiness_meta.status is ReadinessStatus.READY
            and intent_meta.intent_id.value == "reminder"
            and (not skip_generator or clarification_message is None)
        ):
            from backend.app.services.intelligence.reminder_event_dispatch import (
                dispatch_reminder_user_event,
            )

            try:
                if self._db is None:
                    raise RuntimeError("reminder_dispatch_requires_db")
                dispatched = dispatch_reminder_user_event(
                    self._db,
                    user_id=authenticated_user_id,
                    message=message,
                    timezone_name=ctx.locale.timezone,
                )
                extra_reason_codes.append("I3_REMINDER_USEREVENT_DISPATCH")
                if dispatched.get("duplicate"):
                    extra_reason_codes.append("I3_REMINDER_USEREVENT_DEDUPED")
                elif dispatched.get("created"):
                    extra_reason_codes.append("I3_REMINDER_USEREVENT_CREATED")
                if lang == "fa":
                    reminder_message = "رویداد در «برنامه من» ثبت شد."
                elif lang == "ar":
                    reminder_message = "تم حفظ الموعد في «جدولي»."
                else:
                    reminder_message = "I’ve added this to My Schedule."
            except Exception:
                extra_reason_codes.append("I3_REMINDER_USEREVENT_FAIL_CLOSED")
                reminder_message = (
                    "I couldn’t save that schedule item right now."
                    if lang == "en"
                    else "الان نتوانستم این مورد را در برنامه ثبت کنم."
                )
            skip_generator = True
            clarification_message = None

        # CR-03.2: discovery marker already classified/consumed above (before I5/I8/reminder).

        # CR-01/CR-02 NBQ: select directive on normal structured path.
        # Visible append is gated separately (fatigue/caution/specialized/BE_HEARD).
        discovery_question_id: Optional[str] = None
        discovery_target_key: Optional[str] = None
        discovery_localized_question: Optional[str] = None
        discovery_companion_key: Optional[str] = None
        discovery_companion_question: Optional[str] = None
        visible_nbq_eligible = False
        relationship_guidance: Optional[str] = None
        interaction_need_value: Optional[str] = None
        interaction_need_obj: Optional[Any] = None
        allow_governed_knowledge = False
        if (
            not terminal_safety
            and not skip_generator
            and rollout_mode == "structured"
            and snapshot is not None
            and intent_meta is not None
            and readiness_meta is not None
        ):
            from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
            from backend.app.services.intelligence.adaptive_interaction import (
                resolve_adaptive_interaction,
            )
            from backend.app.services.intelligence.next_best_question import (
                detect_discovery_invitation,
                select_next_best_question,
            )
            from backend.app.services.intelligence.psychological_interaction import (
                InteractionNeed,
                classify_interaction_need,
            )

            # Context-fit: classify need before final visible-NBQ eligibility.
            need = classify_interaction_need(
                message=message, intent=intent_meta, language=lang
            )
            interaction_need_obj = need
            interaction_need_value = need.value

            phrase_invitation = detect_discovery_invitation(message, lang)
            invited_rd_mode = bool(continue_invited_discovery or phrase_invitation)

            directive = select_next_best_question(
                snapshot=snapshot,
                intent=intent_meta,
                readiness=readiness_meta,
                language=lang,
                message=message,
                force_invitation=continue_invited_discovery,
                exclude_keys=invited_exclude_keys,
            )
            if directive is not None:
                discovery_question_id = directive.question_id
                discovery_target_key = directive.target_key
                discovery_localized_question = directive.localized_question
                discovery_companion_key = getattr(
                    directive, "companion_target_key", None
                )
                discovery_companion_question = getattr(
                    directive, "companion_localized_question", None
                )
                if (
                    need is not InteractionNeed.BE_HEARD
                    and not caution_active
                    and readiness_meta.status is ReadinessStatus.READY
                    and _fatigue_permits_discovery(
                        self._db, authenticated_user_id, invited=invited_rd_mode
                    )
                ):
                    visible_nbq_eligible = True

            adaptive = resolve_adaptive_interaction(snapshot)
            for code in adaptive.reason_codes:
                if code not in extra_reason_codes:
                    extra_reason_codes.append(code)

            relationship_guidance = PersonaPolicyV1.relationship_guidance_block(
                need.value,
                lang,
                nbq_scheduled=visible_nbq_eligible,
                response_length=adaptive.response_length,
                listen_before_advice=adaptive.listen_before_advice,
            )

        # Structured I5 gate: decide after CR-02 need + I6 adaptive, before generation.
        if (
            rollout_mode == "structured"
            and not terminal_safety
            and not skip_generator
        ):
            allow_governed_knowledge = allow_governed_knowledge_decision(
                terminal_safety=terminal_safety,
                message=message,
                language=lang,
                intent=intent_meta,
                interaction_need=interaction_need_obj,
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
            out_message = (
                directory_message
                or nutrition_message
                or exercise_message
                or reminder_message
                or clarification_message
                or ""
            )
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
            # Directory/nutrition/exercise-owned responses are already fail-safe; skip Gate3 rewrite.
            if (
                directory_message is not None
                or nutrition_message is not None
                or exercise_message is not None
                or reminder_message is not None
            ):
                ctx.append_stage(
                    StageName.VALIDATE_GENERATION_RESULT,
                    "ok",
                    ReasonCode.RESPONSE_VALIDATED,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
            else:
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
                from backend.app.services.intelligence.intent_registry import (
                    DISCOVERY_REPLY_RULE_ID,
                )

                skip_generic_kc_extraction = bool(
                    discovery_reply_active
                    and intent_meta is not None
                    and intent_meta.rule_id == DISCOVERY_REPLY_RULE_ID
                )
                call_kwargs: Dict[str, Any] = {
                    "notification_context": (
                        None
                        if use_structured_context
                        else generation_notification_context
                    ),
                    "structured_context_projection": structured_projection,
                    "structured_preferred_name": structured_preferred_name,
                    "use_structured_context": use_structured_context,
                    "use_intelligence_safety": True,
                    "safety_constraints": caution_constraints,
                }
                if _generator_accepts_kwarg(generator, "relationship_guidance"):
                    call_kwargs["relationship_guidance"] = relationship_guidance
                if _generator_accepts_kwarg(generator, "skip_generic_kc_extraction"):
                    call_kwargs["skip_generic_kc_extraction"] = (
                        skip_generic_kc_extraction
                    )
                if _generator_accepts_kwarg(generator, "allow_governed_knowledge"):
                    call_kwargs["allow_governed_knowledge"] = allow_governed_knowledge
                raw = generator(
                    authenticated_user_id,
                    message,
                    None,
                    **call_kwargs,
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

            durable_memory_id = raw.get("durable_memory_id")
            if durable_memory_id is not None:
                try:
                    durable_memory_id = int(durable_memory_id)
                except (TypeError, ValueError):
                    durable_memory_id = None

            # CR-02 / Q4.2B: append at most two invited questions (normal stays one).
            nbq_was_appended = False
            if (
                visible_nbq_eligible
                and discovery_localized_question
                and discovery_target_key
            ):
                from backend.app.services.intelligence.psychological_interaction import (
                    append_discovery_questions,
                )

                q_list = [discovery_localized_question]
                if discovery_companion_question:
                    q_list.append(discovery_companion_question)
                gen_message = append_discovery_questions(gen_message, q_list)
                nbq_was_appended = True

            validated = self._safety_validator(text=gen_message, language=lang)
            out_message = validated.message
            post_val_status = validated.status
            # Defense-in-depth only: primary gate already skipped generator for care-nav.
            # If we somehow reached generation on a care-nav message, replace with fail-safe.
            if care_nav_handled:
                from backend.app.services.i5.care_navigation_directory import (
                    CareNavEntity,
                    fail_safe_user_message,
                )

                out_message = directory_message or fail_safe_user_message(
                    CareNavEntity.SPECIALIST, lang
                )
                extra_reason_codes.append("CARE_NAV_LLM_FALLTHROUGH_BLOCKED")
                nbq_was_appended = False
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
            # Mark asked only after SAFE final validation (never on replace/fail-closed).
            if (
                nbq_was_appended
                and post_val_status is PostGenerationSafetyStatus.SAFE
                and discovery_target_key
            ):
                # Invited origin when invitation.* directive (not contextual/tier-a).
                mark_invited = bool(
                    discovery_question_id
                    and str(discovery_question_id).startswith("nbq.q.invitation.")
                )
                if mark_invited:
                    _mark_relationship_discovery_asked(
                        self._db,
                        user_id=authenticated_user_id,
                        target_key=discovery_target_key,
                        invited=True,
                        companion_key=discovery_companion_key,
                    )
                else:
                    # Legacy CR04B call shape: no invited/companion kwargs.
                    _mark_relationship_discovery_asked(
                        self._db,
                        user_id=authenticated_user_id,
                        target_key=discovery_target_key,
                    )

            # CR-03.1: finalize durable raw to exact final user-visible response.
            # Fail closed on history eligibility if finalization cannot achieve parity.
            if durable_memory_id is not None and self._db is not None:
                try:
                    from backend.app.services.i7.governed_raw import (
                        finalize_durable_raw_response,
                        mark_durable_raw_ineligible,
                    )

                    fin = finalize_durable_raw_response(
                        self._db,
                        user_id=authenticated_user_id,
                        memory_id=durable_memory_id,
                        final_response=out_message,
                        actor_user_id=authenticated_user_id,
                        commit=True,
                    )
                    if not fin.durable or fin.reason not in (
                        "FINALIZED",
                    ):
                        # Collision / not-durable / unexpected: ensure draft is not eligible.
                        if fin.reason not in (
                            "MARKED_INELIGIBLE",
                            "FINALIZE_KEY_COLLISION",
                            "FINALIZE_INTEGRITY_CONFLICT",
                            "FINALIZE_UNEXPECTED_ERROR",
                        ):
                            mark_durable_raw_ineligible(
                                self._db,
                                user_id=authenticated_user_id,
                                memory_id=durable_memory_id,
                                actor_user_id=authenticated_user_id,
                                reason=str(fin.reason or "FINALIZATION_FAILED"),
                                commit=True,
                            )
                        extra_reason_codes.append("I7_RAW_FINALIZATION_FAILED")
                except Exception:
                    try:
                        self._db.rollback()
                    except Exception:
                        pass
                    try:
                        from backend.app.services.i7.governed_raw import (
                            mark_durable_raw_ineligible,
                        )

                        mark_durable_raw_ineligible(
                            self._db,
                            user_id=authenticated_user_id,
                            memory_id=durable_memory_id,
                            actor_user_id=authenticated_user_id,
                            reason="FINALIZE_ORCHESTRATOR_EXCEPTION",
                            commit=True,
                        )
                    except Exception:
                        try:
                            self._db.rollback()
                        except Exception:
                            pass
                    extra_reason_codes.append("I7_RAW_FINALIZATION_FAILED")

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
            discovery_question_id=discovery_question_id,
            discovery_target_key=discovery_target_key,
            interaction_need=interaction_need_value,
        )
