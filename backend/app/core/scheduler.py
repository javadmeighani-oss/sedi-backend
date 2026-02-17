# app/core/scheduler.py
import os
import time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import SchedulerAlreadyRunningError
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import Depends
import pytz
import json

from backend.app.database import get_db
from backend.app.models import User, Notification, Device, UserMedication, Medication
from backend.app.services.notification_engine import DecisionEngine
from backend.app.core.conversation.memory import ConversationMemory
from backend.app.services.memory import MemoryRepository, build_memory_context

# -------------------------------
# Scheduling and Check Settings
# -------------------------------
CHECK_INTERVAL_HOURS = 2       # Health check interval (every 2 hours)
INACTIVE_HOURS = 4             # Inactive threshold (if no interaction for 4+ hours) - UPDATED
MORNING_HOUR = 9               # Default morning greeting time (9 AM) - UPDATED
MORNING_CHECK_INTERVAL_MIN = 10  # Check for morning notifications every 10 minutes
INACTIVITY_CHECK_INTERVAL_MIN = 15  # Check for inactivity every 15 minutes
ENGAGEMENT_NUDGE_INACTIVE_HOURS = 3  # Stage 16.6: engagement nudge if inactive 3h+
ENGAGEMENT_MAX_PER_DAY = int(os.getenv("ENGAGEMENT_MAX_PER_DAY", "3"))  # Stage 16.6.2
ENGAGEMENT_MIN_HOURS = int(os.getenv("ENGAGEMENT_MIN_HOURS", "3"))  # Stage 16.6.2: min hours between nudges
ENGAGEMENT_CHECK_INTERVAL_MIN = 10  # Run engagement nudge check every 10 minutes
DELIVERY_PENDING_INTERVAL_MIN = 5  # Run notification delivery outbox every 5 minutes
# Device disconnected: if last_seen_at older than threshold, create notification (dedupe: once per 6h per device)
DEVICE_DISCONNECTED_THRESHOLD_MIN = int(os.getenv("DEVICE_DISCONNECTED_THRESHOLD_MIN", "15"))
DEVICE_DISCONNECTED_CHECK_INTERVAL_MIN = 15  # Run check every 15 minutes
# Medication reminders: loop over UserMedication, create reminder (dedupe per med per 8h)
MEDICATION_REMINDER_CHECK_INTERVAL_MIN = 15  # Run every 15 minutes

scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Tehran"))

# -------------------------------
# Function: Check inactive users (UPDATED - Phase 9.4)
# -------------------------------
def run_inactivity_notifications():
    """
    Check for inactive users and send notifications.
    Runs every 15 minutes, but only creates notifications if:
    - User hasn't chatted for 4+ hours
    - Not more than 2 inactive_ping notifications per day
    - Not more than once per 4 hours (cooldown)
    """
    with next(get_db()) as db:
        now = datetime.utcnow()
        memory = ConversationMemory(db)
        decision_engine = DecisionEngine(db)
        
        users = db.query(User).all()
        
        for user in users:
            # Get last interaction time
            last_chat_time = memory.get_last_interaction_time(user.id)
            
            if last_chat_time is None:
                # Skip users who have never chatted
                continue
            
            # Check if 4+ hours inactive
            time_since = now - last_chat_time
            if time_since < timedelta(hours=INACTIVE_HOURS):
                continue
            
            # Dedupe: Check if we already sent inactive_ping today (max 2 per day)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Release B2.1: Check for connection_ping type instead of legacy INSIGHT
            today_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "connection_ping",
                    Notification.created_at >= today_start
                )
                .all()
            )
            
            inactive_count = len(today_notifications)
            if inactive_count >= 2:
                continue  # Max 2 per day reached
            
            # Cooldown: Check if we sent one in the last 4 hours
            cooldown_threshold = now - timedelta(hours=INACTIVE_HOURS)
            recent_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "connection_ping",
                    Notification.created_at >= cooldown_threshold
                )
                .all()
            )
            
            if len(recent_notifications) > 0:
                continue  # Cooldown active
            
            # Create inactive ping notification using new contract (Release B - Part B1)
            # Build memory context for personalization
            try:
                memory_context = build_memory_context(db, user.id)
            except Exception as e:
                print(f"[Sedi Scheduler] Failed to build memory context for user {user.id}: {e}")
                memory_context = None
            
            # Use DecisionEngine with new contract
            notif = decision_engine.create_connection_ping(
                user_id=user.id,
                memory_context=memory_context,
                scheduled_for=now
            )
            
            if notif:
                hours_since = int(time_since.total_seconds() / 3600)
                print(f"[Sedi Scheduler] Connection ping created for user {user.id} ({hours_since}h inactive)")
            else:
                print(f"[Sedi Scheduler] Connection ping skipped for user {user.id} (duplicate or error)")

