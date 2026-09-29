"""I10-B11 daily wellness digest — V1 Daily Smart Touchpoint (localized, bounded)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    sanitize_notification_context,
)
from backend.app.services.gate4.policy_prefs_bridge import DEFAULT_TIMEZONE, resolve_validated_user_timezone
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.self_producer_adapter import resolve_or_ensure_self_health_subject_id
from backend.app.services.i9.i8_projection_service import (
    get_i8_governed_context_projection,
    projection_context_refs,
)

logger = logging.getLogger(__name__)

DIGEST_PRODUCER_OWNER = "I10_DAILY_WELLNESS_DIGEST"
STALE_DATA_HOURS = 48
PARTIAL_COVERAGE_THRESHOLD = 0.5

SUPPORTED_LANGS = ("en", "fa", "ar")


class DailyWellnessDataStatus(str, Enum):
    SUFFICIENT_OBSERVED_DATA = "SUFFICIENT_OBSERVED_DATA"
    PARTIAL_DATA = "PARTIAL_DATA"
    STALE_DATA = "STALE_DATA"
    NO_DATA = "NO_DATA"


class DailySmartContentFamily(str, Enum):
    SAFETY = "safety"
    I9_OBSERVATION = "i9_observation"
    I8_ACTION = "i8_action"
    I6_I7_CONTEXT = "i6_i7_context"
    GENERAL_CHECKIN = "general_checkin"


@dataclass(frozen=True)
class DailyWellnessDigestFacts:
    user_id: int
    health_subject_id: Optional[int]
    observation_period_start: datetime
    observation_period_end: datetime
    data_status: DailyWellnessDataStatus
    coverage_summary: str
    recency_summary: str
    alert_summary: str
    limitations: tuple[str, ...] = ()
    provenance_refs: tuple[dict[str, Any], ...] = ()
    i7_continuity_available: bool = False
    baseline_comparison: Optional[str] = None
    content_family: DailySmartContentFamily = DailySmartContentFamily.GENERAL_CHECKIN
    local_period_date: Optional[date] = None


_DIGEST_TITLES = {
    "en": ("Daily wellness check-in", "Your daily Sedi check-in", "Today with Sedi"),
    "fa": ("چک‌این روزانه سلامتی", "پیگیری روزانه صدی", "امروز با صدی"),
    "ar": ("متابعة الصحة اليومية", "تفقدك اليومي مع صدی", "اليوم مع صدی"),
}

_NO_DATA_BODIES = {
    "en": (
        "No new health observations are available yet today. Open Sedi when you are ready to check in.",
        "We do not have enough observed data for a full daily summary yet. Sedi is here when you want to talk.",
        "Today's health picture is still incomplete. A gentle check-in is ready whenever you are.",
    ),
    "fa": (
        "هنوز دادهٔ مشاهده‌شدهٔ جدیدی برای امروز در دسترس نیست. هر وقت آماده بودی صدی را باز کن.",
        "هنوز دادهٔ کافی برای خلاصهٔ کامل روزانه نداریم. صدی اینجاست اگر بخواهی حرف بزنی.",
        "تصویر امروز هنوز کامل نیست. یک چک‌این آرام هر وقت بخواهی آماده است.",
    ),
    "ar": (
        "لا تتوفر بعد ملاحظات صحية جديدة لليوم. افتح صدی عندما تكون مستعدًا.",
        "ليس لدينا بيانات كافية لملخص يومي كامل بعد. صدی هنا إن أردت التحدث.",
        "صورة اليوم لا تزال غير مكتملة. تفقد لطيف جاهز متى شئت.",
    ),
}

_SAFETY_BODIES = {
    "en": (
        "There is a safety-related update waiting for you. Open Sedi to review it calmly.",
        "Sedi has a safety check-in for you today. Tap to continue in chat.",
    ),
    "fa": (
        "یک به‌روزرسانی مرتبط با ایمنی منتظر توست. برای مرور آرام، صدی را باز کن.",
        "صدی امروز یک چک‌این ایمنی برایت دارد. برای ادامه در گفتگو ضربه بزن.",
    ),
    "ar": (
        "هناك تحديث متعلق بالسلامة بانتظارك. افتح صدی لمراجعته بهدوء.",
        "لدى صدی تفقد سلامة لك اليوم. اضغط للمتابعة في المحادثة.",
    ),
}

_I9_SUFFICIENT_BODIES = {
    "en": (
        "Observed device data was received for today's window. Open Sedi for a short factual check-in.",
        "Your recent device observations are available. Continue in Sedi for a bounded daily review.",
    ),
    "fa": (
        "دادهٔ مشاهده‌شدهٔ دستگاه برای بازهٔ امروز دریافت شد. برای چک‌این کوتاه صدی را باز کن.",
        "مشاهدات اخیر دستگاه در دسترس است. برای مرور محدود روزانه در صدی ادامه بده.",
    ),
    "ar": (
        "تم استلام بيانات الجهاز المرصودة لنافذة اليوم. افتح صدی لتفقد واقعي قصير.",
        "ملاحظات جهازك الأخيرة متاحة. تابع في صدی لمراجعة يومية محدودة.",
    ),
}

_I9_PARTIAL_BODIES = {
    "en": (
        "Today's available data is incomplete, so a full comparison is not available. Open Sedi to continue.",
        "Observed coverage is partial for today. Sedi can help with a gentle check-in.",
    ),
    "fa": (
        "دادهٔ امروز ناقص است؛ مقایسهٔ کامل ممکن نیست. برای ادامه صدی را باز کن.",
        "پوشش مشاهده‌شده برای امروز جزئی است. صدی می‌تواند یک چک‌این آرام کمک کند.",
    ),
    "ar": (
        "بيانات اليوم غير مكتملة، لذا المقارنة الكاملة غير متاحة. افتح صدی للمتابعة.",
        "التغطية المرصودة جزئية لليوم. يمكن لصدی المساعدة بتفقد لطيف.",
    ),
}

_I9_STALE_BODIES = {
    "en": (
        "Observed data exists but is older than expected for today. Open Sedi for a short check-in.",
        "The latest rollup is older than usual. Continue in Sedi when ready.",
    ),
    "fa": (
        "دادهٔ مشاهده‌شده هست اما از حد انتظار امروز قدیمی‌تر است. برای چک‌این کوتاه صدی را باز کن.",
        "آخرین رول‌آپ قدیمی‌تر از معمول است. هر وقت آماده بودی در صدی ادامه بده.",
    ),
    "ar": (
        "توجد بيانات مرصودة لكنها أقدم مما هو متوقع لليوم. افتح صدی لتفقد قصير.",
        "أحدث ملخص أقدم من المعتاد. تابع في صدی عندما تكون مستعدًا.",
    ),
}

_I8_BODIES = {
    "en": (
        "You have an active plan item for today. Open Sedi to continue with it.",
        "A current action from your plan is waiting. Continue in Sedi when ready.",
    ),
    "fa": (
        "یک مورد فعال از برنامه‌ات برای امروز داری. برای ادامه صدی را باز کن.",
        "یک اقدام فعلی از برنامه‌ات منتظر است. هر وقت آماده بودی در صدی ادامه بده.",
    ),
    "ar": (
        "لديك عنصر خطة نشط لليوم. افتح صدی للمتابعة.",
        "إجراء حالي من خطتك بانتظارك. تابع في صدی عندما تكون مستعدًا.",
    ),
}

_I6_I7_BODIES = {
    "en": (
        "A short lifestyle or goal note is ready for a gentle daily check-in. Open Sedi to continue.",
        "Your permitted daily context suggests a light follow-up. Continue in Sedi.",
    ),
    "fa": (
        "یک یادداشت کوتاه سبک زندگی یا هدف برای چک‌این روزانه آماده است. برای ادامه صدی را باز کن.",
        "بافت مجاز روزانه پیشنهاد یک پیگیری سبک می‌دهد. در صدی ادامه بده.",
    ),
    "ar": (
        "ملاحظة قصيرة عن نمط الحياة أو الهدف جاهزة لتفقد يومي لطيف. افتح صدی للمتابعة.",
        "سياقك اليومي المسموح يقترح متابعة خفيفة. تابع في صدی.",
    ),
}

_GENERAL_BODIES = {
    "en": (
        "Good morning — a gentle daily check-in from Sedi is ready when you are.",
        "Sedi is here for a short daily hello. Open chat whenever you like.",
        "One calm touchpoint for today. Continue with Sedi when ready.",
    ),
    "fa": (
        "صبح بخیر — یک چک‌این روزانهٔ آرام از صدی هر وقت بخواهی آماده است.",
        "صدی برای یک سلام کوتاه روزانه اینجاست. هر وقت خواستی گفتگو را باز کن.",
        "یک لمس آرام برای امروز. هر وقت آماده بودی با صدی ادامه بده.",
    ),
    "ar": (
        "صباح الخير — تفقد يومي لطيف من صدی جاهز متى شئت.",
        "صدی هنا لسلام يومي قصير. افتح المحادثة متى أحببت.",
        "لمسة هادئة واحدة لليوم. تابع مع صدی عندما تكون مستعدًا.",
    ),
}

# English fact strings retained for assemble_* compatibility / tests (payload uses localized render).
_EN_ALERT_NONE = "No qualifying alert was recorded during the period."
_EN_ALERT_COUNT = "{count} qualifying alert(s) were recorded during the period."
_EN_BASELINE_ABOVE = (
    "Recent observations are above your personal observed baseline (not a clinical normal range)."
)
_EN_BASELINE_BELOW = (
    "Recent observations are below your personal observed baseline (not a clinical normal range)."
)
_EN_BASELINE_SIMILAR = "Recent observations are similar to your personal observed baseline pattern."
_EN_NO_DATA_COVERAGE = "No observed health data was available for today's digest period."
_EN_NO_DATA_RECENCY = "No recent device-reported data timestamp is available."
_EN_INCOMPLETE = "Today's available data is incomplete, so a full comparison is not available."


def _norm_lang(language: str | None) -> str:
    lang = (language or "en").strip().lower().split("-")[0]
    return lang if lang in SUPPORTED_LANGS else "en"


def _stable_variant_index(seed: str, n: int) -> int:
    """Legacy hash%N (kept for non-rotation callers). Prefer ``_rotation_variant_index``."""
    if n <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % n


def _rotation_variant_index(
    *,
    user_id: int,
    local_day: date,
    content_family: str,
    n: int,
) -> int:
    """Stateless deterministic rotation: adjacent local days differ when n > 1."""
    if n <= 1:
        return 0
    offset = int(
        hashlib.sha256(f"{user_id}:{content_family}".encode("utf-8")).hexdigest()[:8],
        16,
    ) % n
    return (offset + local_day.toordinal()) % n


def _pick_variant(
    variants: dict[str, tuple[str, ...]],
    language: str,
    *,
    user_id: int,
    local_day: date,
    content_family: str,
) -> str:
    lang = _norm_lang(language)
    pool = variants.get(lang) or variants["en"]
    idx = _rotation_variant_index(
        user_id=user_id,
        local_day=local_day,
        content_family=content_family,
        n=len(pool),
    )
    return pool[idx]


def build_daily_digest_occurrence_key(*, user_id: int, period_date: date) -> str:
    return f"i10:self:daily_digest:{user_id}:{period_date.isoformat()}"


def _user_tz(db: Session, user_id: int):
    try:
        name = resolve_validated_user_timezone(db, user_id) or DEFAULT_TIMEZONE
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _period_bounds_local(db: Session, user_id: int, when: datetime) -> tuple[datetime, datetime, date]:
    """User-local calendar day bounds expressed as UTC-aware datetimes."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    zone = _user_tz(db, user_id)
    local = when.astimezone(zone)
    local_day = local.date()
    start_local = datetime(local_day.year, local_day.month, local_day.day, tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), local_day


