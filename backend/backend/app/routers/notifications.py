# app/routers/notifications.py
"""
Notification Router - Backend API for Notification System

Supports:
- Medication reminders
- Condition-based (disease-aware) care notifications
- Future scheduler integration (scheduled_for field is queryable)
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database import get_db
from app.models import Notification, User
from app.schemas import APIResponse, ErrorInfo, NotificationResponse
from app.schemas.notification import NotificationCreate

router = APIRouter()


# ------------------ GET /notifications?user_id={id} ------------------
@router.get("", response_model=APIResponse)
@router.get("/", response_model=APIResponse)
def get_notifications(
    user_id: int = Query(..., description="User ID to fetch notifications for"),
    db: Session = Depends(get_db)
):
    """
    Get all notifications for a user, ordered by created_at descending.
    
    Returns a list of notifications for the specified user_id.
    """
    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    # Query notifications ordered by created_at desc
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    
    # Convert to response format
    notification_list = [
        NotificationResponse(
            id=notif.id,
            user_id=notif.user_id,
            type=notif.type,
            title=notif.title,
            body=notif.body,
            priority=notif.priority,
            is_read=notif.is_read,
            is_sent=notif.is_sent,
            scheduled_for=notif.scheduled_for,
            created_at=notif.created_at
        )
        for notif in notifications
    ]
    
    return APIResponse(
        ok=True,
        data={"notifications": [n.dict() for n in notification_list]}
    )


# ------------------ POST /notifications/{notification_id}/read ------------------
@router.post("/{notification_id}/read", response_model=APIResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db)
):
    """
    Mark a notification as read.
    
    Updates the is_read field to True for the specified notification.
    """
    # Find notification
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="NOTIFICATION_NOT_FOUND", message="Notification not found.")
        )
    
    # Mark as read
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    
    # Return updated notification
    notification_response = NotificationResponse(
        id=notification.id,
        user_id=notification.user_id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        priority=notification.priority,
        is_read=notification.is_read,
        is_sent=notification.is_sent,
        scheduled_for=notification.scheduled_for,
        created_at=notification.created_at
    )
    
    return APIResponse(
        ok=True,
        data=notification_response.dict()
    )


# ==================== SCHEDULER INTEGRATION READINESS ====================
# TODO: Future scheduler integration will query notifications with:
#   - scheduled_for <= current_time
#   - is_sent = False
#   - Then mark is_sent = True after sending
#
# Example query for scheduler:
#   scheduled_notifications = db.query(Notification).filter(
#       Notification.scheduled_for <= datetime.utcnow(),
#       Notification.is_sent == False
#   ).all()
#
# This allows the scheduler to:
#   - Find notifications ready to be sent
#   - Send them (via push notification, SMS, etc.)
#   - Mark them as sent to prevent duplicate sends
# =========================================================================
