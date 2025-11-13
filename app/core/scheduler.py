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
        now = datetime.utcnow()
        threshold = now - timedelta(hours=INACTIVE_HOURS)

        inactive_users = db.query(User).filter(
            User.last_interaction < threshold
        ).all()

        for user in inactive_users:
            message = generate_notification_text(
                language=user.language or "en",
                notification_type=NOTIF_TYPE_INACTIVE,
                user_name=user.name or "my friend",
                hours_since_last_talk=INACTIVE_HOURS,
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
                language=user.language or "en",
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
                language=user.language or "en",
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
        message=message,
        type=notif_type,
        timestamp=datetime.utcnow(),
        status="unread",
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