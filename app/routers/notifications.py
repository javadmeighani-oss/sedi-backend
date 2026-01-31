# app/routers/notifications.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import json
from app.database import get_db
from app import models
from app.schemas import APIResponse, ErrorInfo, NotificationResponse, NotificationFeedback, Action, NotificationMetadata

router = APIRouter()


# ------------------ دریافت لیست نوتیف‌ها (Contract Section 7) ------------------
@router.get("", response_model=APIResponse)  # Empty string to match /notifications (no trailing slash)
@router.get("/", response_model=APIResponse)  # Also match /notifications/ (with trailing slash)
def get_notifications(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Contract-compliant GET /notifications endpoint
    Returns notifications matching contract structure
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    # Get total count
    total = db.query(models.Notification).filter(models.Notification.user_id == user_id).count()
    unread_count = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.is_read == False
    ).count()

    # Get notifications with pagination
    notifs = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user_id)
        .order_by(models.Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Convert to contract-compliant format
    notifications = [NotificationResponse.from_orm(n).dict() for n in notifs]

    return APIResponse(
        ok=True,
        data={
            "notifications": notifications,
            "total": total,
            "unread_count": unread_count
        }
    )


# ------------------ ساخت نوتیف جدید (Structure Only - No Intelligence) ------------------
@router.post("/create", response_model=APIResponse)
def create_notification(
    user_id: int,
    type: str = "info",
    priority: str = "normal",
    title: Optional[str] = None,
    message: str = "",
    actions: Optional[str] = None,  # JSON string
    metadata: Optional[str] = None,  # JSON string
    db: Session = Depends(get_db)
):
    """
    Create notification (structure only, no intelligence)
    Contract-compliant notification creation
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return APIResponse(ok=False, error=ErrorInfo(code="USER_NOT_FOUND", message="User not found."))

    # Validate type and priority enums
    valid_types = ["info", "alert", "reminder", "check_in", "achievement"]
    valid_priorities = ["low", "normal", "high", "urgent"]
    
    if type not in valid_types:
        type = "info"
    if priority not in valid_priorities:
        priority = "normal"

    # Create notification with contract fields
    notif = models.Notification(
        user_id=user.id,
        type=type,
        priority=priority,
        title=title,
        message=message,
        actions=actions,  # Store as JSON string
        metadata_json=metadata,  # Store as JSON string
        is_read=False,
        created_at=datetime.utcnow(),
    )

    db.add(notif)
    db.commit()
    db.refresh(notif)

    # Return contract-compliant response
    return APIResponse(ok=True, data=NotificationResponse.from_orm(notif).dict())


# ------------------ ثبت واکنش کاربر (Contract Section 5) ------------------
@router.post("/feedback", response_model=APIResponse)
def submit_feedback(feedback: NotificationFeedback, db: Session = Depends(get_db)):
    """
    Contract-compliant feedback endpoint
    Accepts feedback payload exactly as defined in contract
    """
    # Convert notification_id string to int for database lookup
    try:
        notification_id = int(feedback.notification_id)
    except ValueError:
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_ID", message="Invalid notification ID."))

    notif = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not notif:
        return APIResponse(ok=False, error=ErrorInfo(code="NOT_FOUND", message="Notification not found."))

    # Validate reaction enum
    valid_reactions = ["seen", "interact", "dismiss", "like", "dislike"]
    if feedback.reaction not in valid_reactions:
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_REACTION", message="Invalid reaction type."))

    # Handle reactions (structure only, no intelligence)
    if feedback.reaction == "seen":
        notif.is_read = True
        db.commit()
        return APIResponse(ok=True, data={
            "feedback_received": True,
            "message": "Feedback recorded"
        })

    elif feedback.reaction == "interact":
        # action_id required for interact
        if not feedback.action_id:
            return APIResponse(ok=False, error=ErrorInfo(code="MISSING_ACTION_ID", message="action_id required for interact reaction."))
        # Mark as read when interacted
        notif.is_read = True
        db.commit()
        return APIResponse(ok=True, data={
            "feedback_received": True,
            "message": "Feedback recorded"
        })

    elif feedback.reaction == "dismiss":
        notif.is_read = True
        db.commit()
        return APIResponse(ok=True, data={
            "feedback_received": True,
            "message": "Feedback recorded"
        })

    elif feedback.reaction == "like":
        # Store feedback (structure only)
        # Future: personality layer can use this
        db.commit()
        return APIResponse(ok=True, data={
            "feedback_received": True,
            "message": "Feedback recorded"
        })

    elif feedback.reaction == "dislike":
        # Store feedback (structure only)
        # Future: personality layer can use feedback_text
        db.commit()
        return APIResponse(ok=True, data={
            "feedback_received": True,
            "message": "Feedback recorded"
        })

    return APIResponse(ok=False, error=ErrorInfo(code="UNKNOWN_ERROR", message="Unknown error occurred."))
