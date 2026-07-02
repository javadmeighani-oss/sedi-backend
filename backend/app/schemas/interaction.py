# app/schemas/interaction.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class InteractionResponse(BaseModel):
    message: str
    language: str
    user_id: Optional[int] = None
    timestamp: datetime
    requires_security_check: Optional[bool] = False  # Flag for suspicious behavior detection
    detected_name: Optional[str] = None  # Name detected from conversation (to update frontend)
    continued_from_notification: Optional[bool] = None
    source_notification_id: Optional[int] = None
    conversation_id: Optional[str] = None
