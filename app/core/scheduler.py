# app/core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import Depends
import pytz
import json

from app.database import get_db
from app.models import User, Notification
from app.core.ai_text_engine import (
    generate_notification_text,
    NOTIF_TYPE_MORNING,
    NOTIF_TYPE_HEALTH_CHECK,
    NOTIF_TYPE_INACTIVE,
)
from app.services.notification_engine import DecisionEngine
from app.core.conversation.memory import ConversationMemory
from app.services.memory import MemoryRepository, build_memory_context

# -------------------------------
# Scheduling and Check Settings
# -------------------------------
CHECK_INTERVAL_HOURS = 2       # Health check interval (every 2 hours)
INACTIVE_HOURS = 4             # Inactive threshold (if no interaction for 4+ hours) - UPDATED
MORNING_HOUR = 9               # Default morning greeting time (9 AM) - UPDATED
MORNING_CHECK_INTERVAL_MIN = 10  # Check for morning notifications every 10 minutes
INACTIVITY_CHECK_INTERVAL_MIN = 15  # Check for inactivity every 15 minutes

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
            today_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "INSIGHT",
                    Notification.created_at >= today_start
                )
                .all()
            )
            
            # Count inactive pings by checking title or body content
            inactive_count = 0
            for notif in today_notifications:
                is_inactive = False
                if notif.title and "inactive" in notif.title.lower():
                    is_inactive = True
                elif notif.body and ("inactive" in notif.body.lower() or "haven't" in notif.body.lower() or "haven" in notif.body.lower()):
                    is_inactive = True
                if is_inactive:
                    inactive_count += 1
            
            if inactive_count >= 2:
                continue  # Max 2 per day reached
            
            # Cooldown: Check if we sent one in the last 4 hours
            cooldown_threshold = now - timedelta(hours=INACTIVE_HOURS)
            recent_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "INSIGHT",
                    Notification.created_at >= cooldown_threshold
                )
                .all()
            )
            
            # Check if any recent notification is an inactive ping
            has_recent_inactive = False
            for recent_notif in recent_notifications:
                is_inactive = False
                if recent_notif.title and "inactive" in recent_notif.title.lower():
                    is_inactive = True
                elif recent_notif.body and ("inactive" in recent_notif.body.lower() or "haven't" in recent_notif.body.lower() or "haven" in recent_notif.body.lower()):
                    is_inactive = True
                if is_inactive:
                    has_recent_inactive = True
                    break
            
            if has_recent_inactive:
                continue  # Cooldown active
            
            # Create inactive ping notification
            hours_since = int(time_since.total_seconds() / 3600)
            message = generate_notification_text(
                language=user.preferred_language or "en",
                notification_type=NOTIF_TYPE_INACTIVE,
                user_name="my friend",
                hours_since_last_talk=hours_since,
            )
            
            # Use DecisionEngine to create notification with title for tracking
            from app.services.notification_engine import NotificationBuilder
            builder = NotificationBuilder(db)
            notif = builder.create_and_save(
                user_id=user.id,
                notification_type="INSIGHT",
                title="Inactivity Reminder",
                body=message,
                priority="low"
            )
            
            print(f"[Sedi Scheduler] Inactive ping created for user {user.id} ({hours_since}h inactive)")

# -------------------------------
# Function: Check daily health status
# -------------------------------
def check_health_status():
    with next(get_db()) as db:
        users = db.query(User).all()
        for user in users:
            # For simple testing, use a fixed health summary
            health_summary = "Your heart rate and temperature are within normal range."

            message = generate_notification_text(
                language=user.preferred_language or "en",
                notification_type=NOTIF_TYPE_HEALTH_CHECK,
                user_name="my friend",  # Name no longer stored in database
                health_summary=health_summary,
            )
            save_notification(db, user.id, message, "health_check")

# -------------------------------
# Function: Send morning greeting (UPDATED - Phase 9.4)
# -------------------------------
def run_morning_notifications():
    """
    Check for morning notification time and send notifications.
    Runs every 10 minutes, but only creates notifications when:
    - Current time matches user's morning preference (default 9 AM)
    - Only once per calendar day per user (dedupe)
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
            
            # Check if current time matches morning time (within 10 minute window)
            current_hour = now.hour
            current_minute = now.minute
            
            if current_hour != morning_hour:
                continue  # Not the right hour
            
            if current_minute < morning_minute or current_minute >= morning_minute + MORNING_CHECK_INTERVAL_MIN:
                continue  # Not within the 10-minute window
            
            # Dedupe: Check if we already sent morning_summary today
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "INSIGHT",
                    Notification.created_at >= today_start
                )
                .all()
            )
            
            # Check if any notification today is a morning summary
            has_morning_today = False
            for notif in today_notifications:
                is_morning = False
                if notif.title and ("morning" in notif.title.lower() or "day" in notif.title.lower()):
                    is_morning = True
                elif notif.body and ("morning" in notif.body.lower() or ("day" in notif.body.lower() and "ready" in notif.body.lower())):
                    is_morning = True
                if is_morning:
                    has_morning_today = True
                    break
            
            if has_morning_today:
                continue  # Already sent today
            
            # Build memory context for personalized message
            try:
                memory_context = build_memory_context(db, user.id)
            except Exception as e:
                print(f"[Sedi Scheduler] Failed to build memory context for user {user.id}: {e}")
                memory_context = None
            
            # Generate morning message
            health_summary = "You seem to be doing fine. Ready for a new day!"
            if memory_context and memory_context.has_sleep_data():
                # Personalize based on sleep data
                if memory_context.sleep_duration_hours and memory_context.sleep_duration_hours < 6:
                    health_summary = "Hope you get better rest tonight. Ready for a new day!"
            
            message = generate_notification_text(
                language=user.preferred_language or "en",
                notification_type=NOTIF_TYPE_MORNING,
                user_name="my friend",
                health_summary=health_summary,
            )
            
            # Use DecisionEngine to create notification with title for tracking
            from app.services.notification_engine import NotificationBuilder
            builder = NotificationBuilder(db)
            notif = builder.create_and_save(
                user_id=user.id,
                notification_type="INSIGHT",
                title="Morning Summary",
                body=message,
                priority="normal"
            )
            
            print(f"[Sedi Scheduler] Morning summary created for user {user.id} at {morning_hour}:{morning_minute:02d}")
    
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
        # Fallback for unknown types
        from app.services.notification_engine import NotificationBuilder
        builder = NotificationBuilder(db)
        notif = builder.create_and_save(
            user_id=user_id,
            notification_type="REMINDER",
            title=None,
            body=message,
            priority="normal"
        )
    
    print(f"[Sedi Scheduler] Notification created for user {user_id} → {notif_type}")

# -------------------------------
# Start Scheduler (UPDATED - Phase 9.4)
# -------------------------------
def start_scheduler():
    print("[Sedi Scheduler] Background scheduler started successfully ✅")

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

    # Schedule health status check every 2 hours (keep existing)
    scheduler.add_job(
        check_health_status,
        "interval",
        hours=CHECK_INTERVAL_HOURS,
        id="health_check",
        replace_existing=True,
    )
    

    scheduler.start()