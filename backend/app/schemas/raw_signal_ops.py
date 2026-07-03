"""Gate 5-C — Admin ops schemas for raw signal feature processing."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_PROCESSING_VERSION = "gate5c_v1"


class RawSignalProcessPendingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=100)
    processing_version: str = Field(default=DEFAULT_PROCESSING_VERSION, max_length=32)


class RawSignalProcessPendingData(BaseModel):
    processed: int
    completed: int
    failed: int
    skipped: int
    processing_version: str


class RawSignalProcessPendingResponse(BaseModel):
    ok: bool
    data: Optional[RawSignalProcessPendingData] = None
    error: Optional[dict] = None


class RawSignalProcessBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processing_version: str = Field(default=DEFAULT_PROCESSING_VERSION, max_length=32)


class RawSignalProcessBatchData(BaseModel):
    batch_id: int
    feature_id: int
    processing_status: str
    processing_version: str


class RawSignalProcessBatchResponse(BaseModel):
    ok: bool
    data: Optional[RawSignalProcessBatchData] = None
    error: Optional[dict] = None