def _period_bounds(when: datetime) -> tuple[datetime, datetime]:
    """UTC-day bounds (legacy helper kept for callers/tests that pass UTC-only)."""
    day = when.date() if when.tzinfo is None else when.astimezone(timezone.utc).date()
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _load_i7_daily_flag(db: Session, user_id: int) -> bool:
    row = (
        db.query(models.UserPeriodSummary)
        .filter(
            models.UserPeriodSummary.user_id == user_id,
            models.UserPeriodSummary.summary_type == "DAILY",
            models.UserPeriodSummary.status == "active",
        )
        .order_by(models.UserPeriodSummary.period_start.desc())
        .limit(1)
        .first()
    )
    return row is not None and row.finalized_at is not None


def _qualifying_alert_summary(db: Session, user_id: int, period_start: datetime) -> str:
    count = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.type == "health_alert",
            models.Notification.created_at >= period_start.replace(tzinfo=None),
        )
        .count()
    )
    if count == 0:
        return _EN_ALERT_NONE
    return _EN_ALERT_COUNT.format(count=count)


def _baseline_comparison_phrase(projection) -> Optional[str]:
    daily = projection.daily_rollup
    baseline = projection.personal_observed_baseline
    if daily is None or baseline is None:
        return None
    if daily.avg_value is None or baseline.baseline_value is None:
        return None
    if daily.avg_value > baseline.baseline_value:
        return _EN_BASELINE_ABOVE
    if daily.avg_value < baseline.baseline_value:
        return _EN_BASELINE_BELOW
    return _EN_BASELINE_SIMILAR


