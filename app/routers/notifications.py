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


# ------------------ POST /notifications/{notification_id}/feedback ------------------
@router.post("/{notification_id}/feedback", response_model=APIResponse)
def submit_notification_feedback(
    notification_id: int,
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Submit feedback (like/dislike) for a notification.
    
    Body: {"reaction": "like"} or {"reaction": "dislike"}
    
    For morning_summary notifications:
    - Stores feedback in UserMemoryFact (domain="preferences", key="morning_notification_feedback")
    - Adjusts morning_notification_time if many dislikes (>=3 dislikes and dislikes > likes)
    """
    # Find notification
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="NOTIFICATION_NOT_FOUND", message="Notification not found.")
        )
    
    reaction = payload.get("reaction")
    if reaction not in ["like", "dislike"]:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="INVALID_REACTION", message="Reaction must be 'like' or 'dislike'.")
        )
    
    # Check if this is a morning_summary notification (check body for morning keywords)
    is_morning_summary = (
        "morning" in notification.body.lower() or 
        "day" in notification.body.lower() or
        notification.title and ("morning" in notification.title.lower() or "day" in notification.title.lower())
    )
    
    if is_morning_summary:
        # Handle morning_summary feedback
        from app.services.memory import MemoryRepository
        import json
        
        memory_repo = MemoryRepository(db)
        
        # Get existing feedback fact
        feedback_fact = memory_repo.get_fact(
            user_id=notification.user_id,
            domain="preferences",
            key="morning_notification_feedback"
        )
        
        # Initialize or update feedback counters
        if feedback_fact:
            try:
                feedback_data = json.loads(feedback_fact.value_json)
                likes = feedback_data.get("likes", 0)
                dislikes = feedback_data.get("dislikes", 0)
            except (json.JSONDecodeError, KeyError, TypeError):
                likes = 0
                dislikes = 0
        else:
            likes = 0
            dislikes = 0
        
        # Update counters
        if reaction == "like":
            likes += 1
        else:
            dislikes += 1
        
        # Store feedback
        feedback_data = {
            "likes": likes,
            "dislikes": dislikes,
            "last_feedback_at": datetime.utcnow().isoformat()
        }
        
        memory_repo.upsert_fact(
            user_id=notification.user_id,
            domain="preferences",
            key="morning_notification_feedback",
            value=feedback_data,
            confidence=0.8,
            source="manual"
        )
        
        # Adjust morning time if many dislikes
        if dislikes >= 3 and dislikes > likes:
            # Get current morning time
            morning_time_fact = memory_repo.get_fact(
                user_id=notification.user_id,
                domain="preferences",
                key="morning_notification_time"
            )
            
            current_hour = 9  # Default
            current_minute = 0
            
            if morning_time_fact:
                try:
                    time_data = json.loads(morning_time_fact.value_json)
                    current_hour = time_data.get("hour", 9)
                    current_minute = time_data.get("minute", 0)
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
            
            # Shift +1 hour (cap between 6 and 11)
            new_hour = min(current_hour + 1, 11)
            if new_hour < 6:
                new_hour = 6
            
            if new_hour != current_hour:
                memory_repo.upsert_fact(
                    user_id=notification.user_id,
                    domain="preferences",
                    key="morning_notification_time",
                    value={"hour": new_hour, "minute": current_minute},
                    confidence=0.7,
                    source="manual"
                )
                print(f"[Feedback] Adjusted morning time for user {notification.user_id} to {new_hour}:{current_minute:02d}")
    
    return APIResponse(
        ok=True,
        data={
            "notification_id": notification_id,
            "reaction": reaction,
            "message": "Feedback recorded successfully"
        }
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
