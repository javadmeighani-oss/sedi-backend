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

# Gate 5-D: Raw signal processing (disabled by default via env flag)
_RAW_SIGNAL_PROCESSING_LOCK_KEY = 0x73656472  # 'sedr' in hex

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
        
        from backend.app.services.gate4.feature_flags import gate4_daily_0800_enabled
        from backend.app.services.gate4.scheduler_timing import (
            legacy_should_run_morning_notification,
            should_run_daily_notification_gate4,
        )

        for user in users:
            now_utc = now.replace(tzinfo=pytz.UTC)
            if gate4_daily_0800_enabled():
                if not should_run_daily_notification_gate4(db, user, now_utc):
                    continue
            else:
                if not legacy_should_run_morning_notification(
                    memory_repo, user, now_utc, morning_hour_default=MORNING_HOUR
                ):
                    continue

            # Dedupe: morning_brief only — daily digest has separate I10 occurrence key
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Release B2.1: Check for morning_brief type instead of legacy INSIGHT
            today_morning_notifications = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user.id,
                    Notification.type == "morning_brief",
                    Notification.created_at >= today_start
                )
                .all()
            )
            
            morning_already_sent = len(today_morning_notifications) > 0
            
            if not morning_already_sent:
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
                    print(f"[Sedi Scheduler] Morning brief created for user {user.id}")
                else:
                    print(f"[Sedi Scheduler] Morning brief skipped for user {user.id} (duplicate or error)")

            digest_notif = decision_engine.create_daily_wellness_digest(
                user_id=user.id,
                scheduled_for=now,
            )
            if digest_notif:
                print(f"[Sedi Scheduler] Daily wellness digest created for user {user.id}")
            else:
                print(f"[Sedi Scheduler] Daily wellness digest skipped for user {user.id}")
    
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
# Advisory lock key for device_disconnected (prevents concurrent job overlap)
_DEVICE_DISCONNECTED_LOCK_KEY = 0x73656469  # 'sedi' in hex


def run_device_disconnected_check():
    """
    For each active device: if now - last_seen_at > THRESHOLD (e.g. 15 min),
    create device_disconnected notification. Dedupe: once per device per 6h (handled in notification_engine).
    Uses pg_advisory_lock to prevent duplicate notifications from concurrent runs.
    """
    from sqlalchemy import text
    with next(get_db()) as db:
        # Advisory lock: skip if another instance is already running (prevents duplicates)
        r = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _DEVICE_DISCONNECTED_LOCK_KEY})
        if not (r.scalar() if r else False):
            print("[Sedi Scheduler] device_disconnected skipped: lock held by another run")
            return
        try:
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
        finally:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _DEVICE_DISCONNECTED_LOCK_KEY})
            except Exception as unlock_err:
                print(f"[Sedi Scheduler] device_disconnected advisory unlock warning: {unlock_err}")


# -------------------------------
# Medication reminders: for each UserMedication create reminder (dedupe per med per 8h)
# -------------------------------
def run_medication_reminders():
    """Create medication reminders from saved schedules or legacy 8h fallback."""
    with next(get_db()) as db:
        from backend.app.services.medication_scheduler import process_medication_reminders

        decision_engine = DecisionEngine(db)
        created = process_medication_reminders(db, decision_engine)
        if created:
            print(f"[Sedi Scheduler] medication_reminders created count={created}")