def _has_eligible_safety_signal(db: Session, user_id: int, period_start: datetime) -> bool:
    """Upstream safety-qualified notifications already persisted via I10 (no reinterpretation)."""
    families = (
        I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        I10SemanticFamily.SAFETY_ESCALATION.value,
    )
    start_naive = period_start.replace(tzinfo=None) if period_start.tzinfo else period_start
    row = (
        db.query(models.Notification.id)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.semantic_family.in_(families),
            models.Notification.created_at >= start_naive,
        )
        .first()
    )
    return row is not None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _i8_action_eligible_for_digest(
    action: models.I8OperationalPlanAction,
    *,
    now: datetime,
) -> bool:
    """Bounded A4 read-only window/safety gate. Does not mutate I8."""
    if action.status != "ACTIVE":
        return False
    if action.safety_state != "SAFE":
        return False
    if bool(action.clarification_required):
        return False
    if action.valid_from is None or action.valid_until is None or action.expires_at is None:
        return False
    now_utc = _as_utc(now)
    if now_utc < _as_utc(action.valid_from):
        return False
    if now_utc > _as_utc(action.valid_until):
        return False
    if now_utc >= _as_utc(action.expires_at):
        return False
    return True


def _has_active_i8_action(
    db: Session,
    user_id: int,
    *,
    local_day: date,
    now: datetime,
) -> bool:
    """READ-ONLY: currently-valid SAFE ACTIVE I8 action for the user-local day."""
    from backend.app.services.i8.repository import I8OperationalRepository

    plan = I8OperationalRepository().get_active_plan(
        db, user_id=user_id, user_local_date=local_day
    )
    if plan is None or plan.user_id != user_id or plan.status != "ACTIVE":
        return False
    if plan.user_local_date != local_day:
        return False
    actions = (
        db.query(models.I8OperationalPlanAction)
        .filter(
            models.I8OperationalPlanAction.plan_id == plan.id,
            models.I8OperationalPlanAction.user_id == user_id,
            models.I8OperationalPlanAction.status == "ACTIVE",
        )
        .all()
    )
    return any(_i8_action_eligible_for_digest(a, now=now) for a in actions)