# -------------------------------
# Function: Check daily health status
# -------------------------------
def check_health_status():
    with next(get_db()) as db:
        users = db.query(User).all()
        for user in users:
            # For simple testing, use a fixed health summary
            # Note: Health alerts should be created by health data evaluation, not scheduled checks
            # This function is kept for backward compatibility but does not create notifications
            # to avoid spam. Actual health alerts are created via DecisionEngine.create_health_alert()
            pass

# -------------------------------
# Function: Send morning greeting (UPDATED - Phase 9.4)
# -------------------------------
def run_morning_notifications():
    """
    Check for morning notification time and send notifications.
    Runs every 10 minutes, but only creates notifications when:
    - Current time (in user's timezone) matches user's morning preference (default 9 AM)
    - Only once per calendar day per user (dedupe)
    Stage 16.6: Uses user timezone from UserMemoryFact key "timezone" (e.g. Asia/Tehran); else server default.
    """
    with next(get_db()) as db:
        now = datetime.utcnow()
        memory_repo = MemoryRepository(db)
        decision_engine = DecisionEngine(db)
        memory_context = None  # Will be built per user if needed
        
        users = db.query(User).all()
        
        for user in users:
            # Get user's morning notification time preference
            morning_time_fact = memory_repo.get_fact(
                user_id=user.id,
                domain="preferences",
                key="morning_notification_time"
            )
            
            # Default to 9 AM if no preference
            morning_hour = MORNING_HOUR
            morning_minute = 0
            
            if morning_time_fact:
                try:
                    time_data = json.loads(morning_time_fact.value_json)
                    morning_hour = time_data.get("hour", MORNING_HOUR)
                    morning_minute = time_data.get("minute", 0)
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass  # Use defaults
            
            # Stage 16.6: Resolve user timezone for per-user scheduling
            timezone_fact = memory_repo.get_fact(
                user_id=user.id,
                domain="preferences",
                key="timezone"
            )
            tz_str = "Asia/Tehran"
            if timezone_fact:
                try:
                    tz_data = json.loads(timezone_fact.value_json)
                    tz_str = tz_data.get("tz", "Asia/Tehran") if isinstance(tz_data, dict) else str(tz_data)
                except (json.JSONDecodeError, TypeError):
                    pass
            try:
                user_tz = pytz.timezone(tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                user_tz = pytz.timezone("Asia/Tehran")
            now_local = now.replace(tzinfo=pytz.UTC).astimezone(user_tz)
            
            # Check if current time (in user's timezone) matches morning time (within 10 minute window)
            current_hour = now_local.hour
            current_minute = now_local.minute
            
            if current_hour != morning_hour:
                continue  # Not the right hour
            
            if current_minute < morning_minute or current_minute >= morning_minute + MORNING_CHECK_INTERVAL_MIN:
                continue  # Not within the 10-minute window
            
            # Dedupe: Check if we already sent morning_summary today
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Release B2.1: Check for morning_brief type instead of legacy INSIGHT
            today_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "morning_brief",
                    Notification.created_at >= today_start
                )
                .all()
            )
            
            if len(today_notifications) > 0:
                continue  # Already sent today
            
            # Build memory context for personalized message
            try:
                memory_context = build_memory_context(db, user.id)
            except Exception as e:
                print(f"[Sedi Scheduler] Failed to build memory context for user {user.id}: {e}")
                memory_context = None
            
            # Create morning notification using new contract (Release B - Part B1)
            notif = decision_engine.create_morning_brief(
                user_id=user.id,
                memory_context=memory_context,
                scheduled_for=now
            )
            
            if notif:
                print(f"[Sedi Scheduler] Morning brief created for user {user.id} at {morning_hour}:{morning_minute:02d}")
            else:
                print(f"[Sedi Scheduler] Morning brief skipped for user {user.id} (duplicate or error)")
    
