"""I9 canonical device packet ingest schemas."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PacketObservationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_type: str = Field(..., description="heart_rate | blood_pressure | glucose | temperature | spo2 | device_reported_cardiac_event")
    payload: Dict[str, Any] = Field(..., description="Type-specific observation payload")
    detected_at: Optional[datetime] = Field(None, description="Observation time; defaults to packet measured_at")


class DevicePacketIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_packet_id: str = Field(..., min_length=1, max_length=128)
    measured_at: datetime
    sequence_number: Optional[int] = None
    measured_interval_start: Optional[datetime] = None
    measured_interval_end: Optional[datetime] = None
    gateway_received_at: Optional[datetime] = None
    transport: Optional[Literal["bluetooth", "wifi", "cellular", "unknown"]] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    algorithm_version: Optional[str] = None
    quality_metadata: Optional[Dict[str, Any]] = None
    provenance: Optional[Dict[str, Any]] = None
    observations: List[PacketObservationSchema] = Field(default_factory=list)

    @field_validator("client_packet_id")
    @classmethod
    def strip_packet_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("client_packet_id must not be empty")
        return s


class DevicePacketIngestResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None

    model_config = ConfigDict(extra="forbid")