def _has_permitted_i6_i7_context(db: Session, user_id: int) -> bool:
    """I6 READ + privacy-safe bounded I7 topic. Finalized empty summary is not enough."""
    from backend.app.services.i6.consent_service import PERM_READ, has_permission

    if not has_permission(db, user_id, PERM_READ):
        return False
    try:
        from backend.app.services.i7.privacy_safe_recent_topic import (
            get_privacy_safe_recent_topic_label,
        )

        return get_privacy_safe_recent_topic_label(db, user_id) is not None
    except Exception:
        return False


def select_daily_smart_content_family(
    db: Session,
    *,
    user_id: int,
    data_status: DailyWellnessDataStatus,
    period_start: datetime,
    local_day: date,
    now: datetime,
) -> DailySmartContentFamily:
    """ONE primary topic in fixed priority order; never invents health facts."""
    if _has_eligible_safety_signal(db, user_id, period_start):
        return DailySmartContentFamily.SAFETY
    if data_status in (
        DailyWellnessDataStatus.SUFFICIENT_OBSERVED_DATA,
        DailyWellnessDataStatus.PARTIAL_DATA,
        DailyWellnessDataStatus.STALE_DATA,
    ):
        return DailySmartContentFamily.I9_OBSERVATION
    if _has_active_i8_action(db, user_id, local_day=local_day, now=now):
        return DailySmartContentFamily.I8_ACTION
    if _has_permitted_i6_i7_context(db, user_id):
        return DailySmartContentFamily.I6_I7_CONTEXT
    return DailySmartContentFamily.GENERAL_CHECKIN


