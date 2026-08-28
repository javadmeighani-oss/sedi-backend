# app/schemas/devices.py
"""
Device Identity Schemas (Release C2 + Gate 5-A Gadget Hub)
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Literal, Any, Dict
from datetime import datetime


class DeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Logical device id (e.g., Sedi001)")
    device_type: Optional[str] = Field("heart_rate", description="Device type (v1 default: heart_rate; use gadget_hub for Gadget Hub)")
    subject_user_id: Optional[int] = Field(
        None,
        description="Legacy: User whose health data this device represents; prefer health_subject_id",
    )
    health_subject_id: Optional[int] = Field(
        None,
        description="I9 health subject for device binding (managed or self)",
    )


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

    model_config = ConfigDict(from_attributes=True)


class DevicesListResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


HubOperationalStatus = Literal[
    "not_registered", "connected", "recently_seen", "disconnected", "revoked", "unknown"
]


class GadgetHubStatusInfo(BaseModel):
    device_id: str
    device_type: str
    status: HubOperationalStatus
    last_seen_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    battery_level: Optional[float] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None


class SensorStatusInfo(BaseModel):
    sensor_key: str
    sensor_type: str
    display_name: Optional[str] = None
    connection_status: str
    battery_level: Optional[float] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    capabilities: Optional[Dict[str, Any]] = None


class HubStatusResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


class DeviceProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Logical device id for unclaimed platform identity")
    device_type: Optional[str] = Field("heart_rate", description="Device type")


class DeviceClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    health_subject_id: int
    possession_proof: str = Field(..., description="COMMISSIONING_READY / per-device credential proof")
    gateway_install_id: Optional[str] = Field(None, description="Optional stable mobile gateway install id")


class DeviceTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health_subject_id: int
    possession_proof: str = Field(..., description="Governed commissioning proof for new assignment")


class DeviceGatewayPairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_install_id: str = Field(..., min_length=8, max_length=128)


class DeviceGatewayDisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_install_id: str = Field(..., min_length=8, max_length=128)

