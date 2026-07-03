# app/schemas/device.py
"""
Device Ingestion Schemas (Release C1)
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, Literal, List
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
    status: Optional[str] = Field(None, description="Optional device status (active/revoked)")
    battery: Optional[float] = Field(None, description="Optional battery level (legacy field name)")
    battery_level: Optional[float] = Field(None, description="Optional battery level (0-100)")
    temperature: Optional[float] = Field(None, description="Optional device temperature")
    firmware_version: Optional[str] = Field(None, description="Gadget Hub firmware version")
    hardware_version: Optional[str] = Field(None, description="Gadget Hub hardware version")
    hub_status: Optional[str] = Field(None, description="Hub-reported operational status label")
    last_sync_at: Optional[datetime] = Field(None, description="Last sensor sync time from hub")


class SensorSyncItem(BaseModel):
    """Single sensor reported by Gadget Hub during sync."""

    model_config = ConfigDict(extra="forbid")

    sensor_key: str = Field(..., min_length=1, description="Stable sensor id from hub")
    sensor_type: str = Field(default="unknown", description="Sensor type (ecg, heart_rate, ...)")
    display_name: Optional[str] = None
    connection_status: str = Field(default="unknown")
    battery_level: Optional[float] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None
    last_seen_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None


class SensorSyncRequest(BaseModel):
    """Gadget Hub sensor registry sync payload."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Logical Gadget Hub device id")
    sensors: List[SensorSyncItem] = Field(default_factory=list, description="Sensors to upsert")


class SensorSyncResponse(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


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