def assemble_daily_wellness_digest_facts(
    db: Session,
    *,
    user_id: int,
    when: Optional[datetime] = None,
) -> DailyWellnessDigestFacts:
    """Bounded I9 rollup/baseline projection only — no raw PhysiologicalMeasurement rows."""
    now = when or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    period_start, period_end, local_day = _period_bounds_local(db, user_id, now)

    projection = get_i8_governed_context_projection(db, account_user_id=user_id)
    refs = tuple(projection_context_refs(projection))
    daily = projection.daily_rollup

    limitations: list[str] = []
    data_status = DailyWellnessDataStatus.NO_DATA
    coverage_summary = _EN_NO_DATA_COVERAGE
    recency_summary = _EN_NO_DATA_RECENCY

    if projection.health_subject_id is None:
        limitations = ("SELF health subject linkage is unavailable.",)
    elif daily is None:
        limitations = ("No daily rollup is available for the observation period.",)
    else:
        age_hours = (now - daily.bucket_end.replace(tzinfo=timezone.utc)).total_seconds() / 3600.0
        if daily.sample_count <= 0:
            data_status = DailyWellnessDataStatus.NO_DATA
            coverage_summary = "No samples were recorded in the daily rollup for this period."
        elif age_hours > STALE_DATA_HOURS:
            data_status = DailyWellnessDataStatus.STALE_DATA
            coverage_summary = "Observed data exists but is older than expected for today."
            recency_summary = f"Latest rollup period ended more than {STALE_DATA_HOURS} hours ago."
        elif daily.coverage is not None and daily.coverage < PARTIAL_COVERAGE_THRESHOLD:
            data_status = DailyWellnessDataStatus.PARTIAL_DATA
            coverage_summary = "Coverage is partial according to the daily rollup metric."
            recency_summary = "Some observed data was received during the period."
        else:
            data_status = DailyWellnessDataStatus.SUFFICIENT_OBSERVED_DATA
            coverage_summary = "Observed data was received during the period."
            recency_summary = "Latest daily rollup covers the recent observation window."

    baseline_cmp = _baseline_comparison_phrase(projection) if projection.health_subject_id else None
    alert_summary = _qualifying_alert_summary(db, user_id, period_start)
    family = select_daily_smart_content_family(
        db,
        user_id=user_id,
        data_status=data_status,
        period_start=period_start,
        local_day=local_day,
        now=now,
    )

    return DailyWellnessDigestFacts(
        user_id=user_id,
        health_subject_id=projection.health_subject_id,
        observation_period_start=period_start,
        observation_period_end=period_end,
        data_status=data_status,
        coverage_summary=coverage_summary,
        recency_summary=recency_summary,
        alert_summary=alert_summary,
        limitations=tuple(limitations),
        provenance_refs=refs,
        i7_continuity_available=_load_i7_daily_flag(db, user_id),
        baseline_comparison=baseline_cmp,
        content_family=family,
        local_period_date=local_day,
    )


def render_digest_body(facts: DailyWellnessDigestFacts, language: str = "en") -> str:
    """
    Deterministic localized copy — no diagnosis, no invented health facts.

    When language is omitted/``en`` and family is I9, preserve factual English join used by
    legacy B11 tests; otherwise use bounded localized variant sets.
    """
    lang = _norm_lang(language)
    local_day = facts.local_period_date or facts.observation_period_start.date()
    family_key = facts.content_family.value

    def _body(pool: dict[str, tuple[str, ...]], *, key: str = family_key) -> str:
        return _pick_variant(
            pool,
            lang,
            user_id=facts.user_id,
            local_day=local_day,
            content_family=key,
        )

    if facts.content_family == DailySmartContentFamily.SAFETY:
        return _body(_SAFETY_BODIES)
    if facts.content_family == DailySmartContentFamily.I8_ACTION:
        return _body(_I8_BODIES)
    if facts.content_family == DailySmartContentFamily.I6_I7_CONTEXT:
        return _body(_I6_I7_BODIES)
    if facts.content_family == DailySmartContentFamily.GENERAL_CHECKIN:
        return _body(_GENERAL_BODIES)

    # I9_OBSERVATION
    if facts.data_status == DailyWellnessDataStatus.NO_DATA:
        return _body(_NO_DATA_BODIES, key=f"{family_key}:no_data")
    if facts.data_status == DailyWellnessDataStatus.STALE_DATA:
        return _body(_I9_STALE_BODIES, key=f"{family_key}:stale")
    if facts.data_status == DailyWellnessDataStatus.PARTIAL_DATA:
        return _body(_I9_PARTIAL_BODIES, key=f"{family_key}:partial")

    # Sufficient I9 — keep factual English join for EN compatibility; localize otherwise.
    if lang == "en":
        parts = [facts.coverage_summary, facts.recency_summary, facts.alert_summary]
        if facts.baseline_comparison:
            parts.append(facts.baseline_comparison)
        if facts.limitations:
            parts.append(facts.limitations[0])
        return " ".join(p for p in parts if p)
    return _body(_I9_SUFFICIENT_BODIES, key=f"{family_key}:sufficient")


