# app/schemas/device.py
"""
Device Ingestion Schemas (Release C1)
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, Dict, Any, Literal, List
from datetime import datetime


RAW_SIGNAL_TYPES = frozenset({"ecg", "heart_rate_raw", "unknown"})

FORBIDDEN_CLINICAL_FIELD_NAMES = frozenset(
    {
        "diagnosis",
        "arrhythmia",
        "afib",
        "alert",
        "severity",
        "ml_score",
        "interpretation",
        "medication",
        "treatment",
        "dosage",
    }
)

MAX_RAW_SAMPLE_COUNT = 10_000
MIN_RAW_SAMPLE_COUNT = 1
MIN_SAMPLE_RATE_HZ = 1.0
MAX_SAMPLE_RATE_HZ = 2000.0
MAX_CLIENT_BATCH_ID_LEN = 128
MAX_METADATA_COMBINED_BYTES = 8 * 1024
MAX_RAW_PAYLOAD_BYTES = 512 * 1024


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


class RawSignalBatchRequest(BaseModel):
    """Gadget Hub raw signal batch ingest payload (store-only)."""

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, description="Logical Gadget Hub device id")
    sensor_key: str = Field(..., min_length=1, description="Registered sensor key on this hub")
    client_batch_id: str = Field(..., min_length=1, max_length=MAX_CLIENT_BATCH_ID_LEN)
    signal_type: Literal["ecg", "heart_rate_raw", "unknown"] = Field(
        ..., description="Raw signal category (non-clinical)"
    )
    sample_rate_hz: float = Field(..., ge=MIN_SAMPLE_RATE_HZ, le=MAX_SAMPLE_RATE_HZ)
    started_at: datetime = Field(..., description="Batch window start (device/hub time)")
    ended_at: datetime = Field(..., description="Batch window end (device/hub time)")
    sample_count: int = Field(..., ge=MIN_RAW_SAMPLE_COUNT, le=MAX_RAW_SAMPLE_COUNT)
    samples: List[float] = Field(..., description="Numeric raw samples only")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Non-clinical hub batch metadata")
    quality_metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Non-clinical quality flags (SNR, lead-off, etc.)"
    )

    @field_validator("samples")
    @classmethod
    def samples_must_be_numeric(cls, value: List[float]) -> List[float]:
        for item in value:
            if not isinstance(item, (int, float)):
                raise ValueError("samples must contain numeric values only")
        return [float(v) for v in value]

    @model_validator(mode="after")
    def validate_batch_consistency(self) -> "RawSignalBatchRequest":
        if self.started_at >= self.ended_at:
            raise ValueError("started_at must be before ended_at")
        if len(self.samples) != self.sample_count:
            raise ValueError("sample_count must match len(samples)")

        for field_name, payload in (("metadata", self.metadata), ("quality_metadata", self.quality_metadata)):
            if payload is None:
                continue
            for key in payload:
                if key in FORBIDDEN_CLINICAL_FIELD_NAMES:
                    raise ValueError(f"forbidden clinical field in {field_name}: {key}")

        combined_meta_len = 0
        if self.metadata is not None:
            combined_meta_len += len(str(self.metadata).encode("utf-8"))
        if self.quality_metadata is not None:
            combined_meta_len += len(str(self.quality_metadata).encode("utf-8"))
        if combined_meta_len > MAX_METADATA_COMBINED_BYTES:
            raise ValueError("metadata and quality_metadata combined size exceeds limit")

        samples_bytes = len(str(self.samples).encode("utf-8"))
        if samples_bytes + combined_meta_len > MAX_RAW_PAYLOAD_BYTES:
            raise ValueError("payload size exceeds limit")

        return self


class RawSignalBatchData(BaseModel):
    batch_id: int
    dedupe_key: str
    received_at: datetime
    sample_count: int
    storage_backend: str = "postgres_json"
    dedupe_hit: bool = False
    message: Optional[str] = None


class RawSignalBatchResponse(BaseModel):
    ok: bool
    data: Optional[RawSignalBatchData] = None
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
