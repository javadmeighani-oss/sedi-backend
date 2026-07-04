"""Gate 5-E/F/G — Admin ops schemas for ML registry, inference, and care bridge."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MlModelCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., min_length=1, max_length=64)
    signal_family: str = Field(..., max_length=64)
    input_type: str = Field(..., max_length=64)
    status: str = Field(default="research", max_length=32)
    training_dataset: Optional[str] = Field(default=None, max_length=255)
    metrics_json: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class MlModelData(BaseModel):
    id: int
    model_name: str
    model_version: str
    signal_family: str
    input_type: str
    status: str
    training_dataset: Optional[str] = None
    metrics_json: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MlModelResponse(BaseModel):
    ok: bool
    data: Optional[MlModelData] = None
    error: Optional[dict] = None


class MlModelListData(BaseModel):
    models: List[MlModelData]
    count: int


class MlModelListResponse(BaseModel):
    ok: bool
    data: Optional[MlModelListData] = None
    error: Optional[dict] = None


class MlInferenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(..., ge=1)
    model_id: int = Field(..., ge=1)
    output_type: str = Field(..., max_length=64)
    device_id: Optional[str] = Field(default=None, max_length=255)
    sensor_id: Optional[int] = Field(default=None, ge=1)
    raw_signal_batch_id: Optional[int] = Field(default=None, ge=1)
    raw_signal_batch_feature_id: Optional[int] = Field(default=None, ge=1)
    score: Optional[float] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    features_summary_json: Optional[Dict[str, Any]] = None
    raw_output_json: Optional[Dict[str, Any]] = None
    safety_status: str = Field(default="shadow_only", max_length=32)
    user_visible: bool = False


class MlInferenceData(BaseModel):
    id: int
    user_id: int
    device_id: Optional[str] = None
    sensor_id: Optional[int] = None
    raw_signal_batch_id: Optional[int] = None
    raw_signal_batch_feature_id: Optional[int] = None
    model_id: int
    output_type: str
    score: Optional[float] = None
    confidence: Optional[float] = None
    features_summary_json: Optional[Dict[str, Any]] = None
    safety_status: str
    user_visible: bool
    created_at: datetime


class MlInferenceResponse(BaseModel):
    ok: bool
    data: Optional[MlInferenceData] = None
    error: Optional[dict] = None


class MlInferenceListData(BaseModel):
    records: List[MlInferenceData]
    count: int


class MlInferenceListResponse(BaseModel):
    ok: bool
    data: Optional[MlInferenceListData] = None
    error: Optional[dict] = None


class MlBaselineRunData(BaseModel):
    feature_id: int
    inference_record_id: int
    output_type: str
    score: float
    confidence: float
    features_summary: Dict[str, Any]


class MlBaselineRunResponse(BaseModel):
    ok: bool
    data: Optional[MlBaselineRunData] = None
    error: Optional[dict] = None


class MlCareBridgeData(BaseModel):
    record_id: int
    output_type: str
    care_suggestion_text: str
    dry_run: bool
    bridge_enabled: bool
    notification_enabled: bool
    chat_context_enabled: bool
    device_event_id: Optional[int] = None
    notification_id: Optional[int] = None
    interaction_event_id: Optional[int] = None
    blocked_reason: Optional[str] = None


class MlCareBridgeResponse(BaseModel):
    ok: bool
    data: Optional[MlCareBridgeData] = None
    error: Optional[dict] = None
