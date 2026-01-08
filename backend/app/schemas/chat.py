from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    user_id: int = Field(..., description="Unique ID of the user")
    message: str = Field(..., min_length=1, description="User chat message")

