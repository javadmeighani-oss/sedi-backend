"""Section 15-I1/I3/I4 — Connected Intelligence Orchestrator.

Always invoked by POST /interact/chat for the normal generation path.
Flag OFF = compatibility mode; flag ON = structured mode.
I3 intent/readiness runs only in structured mode after successful I2 assembly.
I4 safety precheck runs in both modes (never skipped for compatibility).
"""

from __future__ import annotations

import inspect
import re
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


def _topic_carried(db: Any, user_id: Any, message: str, language: str) -> bool:
    try:
        from backend.app.services.intelligence.topic_carryover import find_carried_topic

        return bool(find_carried_topic(db, int(user_id), message or "", language))
    except Exception:
        return False


def allow_governed_knowledge_decision(
    *,
    terminal_safety: bool,
    message: str,
    language: str,
    intent: Optional[IntentResult],
    interaction_need: Optional[Any],
    topic_carried: bool = False,
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
    from backend.app.services.intelligence.intent_registry import (
        DISCOVERY_REPLY_RULE_ID,
    )
    from backend.app.services.intelligence.psychological_interaction import (
        InteractionNeed,
    )

    intent_id = intent.intent_id if intent is not None else None
    request_kind = intent.request_kind if intent is not None else None
    rule_id = getattr(intent, "rule_id", None) if intent is not None else None
    # User-memory discovery capture is not a governed knowledge ask (existing I3 rule).
    if rule_id == DISCOVERY_REPLY_RULE_ID:
        return False
    if intent_id in (IntentId.REMINDER, IntentId.NOTIFICATION_FOLLOW_UP):
        return False

    factual_intent = intent_id in _GOVERNED_KNOWLEDGE_INTENT_IDS
    medical = is_medical_care_intent(message or "", language or "en")
    wellbeing = is_mental_wellbeing_intent(message or "", language or "en")
    informational = request_kind is RequestKind.INFORMATIONAL

    need = interaction_need
    if need is InteractionNeed.BE_HEARD:
        # Pure emotional listen: suppress. Explicit factual/evidence via I3 intent: allow.
        # D-022: an emotional message that ALSO asks what to do ("خیلی استرس دارم، چیکار کنم؟") may be
        # accompanied by governed psychology knowledge (listen-first style is added by the I5 renderer);
        # "just listen / no advice" cues keep it suppressed.
        if factual_intent and informational:
            return True
        from backend.app.services.intelligence.psychological_interaction import (
            asks_for_help_not_just_listening,
        )

        return bool(wellbeing and asks_for_help_not_just_listening(message or "", language or "en"))

    # Non-BE_HEARD: existing medical/wellbeing classifiers or knowledge intents. A topic-less follow-up
    # ("برنامه بده", "این بیماری") continues the earlier verified subject (topic_carryover, I1).
    if factual_intent or medical or wellbeing or topic_carried:
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

_FOLLOWUP_CONTEXT_KEYS = ("template_key", "opening_message", "followup_result")


def _followup_only_context(context: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """R-052 / R-070: in structured mode the model must still know the question Sedi just asked and how the user answered it
    (both are Sedi's own sentence / a bounded token - never notification body or health data). Nothing else is forwarded."""
    if not context or not (context.get("opening_message") or context.get("followup_result")):
        return None
    return {k: context[k] for k in _FOLLOWUP_CONTEXT_KEYS if context.get(k) is not None}


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

    def _continue_reminder_clarification(self, ctx, user_id: int, message: str, lang: str) -> str:
        """D-130: Sedi asked «کِی یادت بندازم؟» and the user answers «حدود ۵ دقیقه دیگه» (no reminder word) - that answer is the
        reminder, not a new general question the LLM would refuse. Returns the answer phrased as a reminder request, or
        the message unchanged. Deterministic, fail-open, only within 30 minutes of Sedi's question."""
        try:
            if self._db is None or not message or not message.strip():
                return message
            from datetime import datetime, timedelta

            from backend.app import models
            from backend.app.services.intelligence.reminder_event_readiness import (
                answer_as_reminder_request,
                is_reminder_clarification,
                parse_reminder_event_draft,
            )

            rows = (
                self._db.query(models.Memory)
                .filter(models.Memory.user_id == user_id)
                .order_by(models.Memory.created_at.desc())
                .limit(4)
                .all()
            )
            fresh = [
                r for r in rows
                if r.created_at is not None
                and datetime.utcnow() - r.created_at.replace(tzinfo=None) <= timedelta(minutes=30)
            ]
            if not fresh:
                return message
            tz_name = self._reminder_timezone(ctx, user_id)
            # Javad 2026-11-09: Sedi asked «صبح یا عصر؟» for an ambiguous hour; the one-word answer completes THAT request.
            from backend.app.services.intelligence.reminder_event_readiness import (
                is_period_clarification,
                period_answer_as_request,
            )

            if is_period_clarification(getattr(fresh[0], "sedi_response", None)):
                combined = period_answer_as_request(getattr(fresh[0], "user_message", None) or "", message)
                if combined:
                    # Codex P2 (PR 179): the combined request is ALWAYS the thing to evaluate next, even when it is now in the
                    # past («today at 5» answered «morning»): readiness then asks for another time instead of losing the original.
                    return combined
            asked = is_reminder_clarification(getattr(fresh[0], "sedi_response", None))
            if not asked:
                # Javad 2026-10-28: after an unfinished reminder request ("نوتیف بفرست ساعت ۲۱:۳۵" with no day) a short answer
                # that only carries a time/day continues THAT request, even when another turn was answered in between.
                if len(message.split()) > 8:
                    return message
                from backend.app.services.intelligence.intent_registry import IntentId, resolve_intent

                def _is_reminder_request(text: str) -> bool:
                    return resolve_intent(message=text or "", language=lang).intent_id is IntentId.REMINDER

                if _is_reminder_request(message):
                    return message  # a complete request of its own
                for r in fresh:
                    prior = getattr(r, "user_message", None) or ""
                    if not _is_reminder_request(prior):
                        continue
                    _, prior_missing = parse_reminder_event_draft(message=prior, timezone_name=tz_name, language=lang)
                    asked = prior_missing is not None  # the earlier request never got its time
                    if prior_missing == "recurrence":
                        # the earlier request waits for «daily / weekly / once»: only a reply that SAYS it continues it
                        # («میگم ۹ صبح» repeats a time, it is not that answer - Javad 2026-11-21)
                        from backend.app.services.intelligence.reminder_event_readiness import answer_names_recurrence

                        asked = answer_names_recurrence(message)
                    break
            if not asked:
                return message
            from backend.app.services.intelligence.reminder_event_readiness import answer_names_recurrence, is_recurrence_question

            if is_recurrence_question(getattr(fresh[0], "sedi_response", None)) and not answer_names_recurrence(message):
                return message  # «میگم ۹ صبح» repeats a time; it does not answer «every day or every week?» (Javad 2026-11-21)
            candidate = answer_as_reminder_request(message, lang)
            draft, missing = parse_reminder_event_draft(
                message=candidate,
                timezone_name=tz_name,
                language=lang,
            )
            if draft is None or missing is not None:
                return message
            return candidate
        except Exception:
            return message

    def _continue_specialist_offer(self, ctx, user_id: int, message: str, lang: str) -> str:
        """R-033: Sedi offered «اگه دوست داری، یه متخصص مناسب برات پیدا کنم؟» and the user answers «آره» - that answer IS the
        find-a-specialist request. Returns the explicit request (which the care-navigation directory flow understands) or
        the message unchanged. Deterministic, fail-open, only within 30 minutes of Sedi's offer."""
        try:
            if self._db is None or not message or not message.strip():
                return message
            from datetime import datetime, timedelta

            from backend.app.services.i6.consent_service import PERM_READ, has_permission_readonly
            from backend.app.services.i7.retention import query_eligible_raw
            from backend.app.services.intelligence.specialist_offer import specialist_request_for_reply

            if not has_permission_readonly(self._db, user_id, PERM_READ):
                return message  # past conversation is not read without memory-read consent (Codex P1, PR 208)
            rows = query_eligible_raw(self._db, user_id, limit=4) or []  # the retention-eligible reader, newest first
            last = rows[0] if rows else None
            if last is None or last.created_at is None:
                return message
            if datetime.utcnow() - last.created_at.replace(tzinfo=None) > timedelta(minutes=30):
                return message
            recent = [getattr(r, "user_message", None) for r in rows]
            return specialist_request_for_reply(getattr(last, "sedi_response", None), message, lang, context=recent) or message
        except Exception:
            return message

    def _with_care_journey(self, directory_message: Optional[str], request_text: str, lang: str, user_id: int, said: Optional[str] = None) -> tuple[Optional[str], bool]:
        """R-109 step 1b-2: append the care-journey block (stabilising care + up to three interview questions, or just «how are you
        now?» while a journey is open) to a doctor/lab answer and track the follow-up. Specialist / hospital / centre / lab requests
        only (a pharmacy lookup is not a care journey). Fail-open: the plain answer is returned unchanged."""
        try:
            if self._db is None or not directory_message:
                return directory_message, False
            from backend.app.services.i5 import care_navigation_directory as _cn
            from backend.app.services.care_journey import journey as _journey

            if _cn.is_directory_source_question(request_text):
                return directory_message, False
            from backend.app.services.i5.care_nav_interview import is_place_question

            if is_place_question(directory_message):
                return directory_message, False  # R-120 am.1: a place question stands ALONE (no care block, no second question)
            entity = _cn.parse_care_nav_request(request_text, language=lang).entity
            if entity is _cn.CareNavEntity.PHARMACY:
                return directory_message, False
            block = _journey.results_block(self._db, user_id, request_text, lang, explanations=self._interview_explanations(user_id, said))
            if not block:
                return directory_message, False
            return directory_message.rstrip() + "\n\n" + block, True
        except Exception:  # noqa: BLE001
            return directory_message, False

    def _memory_first_request(self, user_id: int, message: str, lang: str):
        """R-114: ``care_nav_memory.complete_request`` with the consent-gated recent turns; None = the existing flow (fail-open)."""
        try:
            if self._db is None or not message or not message.strip():
                return None
            from backend.app.services.i5 import care_nav_memory
            from backend.app.services.i6.consent_service import PERM_READ, has_permission_readonly
            from backend.app.services.i7.retention import query_eligible_raw

            rows = (query_eligible_raw(self._db, user_id, limit=10) or []) if has_permission_readonly(self._db, user_id, PERM_READ) else []  # R-120 am.4: far enough back to reach the request of the open doctor talk
            return care_nav_memory.complete_request(self._db, user_id, message, lang, rows=list(rows))
        except Exception:  # noqa: BLE001
            return None

    def _interview_explanations(self, user_id: int, said: Optional[str]) -> list:
        """R-120 am.2: what the user told Sedi in this doctor interview (answers to her interview questions, newest last), read through the
        consent-gated, retention-filtered reader. [] = nothing to build personal care from (fail-open)."""
        try:
            if self._db is None:
                return []
            from backend.app.services.care_journey import journey as _journey
            from backend.app.services.i6.consent_service import PERM_READ, has_permission
            from backend.app.services.i7.retention import query_eligible_raw

            if not has_permission(self._db, user_id, PERM_READ):
                return []
            from datetime import datetime, timedelta

            from backend.app.services.i5.care_nav_interview import is_place_question, is_reason_question

            rows = query_eligible_raw(self._db, user_id, limit=8) or []
            told: list = []
            now = datetime.utcnow()
            # only THIS request's interview: the unbroken run of newest turns in which Sedi was asking (reason / place / interview / follow-up),
            # within 30 minutes - an earlier interview about another complaint never feeds this visit's care (Codex P2, PR 228)
            for i, r in enumerate(rows):
                reply = getattr(r, "sedi_response", None)
                created = getattr(r, "created_at", None)
                if created is not None and now - created.replace(tzinfo=None) > timedelta(minutes=30):
                    break
                interview = _journey.is_interview_reply(reply) or _journey.is_followup_reply(reply)  # both interview steps
                if not (interview or is_place_question(reply) or is_reason_question(reply)):
                    break
                if interview:
                    answer = said if i == 0 else getattr(rows[i - 1], "user_message", None)
                    if answer and str(answer).strip():
                        told.append(str(answer))
            return list(reversed(told))
        except Exception:  # noqa: BLE001
            return []

    def _last_place(self, message: str, user_id: int) -> Optional[str]:
        """R-120 am.2: the place for a doctor request that names none - the newest place the user gave (or his stored residence)."""
        try:
            if self._db is None or not message:
                return None
            from backend.app.services.i5 import care_navigation_directory as _cn
            from backend.app.services.i5.care_nav_interview import last_known_place, place_status

            if not _cn.is_care_navigation_query(message) or place_status(message)[0] != "none":
                return None
            req = _cn.parse_care_nav_request(message, language="fa")
            if req.name_hint or req.entity not in (_cn.CareNavEntity.SPECIALIST, _cn.CareNavEntity.SPECIALTY_CENTER):
                return None
            from backend.app.core.conversation.memory import ConversationMemory

            rows = sorted(ConversationMemory(self._db).get_recent_messages(int(user_id), limit=60), key=lambda r: getattr(r, "id", 0), reverse=True)
            home = None
            try:
                from backend.app.services import care_state as _cs

                st = _cs.get_care_state(self._db, user_id)
                home = (st.home_area, st.home_city) if getattr(st, "home_city", None) else None
            except Exception:  # noqa: BLE001
                home = None
            return last_known_place(rows, home)
        except Exception:  # noqa: BLE001
            return None

    def _answering_open_interview(self, user_id: int) -> bool:
        """R-120 am.3: Sedi's last reply (within 30 minutes) was the OPEN interview question - the follow-up step is due even when memory
        completed the request (it used to skip the questions built from the user's explanation)."""
        try:
            from datetime import datetime, timedelta

            from backend.app.services.care_journey import journey as _journey
            from backend.app.services.i6.consent_service import PERM_READ, has_permission
            from backend.app.services.i7.retention import query_eligible_raw

            if self._db is None or not has_permission(self._db, user_id, PERM_READ):
                return False
            rows = query_eligible_raw(self._db, user_id, limit=1) or []
            if not rows or rows[0].created_at is None or datetime.utcnow() - rows[0].created_at.replace(tzinfo=None) > timedelta(minutes=30):
                return False
            reply = getattr(rows[0], "sedi_response", None)
            return _journey.is_interview_reply(reply) and not _journey.is_followup_reply(reply)
        except Exception:  # noqa: BLE001
            return False

    def _place_said_now(self, place: str, user_id: int, said: Optional[str]) -> bool:
        """R-120 am.3: the place came from THIS conversation (the current message or the last 30 minutes) - then no «as you said before» note."""
        try:
            from datetime import datetime, timedelta

            from backend.app.services.i5 import care_navigation_directory as _cn
            from backend.app.services.i7.retention import query_eligible_raw

            key = re.sub(r"[\s\u200c]+", "", place.replace("شهر ", "").split()[0] if place.strip() else "")
            texts = [said or ""]
            for r in (query_eligible_raw(self._db, user_id, limit=8) or []) if self._db is not None else []:
                created = getattr(r, "created_at", None)
                if created is not None and datetime.utcnow() - created.replace(tzinfo=None) > timedelta(minutes=30):
                    break
                texts.append(getattr(r, "user_message", "") or "")
            for text in texts:
                got = _cn._places.find_place(text)
                for part in (got.area, got.city):
                    if part and key and key in re.sub(r"[\s\u200c]+", "", part):
                        return True
            return False
        except Exception:  # noqa: BLE001
            return False

    def _known_place(self, message: str, user_id: int) -> Optional[str]:
        """R-120: the confirmed place for a doctor request whose place the user ALREADY gave (stored residence, an earlier «yes», or the
        place named with its city before) - so the place question is never asked twice. Consent-gated readers only; fail-open (None)."""
        try:
            if self._db is None or not message:
                return None
            from backend.app.services.i5 import care_navigation_directory as _cn
            from backend.app.services.i5.care_nav_interview import place_already_known

            if not _cn.is_care_navigation_query(message):
                return None
            from backend.app.core.conversation.memory import ConversationMemory

            rows = sorted(ConversationMemory(self._db).get_recent_messages(int(user_id), limit=60), key=lambda r: getattr(r, "id", 0), reverse=True)
            home = None
            try:
                from backend.app.services import care_state as _cs

                st = _cs.get_care_state(self._db, user_id)
                home = (st.home_area, st.home_city) if getattr(st, "home_city", None) else None
            except Exception:  # noqa: BLE001
                home = None
            return place_already_known(message, rows, home)
        except Exception:  # noqa: BLE001
            return None

    def _journey_intake(self, message: str, lang: str, user_id: int, said: Optional[str] = None) -> Optional[str]:
        """R-109: the interview that must come BEFORE a doctor/centre/lab introduction (None = introduce now). It needs the consent-gated
        conversation to keep its state, so without it nothing is asked."""
        try:
            if self._db is None:
                return None
            from datetime import datetime, timedelta

            from backend.app.services.i5 import care_navigation_directory as _cn
            from backend.app.services.care_journey import journey as _journey
            from backend.app.services.i6.consent_service import PERM_READ, PERM_WRITE, has_permission
            from backend.app.services.i7.retention import query_eligible_raw

            if not _cn.is_care_navigation_query(message) or _cn.is_directory_source_question(message):
                return None
            if _cn.parse_care_nav_request(message, language=lang).entity is _cn.CareNavEntity.PHARMACY:
                return None
            if not (has_permission(self._db, user_id, PERM_READ) and has_permission(self._db, user_id, PERM_WRITE)):
                return None
            rows = query_eligible_raw(self._db, user_id, limit=8) or []
            now = datetime.utcnow()
            from backend.app.services.i5 import specialty_lexicon as _sl

            # the interview counts only for THIS request's specialty (Codex P2, PR 198): the earlier heart interview does not excuse a skin search
            done = False
            for i, r in enumerate(rows):
                if (
                    _journey.is_interview_reply(getattr(r, "sedi_response", None))
                    and getattr(r, "created_at", None) is not None
                    and now - r.created_at.replace(tzinfo=None) < timedelta(minutes=30)
                ):
                    def _kind(text: str):  # the provider request kind: entity + specialty (a lab / hospital has no specialty - Codex P2, round 2)
                        if not _cn.is_care_navigation_query(text or ""):
                            return None
                        return (_cn.parse_care_nav_request(text, language=lang).entity, _sl.find_specialty(text))

                    asked = {_kind(getattr(x, "user_message", None) or "") for x in rows[i:]} - {None}
                    now_kind = _kind(message)
                    # the interview is done unless THIS request is provably another one (another provider kind, or another named
                    # specialty): raw turns of the reason flow carry no specialty, so a missing one on either side is no conflict (Codex P2, round 3)
                    conflict = bool(asked) and now_kind is not None and (
                        all(a[0] != now_kind[0] for a in asked)
                        or (now_kind[1] is not None and any(a[1] is not None for a in asked) and now_kind[1] not in {a[1] for a in asked})
                    )
                    done = not conflict
                    # R-120 (Javad 2026-11-26): the first interview asked the REASON openly; the user's explanation now gets 1-3 questions
                    # built FROM it (physical / emotional situation) before the introduction. The second step is asked once.
                    if done and i == 0 and said and not _journey.is_followup_reply(getattr(r, "sedi_response", None)):
                        from backend.app.services.i5.care_nav_interview import _SKIP_INTAKE

                        if not _SKIP_INTAKE.search(said):
                            from backend.app.services.care_journey.followup_questions import followup_message

                            return followup_message(said, lang, _sl.find_specialty(message))
                    break
            return _journey.intake_message(self._db, user_id, message, lang, intake_done=done)
        except Exception:  # noqa: BLE001
            return None

    def _apply_journey_status(self, user_id: int, message: str, lang: str) -> None:
        """DEBT-080: «بهتر شدم» closes the open care journey, «بدتر شد» escalates it to hours-level follow-up (fail-open)."""
        try:
            if self._db is None or not message or not message.strip():
                return
            from backend.app.services.care_journey import journey as _journey

            _journey.apply_status(self._db, user_id, message, lang)
        except Exception:  # noqa: BLE001
            pass

    def _record_journey_answer(self, user_id: int, message: str, lang: str = "fa") -> None:
        """R-109 step 1b-2: the answer to the journey interview becomes an I6 episode note (deterministic, consent-gated, fail-open)."""
        try:
            if self._db is None or not message or not message.strip():
                return
            from datetime import datetime, timedelta

            from backend.app.services.i6.consent_service import PERM_READ, has_permission
            from backend.app.services.i7.retention import query_eligible_raw
            from backend.app.services.care_journey import journey as _journey

            if not has_permission(self._db, user_id, PERM_READ):
                return
            rows = query_eligible_raw(self._db, user_id, limit=4) or []
            last = rows[0] if rows else None
            if last is None or last.created_at is None or datetime.utcnow() - last.created_at.replace(tzinfo=None) > timedelta(hours=6):
                return
            # the run of consecutive turns in which Sedi kept asking: the complaint may have been stated several answers ago (Codex P2, PR 199)
            context = []
            for prev, nxt in zip(rows[1:], rows):
                reply = getattr(prev, "sedi_response", None) or ""
                if not ("؟" in reply or "?" in reply):
                    break
                context.append(getattr(prev, "user_message", None))
            _journey.record_answer(
                self._db, user_id, message, getattr(last, "sedi_response", None),
                last_user_message=getattr(last, "user_message", None), language=lang, context=context,
            )
        except Exception:  # noqa: BLE001
            return

    def _continue_care_nav_interview(self, ctx, user_id: int, message: str, lang: str) -> str:
        """J3-c (D-410): Sedi asked «برای چه مشکل یا نیازی دنبال دکتر می‌گردی؟» and the user answers with a specialty, a complaint or
        «نمی‌دانم» - that answer completes the earlier doctor request. Deterministic, fail-open, only within 30 minutes. The earlier
        turn is read ONLY through the consent-gated, eligibility-filtered raw reader (a revoked memory consent means no reuse)."""
        try:
            if self._db is None or not message or not message.strip():
                return message
            from datetime import datetime, timedelta

            from backend.app.services.i6.consent_service import PERM_READ, has_permission
            from backend.app.services.i7.retention import query_eligible_raw
            from backend.app.services.i5.care_nav_interview import request_for_answer, request_for_chain, request_for_source_followup

            if not has_permission(self._db, user_id, PERM_READ):
                return message
            rows = query_eligible_raw(self._db, user_id, limit=8)
            last = rows[0] if rows else None
            if last is None or last.created_at is None:
                return message
            if datetime.utcnow() - last.created_at.replace(tzinfo=None) > timedelta(minutes=30):
                return message
            prior_q, prior_a = getattr(last, "user_message", None), getattr(last, "sedi_response", None)
            return (
                request_for_chain(rows, message, lang)  # the pending request survives partial answers (Codex P1, PR 194)
                or request_for_answer(prior_q, prior_a, message, lang)
                or request_for_source_followup(prior_q, prior_a, message, lang)
                or message
            )
        except Exception:
            return message

    def _reminder_timezone(self, ctx, user_id: int) -> Optional[str]:
        """Device/profile timezone, else the same canonical fallback the scheduler uses (profile -> memory -> default).

        R-026: the Profile screen has no timezone field, so "set your timezone in Profile" could never be satisfied;
        a reminder uses the exact timezone the reminder scheduler will use anyway.
        """
        tz = ctx.locale.timezone
        if tz:
            return tz
        try:
            if self._db is not None:
                from backend.app.services.gate4.policy_prefs_bridge import (
                    resolve_validated_user_timezone,
                )

                return resolve_validated_user_timezone(self._db, user_id)
        except Exception:
            pass
        return None

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
        # I7 records the user's own words, even when a later stage rewrites `message` (reminder/specialist continuation).
        original_user_message = message
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
                from backend.app.services.intelligence.emergency_lines import finalize_terminal_message

                safety_message = finalize_terminal_message(safety_message, assessment, self._db, authenticated_user_id)
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

            # R-109 step 1b-2: an answer to the journey interview is recorded as an episode note.
            self._record_journey_answer(authenticated_user_id, message, lang)
            self._apply_journey_status(authenticated_user_id, message, lang)
            # D-130: an answer to Sedi's own reminder question continues that reminder.
            message = self._continue_reminder_clarification(ctx, authenticated_user_id, message, lang)
            # R-033: «آره» to Sedi's offer to find a specialist is the find-a-specialist request.
            message = self._continue_specialist_offer(ctx, authenticated_user_id, message, lang)
            # J3-c: «which kind of doctor / why?» was asked first; the answer completes THAT doctor request.
            message = self._continue_care_nav_interview(ctx, authenticated_user_id, message, lang)
            # R-114 / R-115: an incomplete doctor request is completed from MEMORY (problem, stored place, insistence) - never re-asked.
            _memory_req = self._memory_first_request(authenticated_user_id, message, lang)
            _memory_notes: tuple = ()
            if _memory_req is not None:
                message, _memory_notes = _memory_req.text, _memory_req.notes
                extra_reason_codes.extend(_memory_req.reason_codes)

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
                        timezone_name=self._reminder_timezone(ctx, authenticated_user_id),
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
                        timezone_name=self._reminder_timezone(ctx, authenticated_user_id),
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
                        if (
                            getattr(readiness_meta.clarification, "template_id", "") == "tpl.goal.v1"
                            and intent_meta is not None
                            and intent_meta.intent_id in (IntentId.NUTRITION, IntentId.ACTIVITY)
                        ):
                            # Stage 06 / B1.5-a: the goal reply is bound to I6 (intake.goal) like any discovery answer.
                            _mark_relationship_discovery_asked(
                                self._db,
                                user_id=authenticated_user_id,
                                target_key="intake.goal",
                                invited=True,
                            )
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
        plan_domain_ctx: Optional[str] = None
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
                        # Stage 06 / B1.5-a: keep the friendly plan intake going after each answer.
                        _pk = tuple(pending_keys or ())
                        if any(k.startswith(("function.", "intake.")) for k in _pk):
                            plan_domain_ctx = (
                                "activity"
                                if any(k.startswith("intake.exercise_") or k == "intake.equipment" for k in _pk)
                                else "nutrition"
                            )
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
                if answered and discovery_allow_binding:
                    # The snapshot predates this answer: never re-ask the same keys this turn.
                    # Exclude all keys from this marker same-turn (answered + unanswered), for
                    # invited discovery AND the plan-intake interview (R-008).
                    marker_keys = tuple(
                        getattr(bind_result, "marker_keys", None) or pending_keys or ()
                    )
                    invited_exclude_keys = frozenset(marker_keys)
                    if pending_invited:
                        continue_invited_discovery = True
            except Exception:
                pass

        # I5 care-navigation — ONE canonical path via care_navigation_directory facade.
        # DIRECTORY_HIT → structured response; DIRECTORY_MISS → fail-safe.
        # Never fall through to LLM provider generation.
        # REMINDER/event (I3) owns schedule phrasing — do not let care-nav steal it.
        directory_message: Optional[str] = None
        directory_links: tuple = ()  # R-107 am.3
        directory_intro_state: Optional[dict] = None  # R-116: what this doctor introduction covered (the «next five» continues from it)
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
                is_directory_source_question,
                resolve_care_navigation,
            )

            from backend.app.services.i5.care_nav_interview import first_question as reason_question

            from backend.app.services.i5 import provider_next as _pn

            _again = _pn.again_reply(self._db, authenticated_user_id, original_user_message, lang)  # D-550: «introduce them again» = the same five
            _next_req = None if _again is not None else _pn.next_request(self._db, authenticated_user_id, message, lang)  # R-116: «the next five»
            _known = self._known_place(message, authenticated_user_id) if (_next_req is None and _again is None) else None
            if _known:  # R-120: a place the user already gave is not asked again
                from backend.app.services.i5.care_nav_interview import _swap_place

                message = _swap_place(message, _known, lang)
                extra_reason_codes.append("R120_PLACE_ALREADY_KNOWN")
            elif _next_req is None and _again is None:
                _last = self._last_place(message, authenticated_user_id)
                if _last:  # R-120 am.2: a request without a place uses the place he already gave (named briefly, so he can correct it)
                    message = f"{message.strip()} در {_last}" if lang == "fa" else f"{message.strip()} in {_last}"
                    if not self._place_said_now(_last, authenticated_user_id, original_user_message):
                        from backend.app import sedi_copy as _copy

                        _memory_notes = tuple(_memory_notes) + (_copy.t("care_nav.memory.place_used", lang, place=_last.replace("شهر ", "")),)
                    extra_reason_codes.append("R120_LAST_PLACE_USED")
            _reason_q = None if (_next_req is not None or _again is not None) else (reason_question(message, lang) if not is_directory_source_question(message) else None)
            # R-109: reason and place are settled -> the grouped interview comes BEFORE the introduction (the best fit is chosen after)
            _intake_q = None if (_reason_q or _next_req is not None or _again is not None) else (self._journey_intake(message, lang, authenticated_user_id, said=original_user_message) if (_memory_req is None or self._answering_open_interview(authenticated_user_id)) else None)
            if _memory_req is not None and not _reason_q and _again is None and self._db is not None:
                from backend.app.services.care_journey import journey as _cj

                _cj.track(self._db, authenticated_user_id, _memory_req.tier_text or message, lang)  # the follow-up starts even though no interview is asked (urgency from the ORIGINAL complaint)
            if _again is not None:
                care_nav_handled = True
                directory_message = _again.message
                directory_links = tuple(_again.links)
                directory_intro_state = _again.intro_state  # the same state: «the next five» still continues after the re-show
                extra_reason_codes.append("D550_PROVIDER_AGAIN")
                skip_generator = True
                clarification_message = None
            elif _next_req is not None:
                care_nav_handled = True
                try:
                    from backend.app.services.i5.care_navigation_directory import resolve_care_navigation_for_request

                    _next_res = resolve_care_navigation_for_request(self._db, _next_req)
                    directory_message = _pn.compose(_next_res, lang)
                    directory_links = tuple(getattr(_next_res, "links", ()) or ())
                    directory_intro_state = getattr(_next_res, "intro_state", None)
                    extra_reason_codes.append("R116_NEXT_FIVE" if _next_res.status == STATUS_VERIFIED else "R116_NEXT_FIVE_NONE_LEFT")
                except Exception:
                    directory_message = fail_safe_user_message(CareNavEntity.SPECIALIST, lang)
                    extra_reason_codes.append("CARE_NAVIGATION_FAIL_CLOSED")
                skip_generator = True
                clarification_message = None
            elif _reason_q:
                # J3-c: no specialty named -> ask WHY / WHICH doctor first (one question), never a list of random doctors.
                care_nav_handled = True
                directory_message = _reason_q
                extra_reason_codes.append("CARE_NAVIGATION_REASON_ASKED")
                skip_generator = True
                clarification_message = None
            elif _intake_q:
                care_nav_handled = True
                directory_message = _intake_q
                extra_reason_codes.append("R109_CARE_JOURNEY_INTAKE")
                skip_generator = True
                clarification_message = None
            elif is_care_navigation_query(message) or is_directory_source_question(message):
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
                        directory_links = tuple(getattr(care_nav, "links", ()) or ())
                        directory_intro_state = getattr(care_nav, "intro_state", None)
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
                # R-109 step 1b-2: a doctor/lab request is the start of a CARE JOURNEY (follow-up, interview, stabilising care)
                directory_message, _journey_started = self._with_care_journey(
                    directory_message, (_memory_req.tier_text if _memory_req is not None and _memory_req.tier_text else message), lang, authenticated_user_id,
                    said=original_user_message,
                )
                if _journey_started:
                    extra_reason_codes.append("R109_CARE_JOURNEY")
                if _memory_notes and directory_message:
                    directory_message = chr(10).join(_memory_notes) + chr(10) * 2 + directory_message  # where the place came from, the other problem
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

            from backend.app.services.intelligence.plan_subject import (
                mentions_other_person,
                plan_subject_question,
            )

            if is_nutrition_operational_intent(intent_meta.intent_id) and mentions_other_person(message, lang):
                # Stage 06 / B1: never save a plan on the wrong person; ask who it is for.
                nutrition_message = plan_subject_question(lang)
                extra_reason_codes.append("PLAN_SUBJECT_CLARIFICATION")
                skip_generator = True
                clarification_message = None
            elif is_nutrition_operational_intent(intent_meta.intent_id):
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
                        else "الان نتونستم یه برنامه‌ی تغذیه‌ی مطمئن بسازم؛ یه کم بیشتر درباره‌ات بگو تا دوباره امتحان کنم."
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

            from backend.app.services.intelligence.plan_subject import (
                mentions_other_person as _mentions_other_person_ex,
                plan_subject_question as _plan_subject_question_ex,
            )

            if is_activity_operational_intent(intent_meta.intent_id) and _mentions_other_person_ex(message, lang):
                exercise_message = _plan_subject_question_ex(lang)
                extra_reason_codes.append("PLAN_SUBJECT_CLARIFICATION")
                skip_generator = True
                clarification_message = None
            elif is_activity_operational_intent(intent_meta.intent_id):
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
                        else "الان نتونستم یه برنامه‌ی ورزشی مطمئن بسازم؛ یه کم بیشتر درباره‌ات بگو تا دوباره امتحان کنم."
                    )
                    extra_reason_codes.append("EXERCISE_PRIMARY_PATH_FAIL_CLOSED")
                skip_generator = True
                clarification_message = None

        # R-088 / R-091 (A1 v2): the next step of the pill care interview (name -> reason -> reminder at the end).
        # Needs the consent-gated previous reply; fail-open (None -> normal flow).
        reminder_message: Optional[str] = None
        if (
            not terminal_safety
            and not discovery_reply_active
            and not care_nav_handled
            # Codex P2 (PR 185): «just remind me» / «فقط یادم بنداز» is classified as a reminder WITHOUT a time, so the generic
            # clarification («what time?») has already set skip_generator; the interview owns that reply, so it runs when ONLY
            # the clarification is pending (it returns None for every message that is not an answer of an open interview).
            and (not skip_generator or clarification_message is not None)
            and self._db is not None
        ):
            try:
                from backend.app.services.medication_care import chat_reminder as _med_chat

                if _med_chat.enabled():
                    _med_reply = _med_chat.continue_interview(self._db, user_id=authenticated_user_id, message=message, language=lang, timezone_name=self._reminder_timezone(ctx, authenticated_user_id))
                    if _med_reply:
                        reminder_message = _med_reply
                        skip_generator = True
                        clarification_message = None
                        extra_reason_codes.append("R088_MEDICATION_INTERVIEW_STEP")
                    elif _med_reply == _med_chat.MODEL_OWNED_REPLY:
                        # R-112: the interview completed on this message; the chat model answers the reason. A pending generic
                        # «what time?» clarification is stale now (the schedule was already given) - clear it and let the model reply
                        clarification_message = None
                        skip_generator = False
                        extra_reason_codes.append("R112_REASON_ANSWER_BY_MODEL")
            except Exception:  # noqa: BLE001
                pass

        # R-103 step A: «change the time of my reminder» REALLY changes it through the existing owners (UserEvent / UserMedication),
        # or asks ONE question; never a model claim of a change that did not happen. Fail-open (None -> normal flow).
        if (
            reminder_message is None
            and not terminal_safety
            and not discovery_reply_active
            and self._db is not None
        ):
            try:
                from datetime import datetime, timezone
                from backend.app.services.intelligence import reminder_reschedule as _resched
                from backend.app.services.medication_care import chat_reminder as _mc_turns

                _turns_ctx: list = []
                if _mc_turns.history_available(self._db, authenticated_user_id):
                    _turns_ctx = _mc_turns._recent_turns(self._db, authenticated_user_id, datetime.now(timezone.utc))
                # an OPEN question of this flow owns the next message (it may be a reminder title that another path would take)
                _resched_open = _resched.has_open_question(_turns_ctx)
                if (not care_nav_handled and (not skip_generator or clarification_message is not None)) or _resched_open:
                    _resched_msg = message
                    if _turns_ctx:
                        _resched_msg = _resched.pending_request(_turns_ctx, message, lang) or message
                    _resched_ctx = _resched.context_of(_turns_ctx, _resched_msg != message)
                    _resched_reply = _resched.abort_reply(_turns_ctx, message, lang) or _resched.handle(
                        self._db, user_id=authenticated_user_id, message=_resched_msg, language=lang, context=_resched_ctx
                    )
                    if _resched_reply:
                        if care_nav_handled:  # the doctor finder took the answer («Dentist»); the open question wins
                            care_nav_handled = False
                            directory_message = None
                        reminder_message = _resched_reply
                        skip_generator = True
                        clarification_message = None
                        extra_reason_codes.append("R103_REMINDER_RESCHEDULE")
            except Exception:  # noqa: BLE001
                pass

        # I1 dispatch: I3-READY REMINDER/event → existing UserEvent (not I8).
        # No direct Notification write; I10 scheduler consumes reminder fields.
        if (
            not terminal_safety
            and not discovery_reply_active
            and not care_nav_handled
            and reminder_message is None
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
                    timezone_name=self._reminder_timezone(ctx, authenticated_user_id),
                    language=lang,
                )
                extra_reason_codes.append("I3_REMINDER_USEREVENT_DISPATCH")
                if dispatched.get("duplicate"):
                    extra_reason_codes.append("I3_REMINDER_USEREVENT_DEDUPED")
                elif dispatched.get("created"):
                    extra_reason_codes.append("I3_REMINDER_USEREVENT_CREATED")
                from backend.app.services.intelligence.reminder_event_dispatch import (
                    confirmation_message,
                )

                reminder_message = confirmation_message(dispatched, lang)
            except Exception:
                extra_reason_codes.append("I3_REMINDER_USEREVENT_FAIL_CLOSED")
                reminder_message = (
                    "I couldn’t save that right now — please tell me once more in a moment and I’ll add it."
                    if lang == "en"
                    else "الان نشد ثبتش کنم؛ یه کم دیگه دوباره بگو تا برات ثبتش کنم."
                )
            skip_generator = True
            clarification_message = None

        # R-047: "who are you / what can you do / can you send notifications" -> Sedi's locked identity + real abilities.
        about_message: Optional[str] = None
        if (
            not terminal_safety
            and not discovery_reply_active
            and not care_nav_handled
            and (
                not skip_generator
                # a capability question («می‌تونی نوتیف بفرستی؟») also reads as a reminder with no time: the answer about
                # Sedi's abilities wins over the «which day/time?» clarification (never over a created reminder)
                or (
                    clarification_message is not None
                    and reminder_message is None
                    and intent_meta is not None
                    and intent_meta.intent_id.value in ("reminder", "general")
                )
            )
        ):
            try:
                from backend.app.services.intelligence.about_sedi import (
                    about_sedi_reply,
                    is_about_sedi_question,
                )

                if is_about_sedi_question(message):
                    about_message = about_sedi_reply(message, lang)
                    extra_reason_codes.append("R047_ABOUT_SEDI_IDENTITY")
                    skip_generator = True
                    clarification_message = None
            except Exception:
                about_message = None

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
            _plan_intake_ctx = plan_domain_ctx is not None or intent_meta.intent_id in (
                IntentId.NUTRITION,
                IntentId.ACTIVITY,
            )
            invited_rd_mode = bool(continue_invited_discovery or phrase_invitation or _plan_intake_ctx)

            directive = select_next_best_question(
                snapshot=snapshot,
                intent=intent_meta,
                readiness=readiness_meta,
                language=lang,
                message=message,
                force_invitation=continue_invited_discovery,
                exclude_keys=invited_exclude_keys,
                plan_domain=plan_domain_ctx,
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
            # R-011: I7 derived wellbeing (short/medium-term) lets Sedi be attentive; consent-gated, never a fact.
            try:
                from backend.app.services.i6.consent_service import PERM_READ, has_permission
                from backend.app.services.i7.derived_signals import recent_wellbeing_trend

                if self._db is not None and has_permission(self._db, authenticated_user_id, PERM_READ):
                    _wb = recent_wellbeing_trend(self._db, authenticated_user_id)
                    _hint = PersonaPolicyV1.wellbeing_hint(_wb.get("trend"), _wb.get("concerns"), lang)
                    if _hint:
                        relationship_guidance = f"{relationship_guidance}\n{_hint}"
            except Exception:
                pass
            # R-018: continuity of care — a recent significant life event and Sedi's own earlier suggestions (read-only).
            try:
                from backend.app.services.intelligence.care_continuity import build_continuity_hint

                if self._db is not None:
                    _care = build_continuity_hint(self._db, authenticated_user_id, lang)
                    if _care:
                        relationship_guidance = f"{relationship_guidance}\n{_care}"
            except Exception:
                pass

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
                topic_carried=_topic_carried(self._db, authenticated_user_id, message, lang),
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
            from backend.app.services.intelligence.plain_text import to_plain_chat_text

            out_message = to_plain_chat_text(validated.message)
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
                or about_message
                or clarification_message
                or ""
            )
            # Stage 06 / B1: after a grounded I8 plan reply, ask the one pending body-function question.
            if (
                (nutrition_message or exercise_message)
                and not directory_message
                and visible_nbq_eligible
                and discovery_localized_question
                and str(discovery_target_key or "").startswith(("function.", "intake."))
                and ("I8_NUTRITION_ACTION" in extra_reason_codes or "I8_EXERCISE_ACTION" in extra_reason_codes)
            ):
                out_message = f"{out_message}\n\n{discovery_localized_question}"
                _mark_relationship_discovery_asked(
                    self._db,
                    user_id=authenticated_user_id,
                    target_key=str(discovery_target_key),
                )
                extra_reason_codes.append("FUNCTION_QUESTION_APPENDED")
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
                or about_message is not None
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
                        _followup_only_context(generation_notification_context)
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
            # A generic profile question (preferences.*, work.occupation) is not appended to a governed knowledge
            # answer: the user is mid-task. Topical/contextual questions (sleep, food, activity, work schedule) stay.
            llm_unavailable = bool((raw.get("metadata") or {}).get("llm_unavailable"))
            if (
                visible_nbq_eligible
                and not llm_unavailable  # never stack a question under "I can't answer right now"
                and not (
                    allow_governed_knowledge
                    and str(discovery_target_key or "").startswith(("preferences.", "work.occupation"))
                )
                and discovery_localized_question
                and discovery_target_key
            ):
                from backend.app.services.intelligence.psychological_interaction import (
                    append_discovery_questions,
                )

                q_list = [discovery_localized_question]
                if discovery_companion_question:
                    q_list.append(discovery_companion_question)
                _before_nbq = gen_message
                gen_message = append_discovery_questions(gen_message, q_list)
                nbq_was_appended = gen_message != _before_nbq  # R-066: skipped when the model already asked

            validated = self._safety_validator(text=gen_message, language=lang)
            from backend.app.services.intelligence.plain_text import to_plain_chat_text

            out_message = to_plain_chat_text(validated.message)
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

        # Javad 2026-10-29: «صدی در I7 باید توانایی ثبت تمام چت‌ها را داشته باشد». A turn answered WITHOUT the generator
        # (clarification, directory / plan reply, reminder confirmation, terminal safety) never reached the brain, so it
        # was never stored: missing from My History, the same-day recap and the reminder continuation. Record it here
        # (consent-gated by the governed raw write, idempotent, fail-open - chat must never break).
        if skip_generator and self._db is not None and out_message and out_message.strip():
            try:
                from backend.app.core.conversation.memory import ConversationMemory

                saved_turn = ConversationMemory(self._db).save_conversation(
                    authenticated_user_id,
                    original_user_message,
                    out_message.strip(),
                    out_language,
                    actor_user_id=authenticated_user_id,
                )
                if saved_turn is not None and care_nav_handled and directory_links:
                    from backend.app.services.i7.governed_raw import attach_reply_links

                    attach_reply_links(self._db, user_id=authenticated_user_id, sedi_response=out_message.strip(), links=list(directory_links))
                if saved_turn is not None and care_nav_handled and directory_intro_state:
                    from backend.app.services.i7.governed_raw import attach_provider_intro

                    attach_provider_intro(self._db, user_id=authenticated_user_id, sedi_response=out_message.strip(), state=directory_intro_state)
            except Exception:
                try:
                    self._db.rollback()
                except Exception:
                    pass
                extra_reason_codes.append("I7_RAW_RECORD_FAILED")

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
            links=directory_links if care_nav_handled and directory_message else (),
            interaction_need=interaction_need_value,
        )