# -------------------------------
# Save notification to database
# -------------------------------
def save_notification(db: Session, user_id: int, message: str, notif_type: str):
    # Use DecisionEngine instead of direct Notification creation
    decision_engine = DecisionEngine(db)
    
    # Map scheduler notification types to DecisionEngine methods
    if notif_type == "morning_summary":
        notif = decision_engine.create_insight_notification(
            user_id=user_id,
            insight_text=message,
            priority="normal"
        )
    elif notif_type == "health_check":
        notif = decision_engine.create_insight_notification(
            user_id=user_id,
            insight_text=message,
            priority="normal"
        )
    elif notif_type == "inactive_ping":
        notif = decision_engine.create_insight_notification(
            user_id=user_id,
            insight_text=message,
            priority="low"
        )
    else:
        # Release B2.1: Use connection_ping type instead of legacy REMINDER
        from backend.app.services.notification_engine import DecisionEngine
        decision_engine = DecisionEngine(db)
        # Use create_insight_notification which maps to connection_ping
        notif = decision_engine.create_insight_notification(
            user_id=user_id,
            insight_text=message,
            priority="normal"
        )
    
    print(f"[Sedi Scheduler] Notification created for user {user_id} → {notif_type}")


# -------------------------------
# Stage 16.6: Engagement nudge (inactive 3h+, max 3/day, dedupe engagement:user_id:date:bucket)
# -------------------------------
def run_engagement_nudge():
    """
    Every 10 min: if user last interaction > 3 hours, enqueue one engagement nudge
    with dedupe_key engagement:{user_id}:{date}:{bucket}. Max 3 per day per user.
    """
    with next(get_db()) as db:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        memory = ConversationMemory(db)
        decision_engine = DecisionEngine(db)
        users = db.query(User).all()
        for user in users:
            last_chat_time = memory.get_last_interaction_time(user.id)
            if last_chat_time is None:
                continue
            if now - last_chat_time < timedelta(hours=ENGAGEMENT_NUDGE_INACTIVE_HOURS):
                continue
            # Stage 16.6.2: Max engagement nudges per day (channel=engagement for indexed query)
            today_engagement = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.channel == "engagement",
                    Notification.created_at >= today_start,
                )
                .count()
            )
            if today_engagement >= ENGAGEMENT_MAX_PER_DAY:
                continue
            # Stage 16.6.2: Min hours since last engagement (anti-spam)
            min_hours_ago = now - timedelta(hours=ENGAGEMENT_MIN_HOURS)
            last_engagement = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.channel == "engagement",
                    Notification.created_at >= min_hours_ago,
                )
                .order_by(Notification.created_at.desc())
                .first()
            )
            if last_engagement:
                continue
            try:
                memory_context = build_memory_context(db, user.id)
            except Exception as e:
                print(f"[Sedi Scheduler] Failed memory context user {user.id}: {e}")
                memory_context = None
            notif = decision_engine.create_engagement_nudge(
                user_id=user.id,
                memory_context=memory_context,
                scheduled_for=now,
            )
            if notif:
                print(f"[Sedi Scheduler] Engagement nudge created for user {user.id}")


# -------------------------------
# Device disconnected: last_seen_at older than threshold -> create notification (dedupe per device)
# -------------------------------
def run_device_disconnected_check():
    """
    For each active device: if now - last_seen_at > THRESHOLD (e.g. 15 min),
    create device_disconnected notification. Dedupe: once per device per 6h (handled in notification_engine).
    """
    with next(get_db()) as db:
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=DEVICE_DISCONNECTED_THRESHOLD_MIN)
        decision_engine = DecisionEngine(db)
        # Active devices that have been seen before but not within threshold
        devices = (
            db.query(Device)
            .filter(
                Device.status == "active",
                Device.last_seen_at.isnot(None),
                Device.last_seen_at < cutoff,
            )
            .all()
        )
        for dev in devices:
            try:
                notif = decision_engine.create_device_disconnected(
                    user_id=dev.user_id,
                    device_id=dev.device_id,
                    scheduled_for=now,
                )
                if notif:
                    print(f"[Sedi Scheduler] device_disconnected created for user={dev.user_id} device_id={dev.device_id}")
            except Exception as e:
                print(f"[Sedi Scheduler] device_disconnected failed user={dev.user_id} device_id={dev.device_id}: {e}")


