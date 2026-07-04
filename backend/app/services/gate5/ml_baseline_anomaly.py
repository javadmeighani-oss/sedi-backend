"""Gate 5-F — Lightweight baseline anomaly engine (non-clinical, rule-based)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app.models import RawSignalBatchFeature
from backend.app.services.gate5.ml_registry import get_or_create_baseline_model
from backend.app.services.gate5.ml_shadow_inference import InferenceRecord, create_inference_record


class BaselineAnomalyError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class BaselineAnomalyResult:
    inference_record: InferenceRecord
    output_type: str
    score: float
    confidence: float
    features_summary: Dict[str, Any]


MIN_VALID_SAMPLES = 10
SHORT_WINDOW_SECONDS = 1.0
HIGH_ZERO_RATIO = 0.10
HIGH_INVALID_RATIO = 0.05
HIGH_NOISE_THRESHOLD = 50.0
HIGH_STD_THRESHOLD = 500.0
ANOMALY_STD_THRESHOLD = 200.0


def _quality_flags(quality: Optional[Mapping[str, Any]]) -> List[str]:
    if not quality:
        return []
    flags = quality.get("quality_flags")
    if isinstance(flags, list):
        return [str(f) for f in flags]
    return []


def evaluate_baseline_from_features(
    features: Mapping[str, Any],
    quality: Optional[Mapping[str, Any]] = None,
) -> tuple[str, float, float, Dict[str, Any]]:
    """
    Pure baseline evaluation from technical feature dict.
    Returns (output_type, score, confidence, features_summary).
    """
    valid_count = int(features.get("valid_sample_count") or features.get("actual_sample_count") or 0)
    duration = float(features.get("duration_seconds") or 0.0)
    std_dev = float(features.get("std_dev") or 0.0)
    zero_ratio = float(features.get("zero_ratio") or 0.0)
    invalid_ratio = float(features.get("invalid_sample_ratio") or 0.0)
    noise = float(features.get("estimated_noise_level") or 0.0)
    flags = _quality_flags(quality)

    summary: Dict[str, Any] = {
        "valid_sample_count": valid_count,
        "duration_seconds": duration,
        "std_dev": std_dev,
        "zero_ratio": zero_ratio,
        "invalid_sample_ratio": invalid_ratio,
        "estimated_noise_level": noise,
        "quality_flags": flags,
        "engine": "gate5_baseline_anomaly_v1",
    }

    if valid_count < MIN_VALID_SAMPLES or duration < SHORT_WINDOW_SECONDS:
        return "insufficient_data", 0.0, 0.2, summary

    quality_issues = (
        "sample_count_mismatch" in flags
        or "short_window" in flags
        or zero_ratio >= HIGH_ZERO_RATIO
        or invalid_ratio >= HIGH_INVALID_RATIO
        or noise >= HIGH_NOISE_THRESHOLD
    )
    if quality_issues:
        score = min(1.0, zero_ratio + invalid_ratio + (noise / max(HIGH_NOISE_THRESHOLD, 1.0)) * 0.3)
        return "signal_quality_issue", round(score, 4), 0.55, summary

    if std_dev >= HIGH_STD_THRESHOLD or std_dev >= ANOMALY_STD_THRESHOLD:
        score = min(1.0, std_dev / max(HIGH_STD_THRESHOLD, 1.0))
        confidence = 0.45 if std_dev < HIGH_STD_THRESHOLD else 0.6
        return "possible_anomaly", round(score, 4), confidence, summary

    if std_dev >= ANOMALY_STD_THRESHOLD * 0.5:
        score = min(1.0, std_dev / max(ANOMALY_STD_THRESHOLD, 1.0))
        return "unusual_pattern", round(score, 4), 0.4, summary

    return "low_confidence", 0.15, 0.35, summary


def run_baseline_anomaly(
    db: Session,
    feature_id: int,
    *,
    persist: bool = True,
) -> BaselineAnomalyResult:
    """Run baseline anomaly on a completed raw_signal_batch_features row."""
    feature = db.query(RawSignalBatchFeature).filter(RawSignalBatchFeature.id == feature_id).first()
    if not feature:
        raise BaselineAnomalyError("FEATURE_NOT_FOUND", f"feature id {feature_id} not found", 404)
    if feature.processing_status != "completed":
        raise BaselineAnomalyError("FEATURE_NOT_READY", "feature processing is not completed", 422)

    features = feature.features_json if isinstance(feature.features_json, dict) else {}
    quality = feature.quality_json if isinstance(feature.quality_json, dict) else None

    if not features:
        raise BaselineAnomalyError("FEATURES_EMPTY", "no features_json on feature row", 422)

    output_type, score, confidence, summary = evaluate_baseline_from_features(features, quality)

    if not persist:
        model = get_or_create_baseline_model(db)
        placeholder = InferenceRecord(
            id=0,
            user_id=feature.user_id,
            device_id=None,
            sensor_id=feature.sensor_id,
            raw_signal_batch_id=feature.raw_signal_batch_id,
            raw_signal_batch_feature_id=feature.id,
            model_id=model.id,
            output_type=output_type,
            score=score,
            confidence=confidence,
            features_summary_json=summary,
            safety_status="shadow_only",
            user_visible=False,
            created_at=feature.created_at,
        )
        return BaselineAnomalyResult(
            inference_record=placeholder,
            output_type=output_type,
            score=score,
            confidence=confidence,
            features_summary=summary,
        )

    model = get_or_create_baseline_model(db)
    record = create_inference_record(
        db,
        user_id=feature.user_id,
        model_id=model.id,
        output_type=output_type,
        raw_signal_batch_id=feature.raw_signal_batch_id,
        raw_signal_batch_feature_id=feature.id,
        sensor_id=feature.sensor_id,
        score=score,
        confidence=confidence,
        features_summary_json=summary,
        raw_output_json={
            "engine": "gate5_baseline_anomaly_v1",
            "output_type": output_type,
            "score": score,
            "confidence": confidence,
        },
        safety_status="shadow_only",
        user_visible=False,
    )
    return BaselineAnomalyResult(
        inference_record=record,
        output_type=output_type,
        score=score,
        confidence=confidence,
        features_summary=summary,
    )
