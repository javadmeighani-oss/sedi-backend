# app/schemas/common.py
from pydantic import BaseModel
from typing import Optional, Any

class ErrorInfo(BaseModel):
    code: Optional[str] = None
    message: str


class APIResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[ErrorInfo] = None
