# app/core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import Depends
import pytz

from app.database import get_db
from app.models import User, Notification
from app.core.ai_text_engine import (
    generate_notification_text,
    NOTIF_TYPE_MORNING,
    NOTIF_TYPE_HEALTH_CHECK,
    NOTIF_TYPE_INACTIVE,
)

# -------------------------------
# تنظیمات زمان‌بندی و بررسی‌ها
# -------------------------------
CHECK_INTERVAL_HOURS = 2       # بررسی هر ۲ ساعت
INACTIVE_HOURS = 3             # اگر بیش از ۳ ساعت تعامل نداشت
MORNING_HOUR = 8               # ارسال پیام صبحگاهی ساعت ۸ صبح

scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Tehran"))

# -------------------------------
# تابع: بررسی کاربران غیرفعال
# -------------------------------
def check_inactive_users():
    with next(get_db()) as db:
        from app.models import Memory
        now = datetime.utcnow()
        threshold = now - timedelta(hours=INACTIVE_HOURS)

        # Find users who haven't interacted recently (based on Memory table)
        users = db.query(User).all()
        inactive_users = []
        
        for user in users:
            last_memory = db.query(Memory).filter(
                Memory.user_id == user.id
            ).order_by(Memory.created_at.desc()).first()
            
            if not last_memory or last_memory.created_at < threshold:
                inactive_users.append(user)

        for user in inactive_users:
            hours_since = INACTIVE_HOURS
            if user.id in [u.id for u in inactive_users]:
                last_mem = db.query(Memory).filter(
                    Memory.user_id == user.id
                ).order_by(Memory.created_at.desc()).first()
                if last_mem:
                    hours_since = int((now - last_mem.created_at).total_seconds() / 3600)
            
            message = generate_notification_text(
                language=user.preferred_language or "en",
                notification_type=NOTIF_TYPE_INACTIVE,
                user_name=user.name or "my friend",
                hours_since_last_talk=hours_since,
            )
            save_notification(db, user.id, message, "inactive_ping")

# -------------------------------
# تابع: بررسی وضعیت سلامت روزانه
# -------------------------------
def check_health_status():
    with next(get_db()) as db:
        users = db.query(User).all()
        for user in users:
            # برای تست ساده، از خلاصه سلامت ثابت استفاده می‌کنیم
            health_summary = "Your heart rate and temperature are within normal range."

            message = generate_notification_text(
                language=user.preferred_language or "en",
                notification_type=NOTIF_TYPE_HEALTH_CHECK,
                user_name=user.name or "my friend",
                health_summary=health_summary,
            )
            save_notification(db, user.id, message, "health_check")

# -------------------------------
# تابع: پیام صبحگاهی
# -------------------------------
def send_morning_greeting():
    with next(get_db()) as db:
        users = db.query(User).all()
        for user in users:
            health_summary = "You seem to be doing fine. Ready for a new day!"
            message = generate_notification_text(
                language=user.preferred_language or "en",
                notification_type=NOTIF_TYPE_MORNING,
                user_name=user.name or "my friend",
                health_summary=health_summary,
            )
            save_notification(db, user.id, message, "morning_summary")
    
# -------------------------------
# ذخیره نوتیف در پایگاه داده
# -------------------------------
def save_notification(db: Session, user_id: int, message: str, notif_type: str):
    new_notif = Notification(
        user_id=user_id,
        type=notif_type,
        priority="normal",
        message=message,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(new_notif)
    db.commit()
    print(f"[Sedi Scheduler] Notification created for user {user_id} → {notif_type}")

# -------------------------------
# راه‌اندازی Scheduler
# -------------------------------
def start_scheduler():
    print("[Sedi Scheduler] Background scheduler started successfully ✅")

    # اجرای پیام صبحگاهی هر روز ساعت ۸ صبح
    scheduler.add_job(
        send_morning_greeting,
        "cron",
        hour=MORNING_HOUR,
        minute=0,
        id="morning_greeting",
        replace_existing=True,
    )

    # بررسی وضعیت سلامت هر ۲ ساعت
    scheduler.add_job(
        check_health_status,
        "interval",
        hours=CHECK_INTERVAL_HOURS,
        id="health_check",
        replace_existing=True,
    )

    # بررسی کاربران غیرفعال هر ۳ ساعت
    scheduler.add_job(
        check_inactive_users,
        "interval",
        hours=INACTIVE_HOURS,
        id="inactive_check",
        replace_existing=True,
    )
    

    scheduler.start()