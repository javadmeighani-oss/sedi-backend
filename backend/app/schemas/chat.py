from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: Optional[int] = Field(None, description="Optional; JWT is source of truth when omitted")
    message: str = Field(..., min_length=1, description="User chat message")
    source_notification_id: Optional[int] = Field(
        None, description="Optional; links chat to originating notification"
    )
    conversation_id: Optional[str] = Field(None, max_length=128, description="V2-compatible thread id")
    thread_id: Optional[str] = Field(None, max_length=128, description="V2-compatible thread id")
    interaction_source: Optional[str] = Field(
        None, description="Optional hint: chat, notification, device, or system"
    )

