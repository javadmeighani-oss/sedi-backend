"""I8 operational action API schemas."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class I8GenerateActionRequest(BaseModel):
    request: str = Field(..., min_length=1, max_length=2000)
    domain: Optional[str] = Field(None, description="nutrition|exercise|routine|lifestyle|wellbeing|cross_domain")
    plan_idempotency_key: Optional[str] = Field(None, max_length=128)
    action_idempotency_key: Optional[str] = Field(None, max_length=128)
    persist: bool = True
    health_subject_id: Optional[int] = Field(
        None, description="Target HealthSubject; JWT Account must hold AHSA"
    )


class I8GenerateActionResponse(BaseModel):
    ok: bool = True
    result: dict[str, Any]