# -------------------------------
# Medication reminders: for each UserMedication create reminder (dedupe per med per 8h)
# -------------------------------
def run_medication_reminders():
    """
    For each UserMedication (user + medication + interval), create a medication reminder
    if not already sent in the last interval. Dedupe is handled in create_medication_reminder (8h per medication).
    """
    with next(get_db()) as db:
        decision_engine = DecisionEngine(db)
        # All user-medication rows with medication joined
        rows = (
            db.query(UserMedication, Medication)
            .join(Medication, UserMedication.medication_id == Medication.id)
            .all()
        )
        for um, med in rows:
            try:
                result = decision_engine.create_medication_reminder(
                    user_id=um.user_id,
                    medication_name=med.name,
                    dosage=med.default_dosage,
                    medication_id=med.id,
                )
                if result:
                    print(f"[Sedi Scheduler] medication_reminder created user={um.user_id} medication={med.name}")
            except Exception as e:
                print(f"[Sedi Scheduler] medication_reminder failed user={um.user_id} medication_id={med.id}: {e}")


# -------------------------------
# Run notification delivery outbox (mark is_sent)
# -------------------------------
def run_deliver_pending():
    """Query unsent notifications, send via adapter, mark is_sent=true. Idempotent."""
    t0 = time.perf_counter()
    print("[Sedi Scheduler] deliver_pending job start")
    from backend.app.services.notifications.delivery_service import DeliveryService
    with next(get_db()) as db:
        service = DeliveryService(db=db)
        sent_count = service.deliver_pending(limit=100)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    print(f"[Sedi Scheduler] deliver_pending job end duration_ms={duration_ms} sent_count={sent_count}")


# -------------------------------
# Start Scheduler (UPDATED - Phase 9.4)
# -------------------------------
def start_scheduler():
    try:
        if getattr(scheduler, "running", False):
            return
        # Schedule morning notifications check every 10 minutes
        scheduler.add_job(
            run_morning_notifications,
            "interval",
            minutes=MORNING_CHECK_INTERVAL_MIN,
            id="morning_notifications",
            replace_existing=True,
        )

        # Schedule inactivity notifications check every 15 minutes
        scheduler.add_job(
            run_inactivity_notifications,
            "interval",
            minutes=INACTIVITY_CHECK_INTERVAL_MIN,
            id="inactivity_notifications",
            replace_existing=True,
        )

        # Stage 16.6: Engagement nudge every 10 minutes (3h inactive, max 3/day)
        scheduler.add_job(
            run_engagement_nudge,
            "interval",
            minutes=ENGAGEMENT_CHECK_INTERVAL_MIN,
            id="engagement_nudge",
            replace_existing=True,
        )

        # Schedule health status check every 2 hours (keep existing)
        scheduler.add_job(
            check_health_status,
            "interval",
            hours=CHECK_INTERVAL_HOURS,
            id="health_check",
            replace_existing=True,
        )

        # Schedule notification delivery outbox every N minutes
        # V1: max_instances=1 + coalesce + misfire_grace_time prevent overlap warning
        scheduler.add_job(
            run_deliver_pending,
            "interval",
            minutes=DELIVERY_PENDING_INTERVAL_MIN,
            id="deliver_pending",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )

        # Schedule device disconnected check (last_seen_at > threshold -> notify, dedupe per device)
        scheduler.add_job(
            run_device_disconnected_check,
            "interval",
            minutes=DEVICE_DISCONNECTED_CHECK_INTERVAL_MIN,
            id="device_disconnected_check",
            replace_existing=True,
        )

        # Schedule medication reminder loop (UserMedication -> create_medication_reminder, dedupe 8h per med)
        scheduler.add_job(
            run_medication_reminders,
            "interval",
            minutes=MEDICATION_REMINDER_CHECK_INTERVAL_MIN,
            id="medication_reminders",
            replace_existing=True,
        )

        scheduler.start()
        print("[Sedi Scheduler] Background scheduler started successfully ✅")
    except SchedulerAlreadyRunningError:
        return