# -------------------------------
# Gate 5-D: Raw signal batch feature extraction (optional, env-gated)
# -------------------------------
def run_raw_signal_processing():
    """
    Process pending raw signal batches up to env max limit.
    No notifications, DecisionEngine, or clinical side effects.
    """
    from sqlalchemy import text

    from backend.app.services.gate5.raw_signal_feature_extraction import (
        process_pending_raw_signal_batches,
    )
    from backend.app.services.gate5.raw_signal_processing_flags import (
        raw_signal_processing_max_limit,
    )

    with next(get_db()) as db:
        r = db.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": _RAW_SIGNAL_PROCESSING_LOCK_KEY},
        )
        if not (r.scalar() if r else False):
            print("[Sedi Scheduler] raw_signal_processing skipped: lock held by another run")
            return
        try:
            t0 = time.perf_counter()
            limit = raw_signal_processing_max_limit()
            summary = process_pending_raw_signal_batches(
                db,
                limit=limit,
                source="scheduler",
                dry_run=False,
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            print(
                "[Sedi Scheduler] raw_signal_processing end "
                f"processed={summary.processed} completed={summary.completed} "
                f"failed={summary.failed} skipped={summary.skipped} "
                f"limit={limit} duration_ms={duration_ms}"
            )
        finally:
            try:
                db.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _RAW_SIGNAL_PROCESSING_LOCK_KEY},
                )
            except Exception as unlock_err:
                print(
                    "[Sedi Scheduler] raw_signal_processing advisory unlock warning: "
                    f"{unlock_err}"
                )


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

        # Gate 3I-A: Optional KB scheduled fetch (disabled by default)
        # Runs only when SEDI_KB_SCHEDULED_FETCH_ENABLED=true. Never auto-publishes.
        try:
            from backend.app.services.gate3.kb_scheduler import scheduled_fetch_enabled, run_scheduled_kb_fetch

            if scheduled_fetch_enabled():
                kb_interval_min = int(os.getenv("SEDI_KB_SCHEDULED_FETCH_INTERVAL_MIN", "60"))
                kb_interval_min = max(5, min(24 * 60, kb_interval_min))

                def _kb_tick():
                    with next(get_db()) as db:
                        run_scheduled_kb_fetch(db)

                scheduler.add_job(
                    _kb_tick,
                    "interval",
                    minutes=kb_interval_min,
                    id="kb_scheduled_fetch",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=60,
                )
                print(f"[Sedi Scheduler] KB scheduled fetch job enabled interval_min={kb_interval_min}")
        except Exception as e:
            # Fail-safe: do not break existing notification scheduler if KB wiring fails.
            print(f"[Sedi Scheduler] KB scheduled fetch wiring failed: {e}")

        # I5-IMPL-W3-P02 / W6-P01: weekly international knowledge crawler.
        # Job is always registered; body no-ops unless both activation env flags
        # are true. Production ticks use the shared governed weekly callable
        # (DB session + governed source load + advisory lock + deterministic window).
        try:
            from backend.app.services.i5.governed_weekly_runtime import (
                next_weekly_calendar_fire,
                run_weekly_scheduled_job,
                weekly_calendar_trigger_kwargs,
            )
            from backend.app.services.i5.weekly_orchestrator import (
                WEEKLY_ORCHESTRATOR_JOB_ID,
                weekly_orchestrator_enabled,
            )

            def _weekly_orchestrator_tick():
                try:
                    outcome = run_weekly_scheduled_job(persist_ledger=True, acquire_lock=True)
                    print(
                        "[Sedi Scheduler] weekly_international_knowledge_crawler "
                        f"outcome={outcome.outcome} activation={weekly_orchestrator_enabled()} "
                        f"network={outcome.network_executed} detail={outcome.detail}",
                        flush=True,
                    )
                except Exception as exc:
                    print(
                        "[Sedi Scheduler] weekly_international_knowledge_crawler "
                        f"outcome=TICK_ERROR activation={weekly_orchestrator_enabled()} "
                        f"network=false detail={type(exc).__name__}",
                        flush=True,
                    )
                    raise

            cron_kwargs = weekly_calendar_trigger_kwargs()
            next_fire = next_weekly_calendar_fire()
            scheduler.add_job(
                _weekly_orchestrator_tick,
                id=WEEKLY_ORCHESTRATOR_JOB_ID,
                replace_existing=True,
                misfire_grace_time=3600,
                **cron_kwargs,
            )
            print(
                "[Sedi Scheduler] weekly_international_knowledge_crawler registered "
                f"trigger=cron day_of_week={cron_kwargs['day_of_week']} "
                f"hour={cron_kwargs['hour']} minute={cron_kwargs['minute']} "
                f"timezone={cron_kwargs['timezone']} "
                f"max_instances={cron_kwargs['max_instances']} "
                f"coalesce={cron_kwargs['coalesce']} "
                f"enabled={weekly_orchestrator_enabled()} "
                f"next_calendar_fire={next_fire.isoformat()} "
                f"first_run_delay_sec=ignored",
                flush=True,
            )
        except Exception as e:
            print(f"[Sedi Scheduler] weekly orchestrator dormant wiring failed: {e}")

        # Section43/48: I7 lifelong period-summary jobs (dormant unless flag on).
        try:
            from backend.app.database import get_db as _i7_get_db
            from backend.app.services.i7.jobs import (
                DAILY_JOB_ID,
                JOB_IDS,
                JOB_TIMEZONE,
                MONTHLY_JOB_ID,
                WEEKLY_JOB_ID,
                YEARLY_JOB_ID,
                format_i7_run_log,
                next_cron_fire,
                period_summary_cron_kwargs,
                period_summary_jobs_enabled,
                run_period_summary_sweep,
            )

            def _i7_summary_tick(summary_type: str):
                job_id = JOB_IDS[summary_type]
                job = scheduler.get_job(job_id)
                next_run = next_cron_fire(summary_type)
                scheduled = ""
                if job is not None and getattr(job, "trigger", None) is not None:
                    scheduled = str(job.trigger)
                if not period_summary_jobs_enabled():
                    with next(_i7_get_db()) as db:
                        result = run_period_summary_sweep(
                            db,
                            summary_type,
                            persist=False,
                            job_id=job_id,
                            scheduled_time=scheduled,
                            next_run_time=next_run,
                        )
                    print(format_i7_run_log(result), flush=True)
                    print(
                        f"[Sedi Scheduler] {summary_type} period summary "
                        "outcome=DORMANT_FLAG_OFF",
                        flush=True,
                    )
                    return
                with next(_i7_get_db()) as db:
                    result = run_period_summary_sweep(
                        db,
                        summary_type,
                        job_id=job_id,
                        scheduled_time=scheduled,
                        next_run_time=next_run,
                    )
                    print(format_i7_run_log(result), flush=True)
                    print(
                        f"[Sedi Scheduler] i7_period_summary_{summary_type.lower()} "
                        f"enabled={result.enabled} users={result.users_seen} "
                        f"rebuilt={result.rebuilt} skipped={result.skipped} "
                        f"failed={result.failed} detail={result.detail}",
                        flush=True,
                    )

            for _kind, _job_id in (
                ("DAILY", DAILY_JOB_ID),
                ("WEEKLY", WEEKLY_JOB_ID),
                ("MONTHLY", MONTHLY_JOB_ID),
                ("YEARLY", YEARLY_JOB_ID),
            ):
                job = scheduler.add_job(
                    _i7_summary_tick,
                    id=_job_id,
                    replace_existing=True,
                    misfire_grace_time=3600,
                    kwargs={"summary_type": _kind},
                    **period_summary_cron_kwargs(_kind),
                )
                nxt = next_cron_fire(_kind)
                print(
                    "I7_JOB_REGISTERED "
                    f"job_id={job.id} trigger=cron timezone={JOB_TIMEZONE} "
                    f"next_run_time={nxt} max_instances=1 coalesce=true "
                    f"misfire_grace_time=3600 period_type={_kind} "
                    f"enabled={period_summary_jobs_enabled()}",
                    flush=True,
                )
            print(
                "[Sedi Scheduler] i7 period summary jobs registered "
                f"enabled={period_summary_jobs_enabled()} "
                "daily=00:10 weekly=Mon 00:20 monthly=1st 00:30 "
                "yearly=Jan1 00:40 timezone=Asia/Tehran",
                flush=True,
            )
        except Exception as e:
            print(f"[Sedi Scheduler] i7 period summary job wiring failed: {e}")

        # Gate 5-D: Optional raw signal processing (disabled by default)
        try:
            from backend.app.services.gate5.raw_signal_processing_flags import (
                raw_signal_processing_enabled,
                raw_signal_processing_interval_minutes,
            )

            if raw_signal_processing_enabled():
                rs_interval_min = raw_signal_processing_interval_minutes()
                scheduler.add_job(
                    run_raw_signal_processing,
                    "interval",
                    minutes=rs_interval_min,
                    id="raw_signal_processing",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=60,
                )
                print(
                    "[Sedi Scheduler] Raw signal processing job enabled "
                    f"interval_min={rs_interval_min}"
                )
            else:
                print("[Sedi Scheduler] Raw signal processing job disabled (default)")
        except Exception as e:
            print(f"[Sedi Scheduler] Raw signal processing wiring failed: {e}")

        # Section 10: Event and lifestyle reminder schedulers (disabled by default)
        try:
            from backend.app.services.section10 import feature_flags as s10_flags
            from backend.app.services.section10.event_reminder_scheduler import process_event_reminders
            from backend.app.services.section10.lifestyle_reminder_scheduler import process_lifestyle_reminders

            if s10_flags.event_reminder_scheduler_enabled() or s10_flags.lifestyle_reminder_scheduler_enabled():

                def _section10_reminder_tick():
                    with next(get_db()) as db:
                        if s10_flags.event_reminder_scheduler_enabled():
                            process_event_reminders(db)
                        if s10_flags.lifestyle_reminder_scheduler_enabled():
                            process_lifestyle_reminders(db)

                scheduler.add_job(
                    _section10_reminder_tick,
                    "interval",
                    minutes=15,
                    id="section10_reminder_schedulers",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=60,
                )
                print("[Sedi Scheduler] Section 10 reminder schedulers wired (flags control execution)")
        except Exception as e:
            print(f"[Sedi Scheduler] Section 10 reminder scheduler wiring failed: {e}")

        try:
            from backend.app.services.section10 import feature_flags as s10_flags
            from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks

            if s10_flags.contextual_followup_enabled():

                def _contextual_followup_tick():
                    with next(get_db()) as db:
                        count = process_due_follow_up_tasks(db)
                        if count:
                            print(f"[Sedi Scheduler] Contextual follow-ups processed: {count}")

                scheduler.add_job(
                    _contextual_followup_tick,
                    "interval",
                    minutes=10,
                    id="i10_contextual_followup_worker",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=60,
                )
                print("[Sedi Scheduler] I10 contextual follow-up worker wired (flag controls execution)")
        except Exception as e:
            print(f"[Sedi Scheduler] I10 contextual follow-up wiring failed: {e}")

        # PD-I8-04B: I8 proactive schedule scan (always registered; body no-ops unless flag ON).
        # Default OFF. Scheduler is trigger producer only — no I8 decision logic here.
        # Cadence is env-configurable (not a hard-coded product cadence).
        try:
            from backend.app.services.i8.feature_flags import (
                I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG,
                i8_proactive_schedule_scan_interval_minutes,
                i8_proactive_schedule_trigger_enabled,
            )
            from backend.app.services.i8.schedule_scan import (
                I8_SCHEDULE_SCAN_JOB_ID,
                run_i8_proactive_schedule_scan_job_with_coaching,
            )

            i8_scan_interval_min = i8_proactive_schedule_scan_interval_minutes()
            scheduler.add_job(
                run_i8_proactive_schedule_scan_job_with_coaching,
                "interval",
                minutes=i8_scan_interval_min,
                id=I8_SCHEDULE_SCAN_JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=60,
            )
            print(
                "[Sedi Scheduler] I8 proactive schedule scan job registered "
                f"id={I8_SCHEDULE_SCAN_JOB_ID} "
                f"interval_min={i8_scan_interval_min} "
                f"flag={I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG} "
                f"enabled={i8_proactive_schedule_trigger_enabled()} "
                "(default OFF; producer-only; fair in-process cursor)"
            )
        except Exception as e:
            print(f"[Sedi Scheduler] I8 proactive schedule scan wiring failed: {e}")

        # I9: aggregation + personal baseline scheduled sweeps (always registered; dormant unless flag ON).
        try:
            from backend.app.database import get_db as _i9_get_db
            from backend.app.services.i9.jobs import (
                BUCKET_KINDS,
                I9_AGGREGATION_BASELINE_JOBS_FLAG,
                JOB_IDS,
                JOB_TIMEZONE,
                aggregation_baseline_cron_kwargs,
                format_i9_run_log,
                i9_aggregation_baseline_jobs_enabled,
                next_cron_fire,
                run_aggregation_baseline_sweep,
            )

            def _i9_agg_baseline_tick(bucket_kind: str):
                job_id = JOB_IDS[bucket_kind]
                job = scheduler.get_job(job_id)
                scheduled = ""
                if job is not None and getattr(job, "trigger", None) is not None:
                    scheduled = str(job.trigger)
                nxt = next_cron_fire(bucket_kind)
                persist = i9_aggregation_baseline_jobs_enabled()
                with next(_i9_get_db()) as db:
                    result = run_aggregation_baseline_sweep(
                        db,
                        bucket_kind,
                        persist=persist,
                        job_id=job_id,
                        scheduled_time=scheduled,
                        next_run_time=nxt,
                    )
                print(format_i9_run_log(result), flush=True)
                print(
                    f"[Sedi Scheduler] i9_aggregation_baseline_{bucket_kind} "
                    f"enabled={result.enabled} status={result.status} "
                    f"subjects={result.subjects_processed}/{result.subjects_eligible} "
                    f"lock_acquired={result.lock_acquired} detail={result.detail}",
                    flush=True,
                )

            for _kind in BUCKET_KINDS:
                job = scheduler.add_job(
                    _i9_agg_baseline_tick,
                    id=JOB_IDS[_kind],
                    replace_existing=True,
                    misfire_grace_time=3600,
                    kwargs={"bucket_kind": _kind},
                    **aggregation_baseline_cron_kwargs(_kind),
                )
                nxt = next_cron_fire(_kind)
                print(
                    "I9_JOB_REGISTERED "
                    f"job_id={job.id} trigger=cron timezone={JOB_TIMEZONE} "
                    f"next_run_time={nxt} max_instances=1 coalesce=true "
                    f"misfire_grace_time=3600 bucket_kind={_kind} "
                    f"flag={I9_AGGREGATION_BASELINE_JOBS_FLAG} "
                    f"enabled={i9_aggregation_baseline_jobs_enabled()}",
                    flush=True,
                )
            print(
                "[Sedi Scheduler] i9 aggregation/baseline jobs registered "
                f"enabled={i9_aggregation_baseline_jobs_enabled()} "
                "daily=01:10 weekly=Mon 01:20 calendar_month=1st 01:30 "
                "yearly=Jan1 01:40 timezone=Asia/Tehran",
                flush=True,
            )
        except Exception as e:
            print(f"[Sedi Scheduler] i9 aggregation/baseline job wiring failed: {e}")

        try:
            from backend.app.database import get_db as _i10_care_get_db
            from backend.app.services.i10.caregiver_delivery_worker import process_pending_caregiver_delivery_intents
            from backend.app.services.section10.feature_flags import i10_care_network_delivery_enabled

            def _i10_caregiver_delivery_tick():
                with next(_i10_care_get_db()) as db:
                    summary = process_pending_caregiver_delivery_intents(db, limit=50)
                print(f"[Sedi Scheduler] i10_caregiver_delivery summary={summary}", flush=True)

            i10_interval = int(os.getenv("SEDI_I10_CARE_NETWORK_DELIVERY_INTERVAL_MIN", "15"))
            scheduler.add_job(
                _i10_caregiver_delivery_tick,
                "interval",
                minutes=max(5, i10_interval),
                id="i10_caregiver_delivery_worker",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
            print(
                "[Sedi Scheduler] I10 caregiver delivery worker registered "
                f"enabled={i10_care_network_delivery_enabled()} "
                f"flag=SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED "
                f"interval_min={max(5, i10_interval)}",
                flush=True,
            )
        except Exception as e:
            print(f"[Sedi Scheduler] I10 caregiver delivery worker wiring failed: {e}")

        try:
            from backend.app.database import get_db as _i10_digest_get_db
            from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_scan
            from backend.app.services.section10.feature_flags import i10_care_digest_producer_enabled

            def _i10_care_digest_producer_tick():
                with next(_i10_digest_get_db()) as db:
                    summary = run_care_digest_producer_scan(db, deliver=False, limit=100)
                print(f"[Sedi Scheduler] i10_care_digest_producer summary={summary}", flush=True)

            digest_interval = int(os.getenv("SEDI_I10_CARE_DIGEST_PRODUCER_INTERVAL_MIN", "60"))
            scheduler.add_job(
                _i10_care_digest_producer_tick,
                "interval",
                minutes=max(15, digest_interval),
                id="i10_care_digest_producer",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            print(
                "[Sedi Scheduler] I10 care digest producer registered "
                f"enabled={i10_care_digest_producer_enabled()} "
                f"flag=SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED "
                f"interval_min={max(15, digest_interval)}",
                flush=True,
            )
        except Exception as e:
            print(f"[Sedi Scheduler] I10 care digest producer wiring failed: {e}")

        try:
            from backend.app.database import get_db as _i10_care_action_get_db
            from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_scan
            from backend.app.services.section10.feature_flags import i10_care_action_producer_enabled

            def _i10_care_action_producer_tick():
                with next(_i10_care_action_get_db()) as db:
                    summary = run_care_action_producer_scan(db, deliver=False, limit=100)
                print(f"[Sedi Scheduler] i10_care_action_producer summary={summary}", flush=True)

            action_interval = int(os.getenv("SEDI_I10_CARE_ACTION_PRODUCER_INTERVAL_MIN", "60"))
            scheduler.add_job(
                _i10_care_action_producer_tick,
                "interval",
                minutes=max(15, action_interval),
                id="i10_care_action_producer",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=600,
            )
            print(
                "[Sedi Scheduler] I10 care action producer registered "
                f"enabled={i10_care_action_producer_enabled()} "
                f"flag=SEDI_I10_CARE_ACTION_PRODUCER_ENABLED "
                f"interval_min={max(15, action_interval)}",
                flush=True,
            )
        except Exception as e:
            print(f"[Sedi Scheduler] I10 care action producer wiring failed: {e}")

        scheduler.start()
        print("[Sedi Scheduler] Background scheduler started successfully ✅")
    except SchedulerAlreadyRunningError:
        # Idempotent: already running (e.g. under pytest or double-import), skip
        return