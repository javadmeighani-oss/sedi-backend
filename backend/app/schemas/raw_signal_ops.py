"""Gate 5-C/D — Admin ops schemas for raw signal feature processing."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_PROCESSING_VERSION = "gate5c_v1"


class RawSignalProcessPendingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=100)
    processing_version: str = Field(default=DEFAULT_PROCESSING_VERSION, max_length=32)
    dry_run: bool = False


class RawSignalProcessPendingData(BaseModel):
    processed: int
    completed: int
    failed: int
    skipped: int
    processing_version: str
    effective_limit: int
    dry_run: bool
    duration_ms: int
    candidate_batch_ids: List[int] = Field(default_factory=list)


class RawSignalProcessPendingResponse(BaseModel):
    ok: bool
    data: Optional[RawSignalProcessPendingData] = None
    error: Optional[dict] = None


class RawSignalProcessBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processing_version: str = Field(default=DEFAULT_PROCESSING_VERSION, max_length=32)
    allow_retry: bool = False


class RawSignalProcessBatchData(BaseModel):
    batch_id: int
    feature_id: int
    processing_status: str
    processing_version: str
    skipped: bool = False


class RawSignalProcessBatchResponse(BaseModel):
    ok: bool
    data: Optional[RawSignalProcessBatchData] = None
    error: Optional[dict] = None


class RawSignalBatchStatusData(BaseModel):
    batch_id: int
    has_batch: bool
    processing_version: str
    feature_id: Optional[int] = None
    processing_status: Optional[str] = None
    error_code: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class RawSignalBatchStatusResponse(BaseModel):
    ok: bool
    data: Optional[RawSignalBatchStatusData] = None
    error: Optional[dict] = None
