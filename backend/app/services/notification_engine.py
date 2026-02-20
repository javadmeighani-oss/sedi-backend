# app/services/notification_engine.py
"""
Notification Engine - Decision Engine & Builder

Responsibility:
- DecisionEngine: Determines when and what notifications to create
- NotificationBuilder: Builds notification objects with proper structure
- TimingRules: Manages notification timing and scheduling

All notification creation must go through: DecisionEngine → NotificationBuilder
Routers should NOT create notifications directly.
"""

from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime, timedelta
import logging

from backend.app.models import Notification, User, UserCondition, HealthData
from backend.app.services.medical import MedicalService
from backend.app.services.rag import RAGService
from backend.app.services.memory import MemoryContext, build_memory_context
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.notification_runtime.fallback_generator import generate_fallback_text
from backend.app.services.notification_runtime.ai_enhancer import enhance_with_ai
from backend.app.services.notification_runtime.language_resolver import resolve_effective_language
from backend.app.services.notification_runtime.renderer import render
from backend.app.services.notification_runtime.quiet_hours import is_within_quiet_hours
from backend.app.services.notification_runtime.templates_v1 import get_template_v1
from backend.app.services.notification_runtime.user_context_adapter import build_notification_context
from backend.app.services.notifications.adaptive_policy_v1 import (
    compute_adaptive_state,
    is_companion_send_allowed,
)
from backend.app.services.notifications.send_guard_v1 import can_send_v1

logger = logging.getLogger(__name__)

# Canonical companion dedupe_key prefix: "companion:" (channel-prefixed format)
COMPANION_DEDUPE_PREFIX = "companion:"
# Legacy: template_key-based format "companion_*" (backward compatible count)
COMPANION_DEDUPE_LEGACY_PREFIX = "companion_"


def _count_companion_notifications_today(db: Session, user_id: int, now: datetime) -> int:
    """Count notifications with companion dedupe_key for user_id on the same calendar day (UTC).
    Counts both canonical (companion:) and legacy (companion_*) formats for backward compatibility.
    """
    from sqlalchemy import or_
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.created_at >= start_of_day,
            Notification.dedupe_key.isnot(None),
            or_(
                Notification.dedupe_key.like(f"{COMPANION_DEDUPE_PREFIX}%"),
                Notification.dedupe_key.like(f"{COMPANION_DEDUPE_LEGACY_PREFIX}%"),
            ),
        )
        .count()
    )
    return count


def build_notification_from_template(
    db: Session,
    user_id: int,
    template_key: str,
    language: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    priority_override: Optional[str] = None,
    scheduled_for: Optional[datetime] = None,
) -> Optional[Notification]:
    """
    Create a Notification from a V1 template (code-controlled).
    Loads template via get_template_v1, renders with renderer, persists via NotificationBuilder.
    For companion channel, enforces adaptive policy (paused_until, companion_cap_override).
    template_key is logged only (no meta column on Notification).
    """
    template = get_template_v1(template_key)
    if not template:
        logger.warning("[NOTIF] template not found: %s", template_key)
        return None
    channel = template.get("channel", "engagement")
    now = datetime.utcnow()
    user_ctx = build_notification_context(db, user_id)
    lang = (user_ctx.get("language") or language or "en").strip().lower() if (user_ctx.get("language") or language) else "en"
    if lang not in ("en", "fa", "ar"):
        lang = "en"
    priority = (priority_override or template.get("priority") or "normal").strip().lower()
    if priority not in ("low", "normal", "high", "critical"):
        priority = "normal"
    guard = can_send_v1(db, user_id, channel, template_key, priority, now, lang)
    if not guard["allowed"]:
        logger.info("[NOTIF] send guard blocked user_id=%s channel=%s template_key=%s reasons=%s", user_id, channel, template_key, guard["reasons"])
        return None
    inputs = inputs or {}
    # Pass template so renderer uses template.texts via i18n_resolver; user_ctx for personalization
    rendered = render(
        channel=template.get("channel", "engagement"),
        language=lang,
        inputs=inputs,
        priority=priority,
        template=template,
        user_ctx=user_ctx,
    )
    title = (rendered.get("title") or "").strip() or "Sedi"
    body = (rendered.get("body") or "").strip()
    if not body:
        body = (template.get("texts") or {}).get("en") or {}
        if isinstance(body, dict):
            body = (body.get("message") or body.get("body") or "Sedi notification.").strip()
        else:
            body = "Sedi notification."
    actions_json = rendered.get("actions_json") or template.get("actions_json")
    notif_type = template.get("type", "connection_ping")
    date_str = (scheduled_for or datetime.utcnow()).strftime("%Y-%m-%d")
    # Canonical format: {channel}:{template_key}:{user_id}:{YYYY-MM-DD}
    dedupe_key = guard.get("dedupe_key") or f"{channel}:{template_key}:{user_id}:{date_str}"
    if scheduled_for is None:
        scheduled_for = NotificationBuilder(db).timing_rules.calculate_scheduled_time(priority)
    payload = NotificationPayload(
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        priority=priority,
        scheduled_for=scheduled_for,
        dedupe_key=dedupe_key,
        metadata={"language": lang},
    )
    builder = NotificationBuilder(db)
    notification = builder.persist(payload, check_dedupe=True, time_window_hours=24)
    if notification and actions_json:
        notification.actions_json = actions_json
        db.add(notification)
        db.commit()
        db.refresh(notification)
    if notification:
        logger.info("[NOTIF] created from template template_key=%s user_id=%s", template_key, user_id)
    return notification


