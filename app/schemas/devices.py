# app/schemas/devices.py
"""
Device Identity Schemas (Release C2)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., description="Logical device id (e.g., Sedi001)")
    device_type: Optional[str] = Field("heart_rate", description="Device type (v1 default: heart_rate)")


class DeviceRegisterResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


class DevicePublicInfo(BaseModel):
    device_id: str
    device_type: str
    status: Literal["active", "revoked"]
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    revoked_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DevicesListResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None

