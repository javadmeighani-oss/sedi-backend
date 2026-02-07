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
from typing import List, Optional
from datetime import datetime
import json

from app.database import get_db
from app.models import Notification, User
from app.schemas import APIResponse, ErrorInfo, NotificationResponse
from app.schemas.notification import NotificationCreate, NotificationFeedbackRequest

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


# ------------------ GET /notifications/unread (Release B2) ------------------
@router.get("/unread", response_model=APIResponse)
def get_unread_notifications(
    user_id: int = Query(..., description="User ID to fetch unread notifications for"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of notifications to return"),
    type: Optional[str] = Query(None, description="Optional filter by notification type"),
    db: Session = Depends(get_db)
):
    """
    Get unread notifications for a user (Release B2).
    
    Returns list of notifications where is_read=false, ordered by created_at descending.
    Supports optional filtering by type and limit.
    """
    # Validate user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="USER_NOT_FOUND", message="User not found.")
        )
    
    # Build query for unread notifications
    query = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .filter(Notification.is_read == False)
    )
    
    # Apply type filter if provided
    if type:
        query = query.filter(Notification.type == type)
    
    # Order by created_at desc and apply limit
    notifications = (
        query
        .order_by(Notification.created_at.desc())
        .limit(limit)
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
        data={
            "notifications": [n.dict() for n in notification_list],
            "count": len(notification_list)
        }
    )


# ------------------ POST /notifications/{notification_id}/mark-read (Release B2) ------------------
@router.post("/{notification_id}/mark-read", response_model=APIResponse)
@router.post("/{notification_id}/read", response_model=APIResponse)  # Backward compatibility alias
def mark_notification_read(
    notification_id: int,
    user_id: int = Query(..., description="User ID (must own the notification)"),
    db: Session = Depends(get_db)
):
    """
    Mark a notification as read (Release B2).
    
    Updates the is_read field to True for the specified notification.
    Validates ownership: notification.user_id must match provided user_id.
    Idempotent: can be called multiple times safely.
    
    Endpoints:
    - POST /notifications/{id}/mark-read (new)
    - POST /notifications/{id}/read (backward compatible)
    """
    # Find notification
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="NOTIFICATION_NOT_FOUND", message="Notification not found.")
        )
    
    # Validate ownership
    if notification.user_id != user_id:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="FORBIDDEN", message="You do not have permission to modify this notification.")
        )
    
    # Mark as read (idempotent - safe to call multiple times)
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    
    # Return success response
    return APIResponse(
        ok=True,
        data={"ok": True, "notification_id": notification_id, "is_read": True}
    )