def _build_render_inputs(
    memory_context: Optional[MemoryContext],
    metadata: Optional[Dict[str, Any]],
    user_name: Optional[str],
    language: str = "en",
) -> Dict[str, Any]:
    """Build inputs dict for notification_runtime.render (Stage 16.6.4)."""
    inputs: Dict[str, Any] = {"user_display_name": user_name}
    lang = language if language in ("en", "fa", "ar") else "en"
    _sleep_low = {"en": "Try to get more rest tonight", "fa": "امشب بیشتر استراحت کن", "ar": "احصل على مزيد من الراحة الليلة"}
    _sleep_ok = {"en": "You had good sleep", "fa": "خواب خوبی داشتی", "ar": "كان نومك جيداً"}
    _water = {"en": "Remember to drink water", "fa": "یادت نره آب بخوری", "ar": "لا تنس شرب الماء"}
    _activity = {"en": "You had good activity", "fa": "فعالیت خوبی داشتی", "ar": "كان نشاطك جيداً"}
    if memory_context:
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6:
                inputs["sleep_hint"] = _sleep_low.get(lang, _sleep_low["en"])
            elif memory_context.sleep_duration_hours >= 7:
                inputs["sleep_hint"] = _sleep_ok.get(lang, _sleep_ok["en"])
        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                inputs["hydration_hint"] = _water.get(lang, _water["en"])
        if memory_context.has_activity_data() and memory_context.steps_count and memory_context.steps_count > 5000:
            inputs["activity_hint"] = _activity.get(lang, _activity["en"])
    if metadata:
        inputs["last_vitals_summary"] = metadata.get("alert_reason")
        inputs["alert_reason"] = metadata.get("alert_reason")
    return inputs


# -------------------- Helper Functions (Release B2.1) --------------------

def _get_title_for_language(notification_type: str, language: str) -> str:
    """
    Get notification title in the specified language (Release B2.1).
    
    Args:
        notification_type: Type of notification (morning_brief, connection_ping, health_alert)
        language: Language code ("en" | "fa" | "ar")
    
    Returns:
        Title string in the specified language
    """
    titles = {
        "morning_brief": {
            "en": "Good Morning",
            "fa": "صبح بخیر",
            "ar": "صباح الخير"
        },
        "connection_ping": {
            "en": "Hello",
            "fa": "سلام",
            "ar": "مرحباً"
        },
        "health_alert": {
            "en": "Health Alert",
            "fa": "هشدار سلامت",
            "ar": "تنبيه صحي"
        },
        "device_disconnected": {
            "en": "Device Disconnected",
            "fa": "قطع اتصال دستگاه",
            "ar": "انقطع الاتصال بالجهاز"
        }
    }
    
    type_titles = titles.get(notification_type, {})
    return type_titles.get(language, type_titles.get("en", "Notification"))


def _channel_for_type(notification_type: str) -> Optional[str]:
    """Stage 16.6: Map notification type to push channel (morning | engagement | health_alert). Stage 19: device_disconnected => engagement. Behavior V1: companion_ping => engagement."""
    m = {
        "morning_brief": "morning",
        "connection_ping": "engagement",
        "health_alert": "health_alert",
        "device_disconnected": "engagement",
        "companion_ping": "engagement",
    }
    return m.get(notification_type)


