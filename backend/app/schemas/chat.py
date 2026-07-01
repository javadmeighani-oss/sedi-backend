from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: Optional[int] = Field(None, description="Optional; JWT is source of truth when omitted")
    message: str = Field(..., min_length=1, description="User chat message")

