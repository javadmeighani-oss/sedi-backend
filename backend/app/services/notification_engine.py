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

logger = logging.getLogger(__name__)


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
        time_window_hours: int = 24
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
            created_at=datetime.utcnow()
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        # Log creation
        ai_enhanced = "true" if payload.metadata and payload.metadata.get("ai_enhanced") else "false"
        logger.info(
            f"[Notification] created type={payload.type} user={payload.user_id} "
            f"dedupe_key={payload.dedupe_key} ai_enhanced={ai_enhanced}"
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
        Create morning_brief notification using new contract (Release B2.1).
        
        Args:
            user_id: User ID
            memory_context: Optional MemoryContext for personalization
            scheduled_for: Optional scheduled time
        
        Returns:
            Notification if created, None if duplicate or error
        """
        # Get user and resolve language
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        
        # Build memory context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Resolve effective language (Release B2.1)
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=memory_context
        )
        
        # Build metadata with language (Release B2.1)
        metadata = {
            "language": effective_language
        }
        
        # Build payload with correct type and metadata
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="morning_brief",
            title=_get_title_for_language("morning_brief", effective_language),
            body="",  # Will be filled by fallback
            priority="normal",
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        # Apply fallback with language
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
        Create connection_ping notification using new contract (Release B2.1).
        
        Args:
            user_id: User ID
            memory_context: Optional MemoryContext for personalization
            scheduled_for: Optional scheduled time
        
        Returns:
            Notification if created, None if duplicate or error
        """
        # Get user and resolve language
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        
        # Build memory context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Resolve effective language (Release B2.1)
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=memory_context
        )
        
        # Build metadata with language (Release B2.1)
        metadata = {
            "language": effective_language
        }
        
        # Build payload with correct type and metadata
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="connection_ping",
            title=_get_title_for_language("connection_ping", effective_language),
            body="",  # Will be filled by fallback
            priority="low",
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        # Apply fallback with language
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
    
    def create_health_alert(
        self,
        user_id: int,
        alert_code: str,
        alert_reason: Optional[str] = None,
        priority: Literal["low", "normal", "high", "critical"] = "high",
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create health_alert notification using new contract (Release B2.1).
        
        Args:
            user_id: User ID
            alert_code: Alert code (e.g. "high_heart_rate", "low_spo2")
            alert_reason: Optional alert reason text
            priority: Priority level (default: high)
            scheduled_for: Optional scheduled time
        
        Returns:
            Notification if created, None if duplicate or error
        """
        # Get user and resolve language
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        
        # Resolve effective language (Release B2.1)
        effective_language = resolve_effective_language(
            db=self.db,
            user_id=user_id,
            memory_context=None
        )
        
        # Build metadata with language and alert info (Release B2.1)
        metadata = {
            "language": effective_language,
            "alert_code": alert_code,
            "alert_reason": alert_reason
        }
        
        # Build payload with correct type and metadata
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="health_alert",
            title=_get_title_for_language("health_alert", effective_language),
            body="",  # Will be filled by fallback
            priority=priority,
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        # Apply fallback with language
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