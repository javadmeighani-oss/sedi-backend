# app/schemas/device.py
"""
Device Ingestion Schemas (Release C1)
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime


class DeviceIngestRequest(BaseModel):
    """Request schema for device event ingestion"""
    user_id: int = Field(..., description="User ID")
    device_id: Optional[str] = Field(None, description="Device identifier (optional for v0)")
    event_type: Literal["heart_rate", "blood_pressure", "glucose", "temperature"] = Field(
        ..., description="Event type (multi-vital ready)"
    )
    payload: Dict[str, Any] = Field(..., description="Event payload (must not be empty)")
    recorded_at: Optional[datetime] = Field(None, description="Timestamp from device (optional)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "device_id": "Sedi001",
                "event_type": "heart_rate",
                "payload": {
                    "bpm": 82,
                    "quality": "good"
                },
                "recorded_at": "2026-02-02T10:30:00Z"
            }
        }
    )


class DeviceHeartbeatRequest(BaseModel):
    """Firmware heartbeat payload (device identity from X-DEVICE-TOKEN)."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Logical device id")
    status: Optional[str] = Field(None, description="Optional device status")
    battery: Optional[float] = Field(None, description="Optional battery level")
    temperature: Optional[float] = Field(None, description="Optional device temperature")


class DeviceAcknowledgeRequest(BaseModel):
    """Firmware command acknowledge payload (device identity from X-DEVICE-TOKEN)."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Logical device id")
    sound_id: Optional[str] = Field(None, description="Sound/command identifier")
    status: Optional[str] = Field(None, description="Playback status")


class DeviceIngestResponse(BaseModel):
    """Response schema for device event ingestion"""
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ok": True,
                "data": {
                    "event_id": 123,
                    "dedupe_key": "heart_rate:1:2026-02-02T10:30",
                    "device_event_dedupe_hit": False,
                    "decision_outcome": "actions_executed",
                    "actions_created": 1,
                    "skipped_reason": None,
                    "trace_id": "a1b2c3d4e5f6"
                }
            }
        }
    )


class DeviceEventResponse(BaseModel):
    """Response schema for device event query"""
    id: int
    user_id: int
    device_id: Optional[str]
    event_type: str
    payload_json: str
    recorded_at: Optional[datetime]
    received_at: datetime
    dedupe_key: Optional[str]

    model_config = ConfigDict(from_attributes=True)  # Pydantic V2: renamed from orm_mode
