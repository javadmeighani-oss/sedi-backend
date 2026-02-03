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

from app.models import Notification, User, UserCondition, HealthData
from app.services.medical import MedicalService
from app.services.rag import RAGService
from app.services.memory import MemoryContext, build_memory_context
from app.schemas.notification import NotificationPayload
from app.services.notification_engine.fallback_generator import generate_fallback_text
from app.services.notification_engine.ai_enhancer import enhance_with_ai

logger = logging.getLogger(__name__)


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
        notification_type: Literal["morning_brief", "connection_ping", "health_alert"],
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
            hour_str = now.strftime("%H")
            return f"health_alert:{user_id}:{alert_code}:{date_str}T{hour_str}"
        
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
        notification_type: Literal["morning_brief", "connection_ping", "health_alert"],
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
        memory_context: Optional[MemoryContext] = None
    ) -> NotificationPayload:
        """
        Apply deterministic fallback text generation.
        
        Always returns payload with non-empty body. Never raises.
        """
        # Generate fallback text
        fallback_body = generate_fallback_text(
            payload=payload,
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
        # Check dedupe if enabled
        if check_dedupe and self.check_dedupe(payload.dedupe_key, time_window_hours):
            logger.debug(f"[Notification] Duplicate detected, skipping: dedupe_key={payload.dedupe_key}")
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
        Create morning_brief notification using new contract.
        
        Args:
            user_id: User ID
            memory_context: Optional MemoryContext for personalization
            scheduled_for: Optional scheduled time
        
        Returns:
            Notification if created, None if duplicate or error
        """
        # Get user name
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        
        # Build memory context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Build payload
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="morning_brief",
            title="صبح بخیر",
            body="",  # Will be filled by fallback
            priority="normal",
            scheduled_for=scheduled_for,
            metadata=None
        )
        
        # Apply fallback
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=memory_context
        )
        
        # Enhance with AI (safe wrapper)
        payload = enhance_with_ai(payload)
        
        # Persist with dedupe check
        return self.builder.persist(payload, check_dedupe=True)
    
    def create_connection_ping(
        self,
        user_id: int,
        memory_context: Optional[MemoryContext] = None,
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create connection_ping notification using new contract.
        
        Args:
            user_id: User ID
            memory_context: Optional MemoryContext for personalization
            scheduled_for: Optional scheduled time
        
        Returns:
            Notification if created, None if duplicate or error
        """
        # Get user name
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        
        # Build memory context if not provided
        if memory_context is None:
            memory_context = build_memory_context(self.db, user_id)
        
        # Build payload
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="connection_ping",
            title="سلام",
            body="",  # Will be filled by fallback
            priority="low",
            scheduled_for=scheduled_for,
            metadata=None
        )
        
        # Apply fallback
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=memory_context
        )
        
        # Enhance with AI (safe wrapper)
        payload = enhance_with_ai(payload)
        
        # Persist with dedupe check
        return self.builder.persist(payload, check_dedupe=True, time_window_hours=4)
    
    def create_health_alert(
        self,
        user_id: int,
        alert_code: str,
        alert_reason: Optional[str] = None,
        priority: Literal["low", "normal", "high", "critical"] = "high",
        scheduled_for: Optional[datetime] = None
    ) -> Optional[Notification]:
        """
        Create health_alert notification using new contract.
        
        Args:
            user_id: User ID
            alert_code: Alert code (e.g. "high_heart_rate", "low_spo2")
            alert_reason: Optional alert reason text
            priority: Priority level (default: high)
            scheduled_for: Optional scheduled time
        
        Returns:
            Notification if created, None if duplicate or error
        """
        # Get user name
        user = self.db.query(User).filter(User.id == user_id).first()
        user_name = user.name if user and user.name else None
        
        # Build metadata
        metadata = {
            "alert_code": alert_code,
            "alert_reason": alert_reason
        }
        
        # Build payload
        payload = self.builder.build_payload(
            user_id=user_id,
            notification_type="health_alert",
            title="هشدار سلامت",
            body="",  # Will be filled by fallback
            priority=priority,
            scheduled_for=scheduled_for,
            metadata=metadata
        )
        
        # Apply fallback
        payload = self.builder.apply_fallback(
            payload=payload,
            user_name=user_name,
            memory_context=None  # Health alerts don't need lifestyle context
        )
        
        # Enhance with AI (safe wrapper)
        payload = enhance_with_ai(payload)
        
        # Persist with dedupe check (1 hour window for health alerts)
        return self.builder.persist(payload, check_dedupe=True, time_window_hours=1)
    
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
        
        # Rule 1: Low sleep duration
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6.0:
                return self.builder.create_and_save(
                    user_id=user_id,
                    notification_type="REMINDER",
                    title="Sleep Care Reminder",
                    body=f"You slept {memory_context.sleep_duration_hours:.1f} hours last night. Consider getting more rest for better health.",
                    priority="normal"
                )
        
        # Rule 2: Low hydration
        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                return self.builder.create_and_save(
                    user_id=user_id,
                    notification_type="REMINDER",
                    title="Hydration Reminder",
                    body=f"You've had {memory_context.hydration_ml:.0f}ml of water today. Try to reach at least 1500ml for optimal hydration.",
                    priority="low"
                )
        
        # Rule 3: Inactivity (no activity data available)
        if not memory_context.has_activity_data():
            # Check if user has been inactive for a while (no recent activity data)
            # This is a gentle reminder, not urgent
            return self.builder.create_and_save(
                user_id=user_id,
                notification_type="INSIGHT",
                title="Activity Reminder",
                body="Consider adding some light movement to your day. Even a short walk can boost your energy and mood.",
                priority="low"
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
        
        # Create notification
        return self.builder.create_and_save(
            user_id=user_id,
            notification_type="HEALTH",
            title=title,
            body=body,
            priority=priority
        )
    
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
        
        return self.builder.create_and_save(
            user_id=user_id,
            notification_type="REMINDER",
            title=title,
            body=body,
            priority=priority,
            scheduled_for=scheduled_for
        )
    
    # -------------------- Medication Reminders --------------------
    
    def create_medication_reminder(
        self,
        user_id: int,
        medication_name: str,
        dosage: Optional[str] = None
    ) -> Notification:
        """
        Create a medication reminder notification.
        
        Args:
            user_id: User ID
            medication_name: Name of medication
            dosage: Dosage information (optional)
        
        Returns Notification object.
        """
        title = "Medication Reminder"
        body = f"Time to take {medication_name}"
        if dosage:
            body += f" ({dosage})"
        
        # Medication reminders are high priority
        priority = "high"
        
        # Schedule for next medication time (default: 8 hours)
        interval = self.timing_rules.get_reminder_interval("medication")
        scheduled_for = None
        if interval:
            scheduled_for = datetime.utcnow() + interval
        
        # TODO: RAG integration - enhance with medication-specific information
        # rag_context = self.rag_service.retrieve_medication_context(
        #     medication_name=medication_name,
        #     user_conditions=self.medical_service.get_user_conditions(user_id)
        # )
        # if rag_context:
        #     body += f"\n\nNote: {rag_context}"
        
        return self.builder.create_and_save(
            user_id=user_id,
            notification_type="REMINDER",
            title=title,
            body=body,
            priority=priority,
            scheduled_for=scheduled_for
        )
    
    # -------------------- Insight Notifications --------------------
    
    def create_insight_notification(
        self,
        user_id: int,
        insight_text: str,
        priority: str = "normal"
    ) -> Notification:
        """
        Create an insight notification (health insights, trends, etc.).
        
        Args:
            user_id: User ID
            insight_text: Insight message
            priority: Priority level (default: normal)
        
        Returns Notification object.
        """
        return self.builder.create_and_save(
            user_id=user_id,
            notification_type="INSIGHT",
            title="Health Insight",
            body=insight_text,
            priority=priority
        )
    
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
        
        # Rule 1: Low sleep duration
        if memory_context.has_sleep_data() and memory_context.sleep_duration_hours is not None:
            if memory_context.sleep_duration_hours < 6.0:
                return self.builder.create_and_save(
                    user_id=user_id,
                    notification_type="REMINDER",
                    title="Sleep Care Reminder",
                    body=f"You slept {memory_context.sleep_duration_hours:.1f} hours last night. Consider getting more rest for better health.",
                    priority="normal"
                )
        
        # Rule 2: Low hydration
        if memory_context.has_hydration_data() and memory_context.hydration_ml is not None:
            if memory_context.hydration_ml < 1500:
                return self.builder.create_and_save(
                    user_id=user_id,
                    notification_type="REMINDER",
                    title="Hydration Reminder",
                    body=f"You've had {memory_context.hydration_ml:.0f}ml of water today. Try to reach at least 1500ml for optimal hydration.",
                    priority="low"
                )
        
        # Rule 3: Inactivity (no activity data available)
        if not memory_context.has_activity_data():
            # Check if user has been inactive for a while (no recent activity data)
            # This is a gentle reminder, not urgent
            return self.builder.create_and_save(
                user_id=user_id,
                notification_type="INSIGHT",
                title="Activity Reminder",
                body="Consider adding some light movement to your day. Even a short walk can boost your energy and mood.",
                priority="low"
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