def render_digest_title(facts: DailyWellnessDigestFacts, language: str = "en") -> str:
    local_day = facts.local_period_date or facts.observation_period_start.date()
    return _pick_variant(
        _DIGEST_TITLES,
        language,
        user_id=facts.user_id,
        local_day=local_day,
        content_family=f"{facts.content_family.value}:title",
    )


def build_daily_wellness_digest_payload(
    facts: DailyWellnessDigestFacts,
    *,
    occurrence_key: str,
    language: str = "en",
) -> NotificationPayload:
    lang = _norm_lang(language)
    title = render_digest_title(facts, lang)
    body = render_digest_body(facts, lang)
    local_day = facts.local_period_date or facts.observation_period_start.date()
    context = sanitize_notification_context(
        {
            "template_key": "daily_wellness_digest",
            "trigger_reason": "daily_wellness_digest",
            "schedule_label": local_day.isoformat(),
            "content_family": facts.content_family.value,
            # Never dump raw memory/health payloads into context_json
        }
    )
    return NotificationPayload(
        user_id=facts.user_id,
        type="health_alert",
        title=title,
        body=body,
        priority="normal",
        dedupe_key=occurrence_key,
        metadata={
            "language": lang,
            "alert_code": "daily_wellness_digest",
            "data_status": facts.data_status.value,
            "content_family": facts.content_family.value,
            "i7_continuity_available": facts.i7_continuity_available,
            "provenance_ref_count": len(facts.provenance_refs),
        },
        category=NotificationCategory.DAILY_STATUS.value,
        source_type=NotificationSourceType.DAILY_ROUTINE.value,
        source_id=local_day.isoformat(),
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key="daily_wellness_digest",
        context=context,
        health_subject_id=facts.health_subject_id,
        privacy_class=I10PrivacyClass.HEALTH_SENSITIVE.value,
    )


def enqueue_daily_wellness_digest(
    db: Session,
    *,
    facts: DailyWellnessDigestFacts,
    occurrence_key: str,
    language: str = "en",
) -> Optional[models.Notification]:
    if facts.health_subject_id is None:
        health_subject_id = resolve_or_ensure_self_health_subject_id(db, facts.user_id)
    else:
        health_subject_id = facts.health_subject_id

    local_day = facts.local_period_date or facts.observation_period_start.date()
    payload = build_daily_wellness_digest_payload(facts, occurrence_key=occurrence_key, language=language)
    candidate = I10NotificationCandidate(
        candidate_key=occurrence_key,
        health_subject_id=health_subject_id,
        recipient_user_id=facts.user_id,
        notification_scope=I10NotificationScope.SENSITIVE_HEALTH_DETAIL,
        source_owner=DIGEST_PRODUCER_OWNER,
        source_type="morning_notifications",
        source_id=local_day.isoformat(),
        semantic_family=I10SemanticFamily.DAILY_WELLNESS_DIGEST,
        privacy_hint=I10PrivacyClass.HEALTH_SENSITIVE,
        provenance_refs=tuple(
            json.dumps(ref, separators=(",", ":"), sort_keys=True) for ref in facts.provenance_refs
        ),
    )
    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
    if result.decision != I10DecisionValue.SEND or result.notification_id is None:
        logger.info(
            "[I10-B11] suppressed user=%s digest=%s reason=%s",
            facts.user_id,
            occurrence_key,
            result.reason_code,
        )
        return None
    return (
        db.query(models.Notification)
        .filter(models.Notification.id == result.notification_id)
        .one()
    )