def _default_body_for_type(
    notification_type: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Return a non-empty default body when generated body is empty (e.g. health_alert, device_disconnected).
    NotificationPayload requires body min_length=1; this avoids validation errors before apply_fallback runs.
    """
    language = "en"
    if metadata and metadata.get("language") in ("en", "fa", "ar"):
        language = metadata["language"]
    defaults = {
        "health_alert": {
            "en": "Health alert detected. Please review your readings.",
            "fa": "هشدار سلامت ثبت شد. لطفاً وضعیت خود را بررسی کنید.",
            "ar": "تم اكتشاف تنبيه صحي. يرجى التحقق من قراءاتك.",
        },
        "device_disconnected": {
            "en": "Device connection lost. Please reconnect your device.",
            "fa": "اتصال دستگاه قطع شده. لطفاً دستگاه را دوباره وصل کنید.",
            "ar": "فُقد اتصال الجهاز. يرجى إعادة توصيل جهازك.",
        },
        "morning_brief": {
            "en": "Good morning. Have a wonderful day.",
            "fa": "صبح بخیر. روز خوبی داشته باشید.",
            "ar": "صباح الخير. أتمنى لك يوماً سعيداً.",
        },
        "connection_ping": {
            "en": "Hello. Hope you're doing well.",
            "fa": "سلام. امیدوارم حالتون خوب باشه.",
            "ar": "مرحباً. أتمنى أن تكون بخير.",
        },
        "companion_ping": {
            "en": "Hi; I was thinking of you. If you'd like, tell me how today's going? 🌿",
            "fa": "سلام؛ دلم برات تنگ شده. اگر دوست داری بگو امروز چطوره؟ 🌿",
            "ar": "مرحباً؛ كنت أفكر بك. إذا أحببت، أخبرني كيف يومك؟ 🌿",
        },
    }
    type_defaults = defaults.get(notification_type, defaults["health_alert"])
    return type_defaults.get(language, type_defaults["en"])


# -------------------- Timing Rules --------------------
class TimingRules:
    """Manages timing rules for notifications"""
    
    @staticmethod
    def should_send_immediately(priority: str) -> bool:
        """Determine if notification should be sent immediately based on priority"""
        return priority in ["high", "critical"]
    
    @staticmethod
    def calculate_scheduled_time(
        priority: str,
        base_time: Optional[datetime] = None
    ) -> Optional[datetime]:
        """
        Calculate scheduled time for notification based on priority.
        
        Returns None for immediate notifications (high/critical priority).
        Returns scheduled datetime for lower priority notifications.
        """
        if base_time is None:
            base_time = datetime.utcnow()
        
        if priority in ["high", "critical"]:
            return None  # Send immediately
        
        if priority == "normal":
            # Schedule for next hour
            return base_time + timedelta(hours=1)
        
        if priority == "low":
            # Schedule for next 4 hours
            return base_time + timedelta(hours=4)
        
        return None
    
    @staticmethod
    def get_reminder_interval(condition_type: str) -> Optional[timedelta]:
        """
        Get reminder interval for condition-based notifications.
        
        Returns None if no reminder needed, or timedelta for reminder interval.
        """
        # Simple rule-based intervals (can be enhanced with RAG)
        intervals = {
            "medication": timedelta(hours=8),  # Medication reminders every 8 hours
            "checkup": timedelta(days=7),  # Weekly checkup reminders
            "monitoring": timedelta(hours=12),  # Health monitoring every 12 hours
        }
        return intervals.get(condition_type)


# -------------------- Notification Builder --------------------
class NotificationBuilder:
    """Builds notification objects with proper structure (Release B - Part B1)"""
    
    def __init__(self, db: Session):
        self.db = db
        self.timing_rules = TimingRules()
    
    # -------------------- Release B: New Contract Methods --------------------
    
    def compute_dedupe_key(
        self,
        notification_type: Literal["morning_brief", "connection_ping", "health_alert", "device_disconnected"],
        user_id: int,
        scheduled_for: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Compute deterministic dedupe key for notification.
        
        Format:
        - morning_brief:{user_id}:{YYYY-MM-DD}
        - connection_ping:{user_id}:{YYYY-MM-DD}:{window}  (4h bucket)
        - health_alert:{user_id}:{alert_code}:{YYYY-MM-DDTHH}
        - device_disconnected:{device_id}:{YYYY-MM-DD}:{6h_bucket}  (once per 6h per device)
        """
        now = scheduled_for or datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")
        
        if notification_type == "morning_brief":
            return f"morning_brief:{user_id}:{date_str}"
        
        elif notification_type == "connection_ping":
            # Use 4-hour window bucket
            hour_bucket = (now.hour // 4) * 4
            return f"connection_ping:{user_id}:{date_str}:{hour_bucket:02d}"
        
        elif notification_type == "health_alert":
            alert_code = metadata.get("alert_code", "generic") if metadata else "generic"
            # Medication reminders: one per medication per 8h bucket (no spam)
            if alert_code == "medication_reminder" and metadata and metadata.get("medication_id") is not None:
                med_id = metadata.get("medication_id")
                hour_bucket_8 = (now.hour // 8) * 8
                return f"health_alert:{user_id}:medication_reminder:{med_id}:{date_str}:{hour_bucket_8:02d}"
            hour_str = now.strftime("%H")
            return f"health_alert:{user_id}:{alert_code}:{date_str}T{hour_str}"
        
        elif notification_type == "device_disconnected":
            device_id = (metadata or {}).get("device_id", "unknown")
            hour_bucket = (now.hour // 6) * 6  # 6-hour bucket: once per X hours
            return f"device_disconnected:{device_id}:{date_str}:{hour_bucket:02d}"
        
        else:
            # Fallback for unknown types
            return f"{notification_type}:{user_id}:{date_str}"
    
    def check_dedupe(self, dedupe_key: str, time_window_hours: int = 24) -> bool:
        """
        Check if a notification with the same dedupe_key exists within time window.
        
        Args:
            dedupe_key: Deduplication key
            time_window_hours: Time window in hours (default: 24)
        
        Returns:
            True if duplicate exists, False otherwise
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)
        
        existing = (
            self.db.query(Notification)
            .filter(
                Notification.dedupe_key == dedupe_key,
                Notification.created_at >= cutoff_time
            )
            .first()
        )
        
        return existing is not None
    
    def build_payload(
        self,
        user_id: int,
        notification_type: Literal["morning_brief", "connection_ping", "health_alert", "device_disconnected"],
        title: str,
        body: str,
        priority: Literal["low", "normal", "high", "critical"] = "normal",
        scheduled_for: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> NotificationPayload:
        """
        Build NotificationPayload (Release B - Part B1).
        
        This is the entry point for the new notification contract.
        """
        # Compute dedupe key
        dedupe_key = self.compute_dedupe_key(
            notification_type=notification_type,
            user_id=user_id,
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        # Calculate scheduled time if not provided
        if scheduled_for is None:
            scheduled_for = self.timing_rules.calculate_scheduled_time(priority)
        
        # NotificationPayload requires body min_length=1; ensure non-empty before apply_fallback
        if not (body and body.strip()):
            body = _default_body_for_type(notification_type, metadata)
        
        return NotificationPayload(
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            priority=priority,
            scheduled_for=scheduled_for,
            dedupe_key=dedupe_key,
            metadata=metadata
        )
    
    def apply_fallback(
        self,
        payload: NotificationPayload,
        user_name: Optional[str] = None,
        memory_context: Optional[MemoryContext] = None,
        language: Optional[str] = None
    ) -> NotificationPayload:
        """
        Apply deterministic fallback text generation (Release B2.1).
        
        Always returns payload with non-empty body. Never raises.
        Uses language from payload.metadata if available, otherwise uses provided language.
        """
        # Resolve language from metadata or provided parameter
        effective_language = "en"  # Default fallback
        if payload.metadata and "language" in payload.metadata:
            effective_language = payload.metadata["language"]
        elif language:
            effective_language = language
        
        # Ensure language is valid
        if effective_language not in ("en", "fa", "ar"):
            effective_language = "en"
        
        # Generate fallback text with language
        fallback_body = generate_fallback_text(
            payload=payload,
            language=effective_language,
            user_name=user_name,
            memory_context=memory_context
        )
        
        # Update payload with fallback body (if original is empty, use fallback)
        if not payload.body or len(payload.body.strip()) == 0:
            return NotificationPayload(
                **{**payload.model_dump(), "body": fallback_body}
            )
        
        # Otherwise keep original body (fallback is just a safety net)
        return payload
    
    def persist(
        self,
        payload: NotificationPayload,
        check_dedupe: bool = True,
        time_window_hours: int = 24,
        trace_id: Optional[str] = None,
    ) -> Optional[Notification]:
        """
        Persist notification to database with dedupe check.
        
        Args:
            payload: NotificationPayload to persist
            check_dedupe: Whether to check for duplicates (default: True)
            time_window_hours: Time window for dedupe check (default: 24)
        
        Returns:
            Notification object if created, None if duplicate found
        """
        # Check dedupe if enabled (Release B2: Rate limit enforcement)
        if check_dedupe and self.check_dedupe(payload.dedupe_key, time_window_hours):
            logger.info(
                f"[Notification] Rate limit/dedupe: Suppressed type={payload.type} "
                f"user={payload.user_id} dedupe_key={payload.dedupe_key} "
                f"(window={time_window_hours}h)"
            )
            return None
        
        # Stage 16.6: channel + language + status for push pipeline
        channel = _channel_for_type(payload.type)
        language = (payload.metadata or {}).get("language") if payload.metadata else None
        default_actions = '[{"id":"like","type":"LIKE"},{"id":"dislike","type":"DISLIKE"},{"id":"open_chat","type":"OPEN_CHAT"}]'

        # Build notification object
        notification = Notification(
            user_id=payload.user_id,
            type=payload.type,
            title=payload.title,
            body=payload.body,
            priority=payload.priority,
            is_read=False,
            is_sent=False,
            scheduled_for=payload.scheduled_for,
            dedupe_key=payload.dedupe_key,
            created_at=datetime.utcnow(),
            channel=channel,
            language=language,
            status="queued",
            actions_json=default_actions,
            provider=None,
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        # Stage 16.6: Set deeplink_url for app routing
        if not notification.deeplink_url:
            notification.deeplink_url = f"sedi://chat?from=notif&id={notification.id}"
            self.db.add(notification)
            self.db.commit()
        
        # Log creation (Stage 16.6.2: structured [NOTIF] prefix, no secrets)
        logger.info(
            "[NOTIF] enqueue channel=%s user_id=%s dedupe=%s trace=%s",
            (channel or payload.type or "?"),
            payload.user_id,
            payload.dedupe_key[:80] + "..." if len(payload.dedupe_key or "") > 80 else (payload.dedupe_key or "?"),
            trace_id or "",
        )
        
        return notification
    
    # -------------------- Legacy Methods (Backward Compatible) --------------------
    
    def build(
        self,
        user_id: int,
        notification_type: str,
        title: Optional[str],
        body: str,
        priority: str = "normal",
        scheduled_for: Optional[datetime] = None
    ) -> Notification:
        """
        Build a notification object (legacy method).
        
        Args:
            user_id: User ID
            notification_type: Type of notification (HEALTH, REMINDER, INSIGHT)
            title: Notification title (optional)
            body: Notification body/message (required)
            priority: Priority level (low, normal, high, critical)
            scheduled_for: Scheduled datetime (None for immediate)
        
        Returns:
            Notification object (not yet committed to database)
        """
        # Validate priority
        valid_priorities = ["low", "normal", "high", "critical"]
        if priority not in valid_priorities:
            priority = "normal"
        
        # Calculate scheduled time if not provided
        if scheduled_for is None:
            scheduled_for = self.timing_rules.calculate_scheduled_time(priority)
        
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            priority=priority,
            is_read=False,
            is_sent=False,
            scheduled_for=scheduled_for,
            created_at=datetime.utcnow()
        )
        
        return notification
    
    def create_and_save(
        self,
        user_id: int,
        notification_type: str,
        title: Optional[str],
        body: str,
        priority: str = "normal",
        scheduled_for: Optional[datetime] = None
    ) -> Notification:
        """
        Build and save notification to database (legacy method).
        
        Returns the saved notification object.
        """
        notification = self.build(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            body=body,
            priority=priority,
            scheduled_for=scheduled_for
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        return notification


# -------------------- Decision Engine --------------------
class DecisionEngine:
    """
    Decision Engine - Determines when and what notifications to create.
    
    This is the central decision-making component for notifications.
    All notification creation logic should go through this engine.
    
    Release B - Part B1: Routes all notification creation through the new contract:
    build_payload → apply_fallback → enhance_with_ai → persist
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.builder = NotificationBuilder(db)
        self.medical_service = MedicalService(db)
        self.rag_service = RAGService(db)
        self.timing_rules = TimingRules()
    
    # -------------------- Release B: New Contract Methods --------------------
    
    def create_morning_brief(
        self,
        user_id: int,
        memory_context: Optional[MemoryContext] = None,
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create morning_brief notification using new contract (Release B2.1 / Stage 16.6.4).
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        user_ctx = build_notification_context(self.db, user_id)
        effective_language = (user_ctx.get("language") or resolve_effective_language(
            db=self.db, user_id=user_id, memory_context=memory_context
        ))
        if effective_language not in ("en", "fa", "ar"):
            effective_language = "en"
        metadata = {"language": effective_language}

        # Stage 16.6.4: Quiet hours suppression
        if is_within_quiet_hours(self.db, user_id, "morning", "normal"):
            logger.info("[NOTIF] suppressed channel=morning user_id=%s reason=quiet_hours", user_id)
            return None

        # Stage 16.6.4: Use renderer for title/body; user_ctx for personalization
        inputs = _build_render_inputs(memory_context, metadata, user_name, effective_language)
        rendered = render("morning", effective_language, inputs, "normal", user_ctx=user_ctx)

        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="morning_brief",
            title=rendered["title"],
            body=rendered["body"],
            priority="normal",
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=memory_context,
            language=effective_language
        )
        
        # Enhance with AI (safe wrapper)
        payload = enhance_with_ai(payload)
        
        # Persist with dedupe check (Rate limit: 1 per day per user)
        result = self.builder.persist(payload, check_dedupe=True, time_window_hours=24)
        if result is None:
            logger.info(
                f"[NOTIFICATION] SUPPRESSED type=morning_brief user={user_id} "
                f"lang={effective_language} reason=dedupe"
            )
        else:
            logger.info(
                f"[NOTIFICATION] type=morning_brief user={user_id} "
                f"lang={effective_language} dedupe={payload.dedupe_key}"
            )
        return result
    
    def create_connection_ping(
        self,
        user_id: int,
        memory_context: Optional[MemoryContext] = None,
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create connection_ping notification (Release B2.1 / Stage 16.6.4).
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        user_ctx = build_notification_context(self.db, user_id)
        effective_language = (user_ctx.get("language") or resolve_effective_language(
            db=self.db, user_id=user_id, memory_context=memory_context
        ))
        if effective_language not in ("en", "fa", "ar"):
            effective_language = "en"
        metadata = {"language": effective_language}

        if is_within_quiet_hours(self.db, user_id, "engagement", "low"):
            logger.info("[NOTIF] suppressed channel=engagement user_id=%s reason=quiet_hours", user_id)
            return None

        inputs = _build_render_inputs(memory_context, metadata, user_name, effective_language)
        rendered = render("engagement", effective_language, inputs, "low", user_ctx=user_ctx)

        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="connection_ping",
            title=rendered["title"],
            body=rendered["body"],
            priority="low",
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=memory_context,
            language=effective_language
        )
        
        # Enhance with AI (safe wrapper)
        payload = enhance_with_ai(payload)
        
        # Persist with dedupe check (Rate limit: 1 per user per 4-hour window)
        result = self.builder.persist(payload, check_dedupe=True, time_window_hours=4)
        if result is None:
            logger.info(
                f"[NOTIFICATION] SUPPRESSED type=connection_ping user={user_id} "
                f"lang={effective_language} reason=dedupe"
            )
        else:
            logger.info(
                f"[NOTIFICATION] type=connection_ping user={user_id} "
                f"lang={effective_language} dedupe={payload.dedupe_key}"
            )
        return result

    def create_engagement_nudge(
        self,
        user_id: int,
        memory_context: Optional[MemoryContext] = None,
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Stage 16.6: Create engagement nudge (inactive 3h+). Stage 16.6.4: quiet hours, renderer.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        user_ctx = build_notification_context(self.db, user_id)
        effective_language = (user_ctx.get("language") or resolve_effective_language(
            db=self.db, user_id=user_id, memory_context=memory_context
        ))
        if effective_language not in ("en", "fa", "ar"):
            effective_language = "en"
        metadata = {"language": effective_language}

        if is_within_quiet_hours(self.db, user_id, "engagement", "normal"):
            logger.info("[NOTIF] suppressed channel=engagement user_id=%s reason=quiet_hours", user_id)
            return None

        inputs = _build_render_inputs(memory_context, metadata, user_name, effective_language)
        rendered = render("engagement", effective_language, inputs, "normal", user_ctx=user_ctx)

        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="connection_ping",
            title=rendered["title"],
            body=rendered["body"],
            priority="normal",
            scheduled_for=scheduled_for,
            metadata=metadata,
        )
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=memory_context,
            language=effective_language,
        )
        payload = enhance_with_ai(payload)
        now = scheduled_for or datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")
        bucket = (now.hour // 3) * 3
        payload = payload.model_copy(
            update={"dedupe_key": f"engagement:{user_id}:{date_str}:{bucket:02d}"}
        )
        result = self.builder.persist(payload, check_dedupe=True, time_window_hours=24)
        if result:
            logger.info(
                f"[NOTIFICATION] type=engagement_nudge user={user_id} "
                f"dedupe={payload.dedupe_key}"
            )
        return result

    def create_health_alert(
        self,
        user_id: int,
        alert_code: str,
        alert_reason: Optional[str] = None,
        priority: Literal["low", "normal", "high", "critical"] = "high",
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create health_alert notification (Release B2.1 / Stage 16.6.4).
        Conservative phrasing; quiet hours suppress non-critical only.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        user_ctx = build_notification_context(self.db, user_id)
        effective_language = (user_ctx.get("language") or resolve_effective_language(
            db=self.db, user_id=user_id, memory_context=None
        ))
        if effective_language not in ("en", "fa", "ar"):
            effective_language = "en"
        metadata = {
            "language": effective_language,
            "alert_code": alert_code,
            "alert_reason": alert_reason,
        }

        if is_within_quiet_hours(self.db, user_id, "health_alert", priority):
            logger.info("[NOTIF] suppressed channel=health_alert user_id=%s reason=quiet_hours", user_id)
            return None

        inputs = _build_render_inputs(None, metadata, user_name, effective_language)
        rendered = render("health_alert", effective_language, inputs, priority, user_ctx=user_ctx)

        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="health_alert",
            title=rendered["title"],
            body=rendered["body"],
            priority=priority,
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=None,  # Health alerts don't need lifestyle context
            language=effective_language
        )
        
        # Enhance with AI (safe wrapper)
        payload = enhance_with_ai(payload)
        
        # Persist with dedupe check (Rate limit: dedupe by alert_code + time bucket)
        result = self.builder.persist(payload, check_dedupe=True, time_window_hours=1)
        if result is None:
            logger.info(
                f"[NOTIFICATION] SUPPRESSED type=health_alert user={user_id} "
                f"lang={effective_language} alert_code={alert_code} reason=dedupe"
            )
        else:
            logger.info(
                f"[NOTIFICATION] type=health_alert user={user_id} "
                f"lang={effective_language} dedupe={payload.dedupe_key}"
            )
        return result
    
    def create_device_disconnected(
        self,
        user_id: int,
        device_id: str,
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create device_disconnected notification when a device has not been seen
        for longer than threshold (scheduler job). Dedupe: once per device per 6h bucket.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=None
        )
        metadata = {
            "language": effective_language,
            "device_id": device_id,
        }
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="device_disconnected",
            title=_get_title_for_language("device_disconnected", effective_language),
            body="",
            priority="normal",
            scheduled_for=scheduled_for,
            metadata=metadata,
        )
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=None,
            language=effective_language,
        )
        payload = enhance_with_ai(payload)
        # Once per 6 hours per device (dedupe key includes 6h bucket)
        result = self.builder.persist(payload, check_dedupe=True, time_window_hours=6)
        if result is None:
            logger.info(
                f"[NOTIFICATION] SUPPRESSED type=device_disconnected user={user_id} "
                f"device_id={device_id} reason=dedupe"
            )
        else:
            logger.info(
                f"[NOTIFICATION] type=device_disconnected user={user_id} "
                f"device_id={device_id} dedupe={payload.dedupe_key}"
            )
        return result

    def create_companion_ping(
        self,
        user_id: int,
        language: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Optional[Notification]:
        """
        Behavior Layer V1: Create companion_ping notification when policy allows (quiet hours, daily cap, cooldown).
        Message and deeplink (from=notif&type=companion_ping) are controlled by BehaviorPolicy.
        Returns None when disabled, blocked, or dedupe.
        """
        from backend.app.behavior.service import try_create_companion_ping_notification
        return try_create_companion_ping_notification(self.db, user_id, lang=language, now=now)
    
    # -------------------- Lifestyle-Based Notifications --------------------
    
    def evaluate_lifestyle_context(
        self,
        user_id: int,
        memory_context: Optional[MemoryContext] = None
    ) -> Optional[Notification]:
        """
        Evaluate lifestyle context and create notifications if needed.
        
        Lifestyle rules:
        - Low sleep (< 6 hours) -> gentle sleep-care notification
        - Low hydration (< 1500ml) -> hydration reminder
        - Inactivity (no activity data) -> gentle movement reminder
        
        Args:
            user_id: User ID
            memory_context: Optional MemoryContext (will be built if not provided)
        
        Returns:
            Notification if created, None otherwise.
        """
        # Build context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Release B2.1: Use new contract types instead of legacy REMINDER/INSIGHT
        # Resolve language
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=memory_context
        )
        
        # Rule 1: Low sleep duration -> use connection_ping (gentle reminder)
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6.0:
                return self.create_connection_ping(
                    user_id=user_id,
                    memory_context=memory_context
                )
        
        # Rule 2: Low hydration -> use connection_ping (gentle reminder)
        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                return self.create_connection_ping(
                    user_id=user_id,
                    memory_context=memory_context
                )
        
        # Rule 3: Inactivity -> use connection_ping (gentle reminder)
        if not memory_context.has_activity_data():
            return self.create_connection_ping(
                user_id=user_id,
                memory_context=memory_context
            )
        
        return None
    
    # -------------------- Health-Based Notifications --------------------
    
    def evaluate_health_data(
        self,
        user_id: int,
        health_data: HealthData,
        memory_context: Optional[MemoryContext] = None
    ) -> Optional[Notification]:
        """
        Evaluate health data and create notification if needed.
        
        Args:
            user_id: User ID
            health_data: HealthData object
            memory_context: Optional MemoryContext for lifestyle-aware decisions
        
        Returns Notification if created, None otherwise.
        """
        # Get user conditions for context
        user_conditions = self.medical_service.get_user_conditions(user_id)
        
        # Determine priority and message based on health metrics
        priority = "normal"
        title = "Health Update"
        body_parts = []
        
        # Check heart rate
        if health_data.heart_rate:
            try:
                hr = float(health_data.heart_rate)
                if hr > 100:
                    priority = "high"
                    body_parts.append(f"Heart rate is elevated: {hr} bpm")
                elif hr < 60:
                    priority = "high"
                    body_parts.append(f"Heart rate is low: {hr} bpm")
                else:
                    body_parts.append(f"Heart rate: {hr} bpm (normal)")
            except (ValueError, TypeError):
                pass
        
        # Check SpO2
        if health_data.spo2:
            try:
                spo2 = float(health_data.spo2)
                if spo2 < 95:
                    priority = "critical"
                    body_parts.append(f"⚠️ Low oxygen saturation: {spo2}%")
                else:
                    body_parts.append(f"SpO2: {spo2}% (normal)")
            except (ValueError, TypeError):
                pass
        
        # Check temperature
        if health_data.temperature:
            try:
                temp = float(health_data.temperature)
                if temp > 37.5:
                    priority = "high" if priority != "critical" else "critical"
                    body_parts.append(f"⚠️ Elevated temperature: {temp}°C")
                else:
                    body_parts.append(f"Temperature: {temp}°C (normal)")
            except (ValueError, TypeError):
                pass
        
        # If no alerts, don't create notification
        if not body_parts or priority == "normal":
            return None
        
        # Build notification body
        body = " | ".join(body_parts)
        
        # TODO: RAG integration - enhance body with condition-specific care guidelines
        # if user_conditions:
        #     rag_context = self.rag_service.retrieve_condition_context(
        #         condition_name=user_conditions[0].condition.name,
        #         user_conditions=user_conditions
        #     )
        #     if rag_context:
        #         body += f"\n\nCare tip: {rag_context}"
        
        # Create notification using health_alert type (Release B2.1)
        # Resolve language
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=memory_context
        )
        
        # Build metadata with language and alert info
        metadata = {
            "language": effective_language,
            "alert_code": "health_data_alert",
            "alert_reason": body
        }
        
        # Use health_alert type instead of legacy HEALTH
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="health_alert",
            title=_get_title_for_language("health_alert", effective_language),
            body=body,
            priority=priority,
            scheduled_for=None,
            metadata=metadata
        )
        
        # Apply fallback
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=memory_context,
            language=effective_language
        )
        
        # Persist
        result = self.builder.persist(payload, check_dedupe=False)  # Legacy method
        if result:
            logger.info(
                f"[NOTIFICATION] type=health_alert user={user_id} "
                f"lang={effective_language} dedupe={payload.dedupe_key} (legacy:evaluate_health_data)"
            )
        return result
    
    # -------------------- Condition-Based Notifications --------------------
    
    def create_condition_reminder(
        self,
        user_id: int,
        condition_id: int,
        reminder_type: str = "monitoring"
    ) -> Optional[Notification]:
        """
        Create a reminder notification for a user's medical condition.
        
        Args:
            user_id: User ID
            condition_id: Medical condition ID
            reminder_type: Type of reminder (medication, checkup, monitoring)
        
        Returns Notification if created, None otherwise.
        """
        # Get condition details
        condition = self.medical_service.get_condition_by_id(condition_id)
        if not condition:
            return None
        
        # Get user condition assignment
        user_conditions = self.medical_service.get_user_conditions(user_id)
        user_condition = next(
            (uc for uc in user_conditions if uc.condition_id == condition_id),
            None
        )
        
        if not user_condition:
            return None
        
        # Build reminder message
        title = f"{condition.name} Reminder"
        body = f"Time to check on your {condition.name.lower()}"
        
        # Determine priority based on condition severity
        priority = "normal"
        if user_condition.severity == "severe":
            priority = "high"
        elif user_condition.severity == "moderate":
            priority = "normal"
        else:
            priority = "low"
        
        # Get reminder interval
        interval = self.timing_rules.get_reminder_interval(reminder_type)
        scheduled_for = None
        if interval:
            scheduled_for = datetime.utcnow() + interval
        
        # TODO: RAG integration - enhance with condition-specific care guidelines
        # rag_context = self.rag_service.retrieve_condition_context(
        #     condition_name=condition.name,
        #     user_conditions=[user_condition]
        # )
        # if rag_context:
        #     body += f"\n\nCare tip: {rag_context}"
        
        # Release B2.1: Use health_alert type for condition reminders
        # Resolve language
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=None
        )
        
        # Build metadata with language
        metadata = {
            "language": effective_language,
            "alert_code": f"condition_reminder_{reminder_type}",
            "alert_reason": body
        }
        
        # Use health_alert type instead of legacy REMINDER
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="health_alert",
            title=_get_title_for_language("health_alert", effective_language),
            body=body,
            priority=priority,
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        # Apply fallback
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=None,
            language=effective_language
        )
        
        # Persist
        result = self.builder.persist(payload, check_dedupe=False)  # Legacy method
        if result:
            logger.info(
                f"[NOTIFICATION] type=health_alert user={user_id} "
                f"lang={effective_language} dedupe={payload.dedupe_key} (legacy:create_condition_reminder)"
            )
        return result
    
    # -------------------- Medication Reminders --------------------
    
    def create_medication_reminder(
        self,
        user_id: int,
        medication_name: str,
        dosage: Optional[str] = None,
        medication_id: Optional[int] = None,
    ) -> Optional[Notification]:
        """
        Create a medication reminder notification (Release B2.1).
        Used by scheduler loop and optional API. Dedupe: once per medication per 8h when medication_id provided.
        
        Args:
            user_id: User ID
            medication_name: Name of medication
            dosage: Dosage information (optional)
            medication_id: Optional; when set, dedupe is per-medication per 8h (for scheduled loop).
        
        Returns Notification if created, None if duplicate/suppressed.
        """
        title = "Medication Reminder"
        body = f"Time to take {medication_name}"
        if dosage:
            body += f" ({dosage})"
        
        priority = "high"
        interval = self.timing_rules.get_reminder_interval("medication")
        scheduled_for = None
        if interval:
            scheduled_for = datetime.utcnow() + interval
        
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=None
        )
        
        metadata = {
            "language": effective_language,
            "alert_code": "medication_reminder",
            "alert_reason": body,
        }
        if medication_id is not None:
            metadata["medication_id"] = medication_id
        
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="health_alert",
            title=_get_title_for_language("health_alert", effective_language),
            body=body,
            priority=priority,
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=None,
            language=effective_language
        )
        
        # Dedupe: when medication_id set, at most one per medication per 8h
        check_dedupe = medication_id is not None
        time_window_hours = 8 if medication_id is not None else 24
        result = self.builder.persist(payload, check_dedupe=check_dedupe, time_window_hours=time_window_hours)
        if result:
            logger.info(
                f"[NOTIFICATION] type=health_alert user={user_id} medication_reminder "
                f"medication_id={medication_id} dedupe={payload.dedupe_key}"
            )
        else:
            logger.info(
                f"[NOTIFICATION] SUPPRESSED medication_reminder user={user_id} medication_id={medication_id} reason=dedupe"
            )
        return result
    
    # -------------------- Insight Notifications --------------------
    
    def create_insight_notification(
        self,
        user_id: int,
        insight_text: str,
        priority: str = "normal"
    ) -> Notification:
        """
        Create an insight notification (health insights, trends, etc.) - Release B2.1.
        
        Legacy method: Maps to connection_ping type (gentle check-in style).
        Maintains backward compatibility while using new contract.
        
        Args:
            user_id: User ID
            insight_text: Insight message
            priority: Priority level (default: normal)
        
        Returns Notification object.
        """
        # Resolve language
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=None
        )
        
        # Build metadata with language
        metadata = {
            "language": effective_language
        }
        
        # Use connection_ping type (gentle check-in) instead of legacy INSIGHT
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="connection_ping",
            title=_get_title_for_language("connection_ping", effective_language),
            body=insight_text,  # Use provided text
            priority=priority,
            scheduled_for=None,
            metadata=metadata
        )
        
        # Apply fallback (will use provided text if not empty)
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=None,
            language=effective_language
        )
        
        # Persist
        result = self.builder.persist(payload, check_dedupe=False)  # Legacy method doesn't enforce dedupe
        if result:
            logger.info(
                f"[NOTIFICATION] type=connection_ping user={user_id} "
                f"lang={effective_language} dedupe={payload.dedupe_key} (legacy:create_insight_notification)"
            )
        return result
    
    # -------------------- Lifestyle-Based Notifications --------------------
    
    def evaluate_lifestyle_context(
        self,
        user_id: int,
        memory_context: Optional[MemoryContext] = None
    ) -> Optional[Notification]:
        """
        Evaluate lifestyle context and create notifications if needed.
        
        Lifestyle rules:
        - Low sleep (< 6 hours) -> gentle sleep-care notification
        - Low hydration (< 1500ml) -> hydration reminder
        - Inactivity (no activity data) -> gentle movement reminder
        
        Args:
            user_id: User ID
            memory_context: Optional MemoryContext (will be built if not provided)
        
        Returns:
            Notification if created, None otherwise.
        """
        # Build context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Release B2.1: Use new contract types instead of legacy REMINDER/INSIGHT
        # Resolve language
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=memory_context
        )
        
        # Rule 1: Low sleep duration -> use connection_ping (gentle reminder)
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6.0:
                return self.create_connection_ping(
                    user_id=user_id,
                    memory_context=memory_context
                )
        
        # Rule 2: Low hydration -> use connection_ping (gentle reminder)
        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                return self.create_connection_ping(
                    user_id=user_id,
                    memory_context=memory_context
                )
        
        # Rule 3: Inactivity -> use connection_ping (gentle reminder)
        if not memory_context.has_activity_data():
            return self.create_connection_ping(
                user_id=user_id,
                memory_context=memory_context
            )
        
        return None
    
    # -------------------- Combined Evaluation (Health + Lifestyle) --------------------
    
    def evaluate_user_state(
        self,
        user_id: int,
        health_data: Optional[HealthData] = None,
        memory_context: Optional[MemoryContext] = None
    ) -> List[Notification]:
        """
        Evaluate both health data and lifestyle context, returning all relevant notifications.
        
        This is a convenience method that combines health and lifestyle evaluation.
        
        Args:
            user_id: User ID
            health_data: Optional HealthData object
            memory_context: Optional MemoryContext (will be built if not provided)
        
        Returns:
            List of Notification objects (may be empty)
        """
        notifications = []
        
        # Build context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Evaluate health data
        if health_data:
            health_notif = self.evaluate_health_data(user_id, health_data, memory_context)
            if health_notif:
                notifications.append(health_notif)
        
        # Evaluate lifestyle context
        lifestyle_notif = self.evaluate_lifestyle_context(user_id, memory_context)
        if lifestyle_notif:
            notifications.append(lifestyle_notif)
        
        return notifications


