"""Section 15-I1 — Connected Intelligence Orchestrator foundation.

Always invoked by POST /interact/chat for the normal generation path.
Flag OFF = compatibility mode; flag ON = structured mode.
Both modes still run deterministic I1 stages and legacy ConversationBrain generation.
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
    ConversationOrigin,
    LanguageCode,
    NotificationOrigin,
    OrchestrationError,
    OrchestrationResult,
    ReasonCode,
    RolloutMode,
    StageName,
    build_empty_context,
)
from backend.app.services.intelligence.feature_flags import (
    intelligence_orchestrator_v1_enabled,
)

LegacyGenerator = Callable[..., Dict[str, Any]]


class LegacyGeneratorProtocol(Protocol):
    def __call__(
        self,
        user_id: int,
        user_message: str,
        user_name: Optional[str] = None,
        *,
        notification_context: Optional[dict] = None,
    ) -> Dict[str, Any]:
        ...


def _default_legacy_generator(db: Session, language: str) -> LegacyGenerator:
    def _generate(
        user_id: int,
        user_message: str,
        user_name: Optional[str] = None,
        *,
        notification_context: Optional[dict] = None,
    ) -> Dict[str, Any]:
        brain = ConversationBrain(db, language=language)
        return brain.process_message(
            user_id,
            user_message,
            user_name,
            notification_context=notification_context,
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


_BANNED_NOTIF_KEYS = frozenset(
    {"body", "raw_body", "context_json", "health", "dose", "dosage", "notification_body"}
)


class IntelligenceOrchestrator:
    """Stateless gateway: each process() builds a fresh request-scoped context."""

    def __init__(
        self,
        *,
        db: Optional[Session] = None,
        legacy_generator: Optional[LegacyGenerator] = None,
        structured_mode: Optional[bool] = None,
    ) -> None:
        self._db = db
        self._legacy_generator = legacy_generator
        self._structured_mode_override = structured_mode

    def _rollout_mode(self) -> RolloutMode:
        if self._structured_mode_override is not None:
            return "structured" if self._structured_mode_override else "compatibility"
        return (
            "structured"
            if intelligence_orchestrator_v1_enabled()
            else "compatibility"
        )

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
    ) -> OrchestrationResult:
        """
        Run deterministic I1 stages then legacy generation exactly once.

        ``message`` and ``notification_context`` are generation-only inputs and
        never enter stage traces. Authenticated identity must come from the
        JWT/server caller — never from a caller-controlled user_id field.
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
            # Ownership already verified by router before orchestration entry.
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

        # 5) prepare_compatibility_generation
        # I1 always selects the legacy brain, including structured mode.
        t0 = time.perf_counter()
        if rollout_mode == "structured":
            extra_reason_codes.append(ReasonCode.STRUCTURED_MODE_ACTIVE.value)
        ctx.append_stage(
            StageName.PREPARE_COMPATIBILITY_GENERATION,
            "ok",
            ReasonCode.COMPATIBILITY_GENERATOR_SELECTED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        generator = self._legacy_generator
        if generator is None:
            if self._db is None:
                raise OrchestrationError("missing_db_for_legacy_generator")
            generator = _default_legacy_generator(self._db, lang)

        # 6) generate_with_legacy_brain — exactly once; no out-of-band retry
        t0 = time.perf_counter()
        try:
            raw = generator(
                authenticated_user_id,
                message,
                None,
                notification_context=generation_notification_context,
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

        # 7) validate_generation_result
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
        out_message = raw.get("message")
        if not isinstance(out_message, str) or not out_message.strip():
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
        out_language = _normalize_language_code(
            raw.get("language") if isinstance(raw.get("language"), str) else lang
        )
        detected_name = raw.get("detected_name")
        if detected_name is not None and not isinstance(detected_name, str):
            detected_name = None
        ctx.append_stage(
            StageName.VALIDATE_GENERATION_RESULT,
            "ok",
            ReasonCode.RESPONSE_VALIDATED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        # 8) complete
        t0 = time.perf_counter()
        ctx.append_stage(
            StageName.COMPLETE,
            "ok",
            ReasonCode.ORCHESTRATION_COMPLETED,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        stage_reasons = ctx.reason_codes()
        # Insert timezone (+ optional structured) codes after LANGUAGE_NORMALIZED.
        reason_codes: list[str] = []
        extras_to_place = list(extra_reason_codes)
        for code in stage_reasons:
            reason_codes.append(code)
            if code == ReasonCode.LANGUAGE_NORMALIZED.value and extras_to_place:
                # Prefer placing timezone codes immediately after language normalization.
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
        )