# ------------------ POST /notifications/{notification_id}/feedback (Release B2) ------------------
@router.post("/{notification_id}/feedback", response_model=APIResponse)
def submit_notification_feedback(
    notification_id: int,
    payload: dict,
    user_id: Optional[int] = Query(None, description="User ID (optional, validated from notification if not provided)"),
    db: Session = Depends(get_db)
):
    """
    Submit standardized feedback for a notification (Release B2).
    
    Request body (new format):
    {
        "feedback": "positive" | "negative" | "neutral",
        "reason": optional string,
        "action": optional string (e.g. "too_early", "too_late", "irrelevant")
    }
    
    For backward compatibility: also accepts old format {"reaction": "like" | "dislike"}
    
    For morning_brief notifications:
    - Stores feedback in UserMemoryFact
    - Adjusts morning_notification_time if many negative feedbacks (>=3 negatives and negatives > positives)
    """
    # Find notification
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="NOTIFICATION_NOT_FOUND", message="Notification not found.")
        )
    
    # Use notification's user_id if user_id not provided
    if user_id is None:
        user_id = notification.user_id
    elif user_id != notification.user_id:
        return APIResponse(
            ok=False,
            error=ErrorInfo(code="FORBIDDEN", message="You do not have permission to provide feedback for this notification.")
        )
    
    # Handle backward compatibility: old format {"reaction": "like" | "dislike"}
    if "reaction" in payload:
        # Convert old format to new format
        reaction = payload.get("reaction")
        if reaction == "like":
            feedback_type = "positive"
        elif reaction == "dislike":
            feedback_type = "negative"
        else:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="INVALID_REACTION", message="Reaction must be 'like' or 'dislike'.")
            )
        feedback_request = NotificationFeedbackRequest(
            feedback=feedback_type,
            reason=payload.get("reason"),
            action=payload.get("action")
        )
    else:
        # New standardized format
        try:
            feedback_request = NotificationFeedbackRequest(**payload)
        except Exception as e:
            return APIResponse(
                ok=False,
                error=ErrorInfo(code="INVALID_FEEDBACK", message=f"Invalid feedback format: {str(e)}")
            )
    
    # Note: Notification model doesn't have metadata field in B2
    # Feedback is stored in UserMemoryFact only
    
    # Check if this is a morning_brief notification
    is_morning_brief = (
        notification.type == "morning_brief" or
        "morning" in notification.body.lower() or 
        (notification.title and "morning" in notification.title.lower())
    )
    
    if is_morning_brief:
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
                positives = feedback_data.get("positives", feedback_data.get("likes", 0))  # Support old format
                negatives = feedback_data.get("negatives", feedback_data.get("dislikes", 0))  # Support old format
            except (json.JSONDecodeError, KeyError, TypeError):
                positives = 0
                negatives = 0
        else:
            positives = 0
            negatives = 0
        
        # Update counters based on new standardized feedback
        if feedback_request.feedback == "positive":
            positives += 1
        elif feedback_request.feedback == "negative":
            negatives += 1
        # "neutral" doesn't affect counters
        
        # Store feedback
        feedback_data = {
            "positives": positives,
            "negatives": negatives,
            "last_feedback_at": datetime.utcnow().isoformat()
        }
        
        try:
            memory_repo.upsert_fact(
                user_id=user_id,
                domain="preferences",
                key="morning_notification_feedback",
                value=feedback_data,
                confidence=0.8,
                source="manual"
            )
        except Exception as e:
            print(f"[Feedback] Error storing feedback fact: {e}")
        
        # Adjust morning time if many negatives (safe, with logging)
        if negatives >= 3 and negatives > positives:
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
                try:
                    memory_repo.upsert_fact(
                        user_id=user_id,
                        domain="preferences",
                        key="morning_notification_time",
                        value={"hour": new_hour, "minute": current_minute},
                        confidence=0.7,
                        source="manual"
                    )
                    print(f"[Feedback] Adjusted morning time for user {user_id} from {current_hour}:{current_minute:02d} to {new_hour}:{current_minute:02d} (reason: {negatives} negative feedbacks)")
                except Exception as e:
                    print(f"[Feedback] Error adjusting morning time for user {user_id}: {e}")
    
    return APIResponse(
        ok=True,
        data={
            "notification_id": notification_id,
            "feedback": feedback_request.feedback,
            "message": "Feedback recorded successfully"
        }
    )


# ------------------ POST /notifications/deliver_pending (admin/dev) ------------------
@router.post("/deliver_pending", response_model=APIResponse)
def deliver_pending_notifications(
    limit: int = Query(100, ge=1, le=500, description="Max number of unsent notifications to process"),
    db: Session = Depends(get_db),
):
    """
    Run the notification delivery pipeline: query unsent (is_sent=false),
    send via configured adapter, mark is_sent=true. Safe to call repeatedly.
    """
    from app.services.notifications.delivery_service import DeliveryService
    service = DeliveryService(db=db)
    sent_count = service.deliver_pending(limit=limit)
    return APIResponse(
        ok=True,
        data={"sent_count": sent_count, "message": f"Marked {sent_count} notification(s) as sent"}
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