# -------------------- Stage 16.6: Health alert hook (safe entrypoint for decision engine / vitals) --------------------
def enqueue_health_alert(
    db: Session,
    user_id: int,
    alert_code: str,
    alert_reason: Optional[str] = None,
    priority: Literal["low", "normal", "high", "critical"] = "high",
    scheduled_for: Optional[datetime] = None,
    **kwargs: Any
) -> Optional[Notification]:
    """
    Enqueue a health alert notification. Safe entrypoint callable from decision engine
    or vitals/rules later. Does NOT implement vitals rules here.
    """
    engine = DecisionEngine(db)
    return engine.create_health_alert(
        user_id=user_id,
        alert_code=alert_code,
        alert_reason=alert_reason,
        priority=priority,
        scheduled_for=scheduled_for,
    )


# -------------------- D1: Persist health_alert with explicit title/body/dedupe_key (caller does dedupe check) --------------------
def persist_health_alert_d1(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    dedupe_key: str,
    priority: Literal["low", "normal", "high", "critical"] = "high",
    trace_id: Optional[str] = None,
) -> Optional[Notification]:
    """
    Create a health_alert notification row with given title, body, dedupe_key.
    Caller must ensure no duplicate dedupe_key exists (app-level dedupe).
    """
    if not body or not body.strip():
        body = "هشدار سلامت ثبت شد."
    payload = NotificationPayload(
        user_id=user_id,
        type="health_alert",
        title=(title or "هشدار سلامت").strip(),
        body=body.strip(),
        priority=priority,
        scheduled_for=None,
        dedupe_key=dedupe_key,
        metadata={"language": "fa"},
    )
    builder = NotificationBuilder(db)
    return builder.persist(payload, check_dedupe=False, trace_id=trace_id)