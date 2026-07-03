"""Gate 5-C — Pure technical feature computation for raw signal batches (stdlib only)."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_ADC_MIN = 0.0
DEFAULT_ADC_MAX = 4095.0
SHORT_WINDOW_SECONDS = 1.0
ZERO_RATIO_THRESHOLD = 0.10
INVALID_RATIO_THRESHOLD = 0.01
CLIPPING_RATIO_THRESHOLD = 0.01
BASELINE_DRIFT_THRESHOLD = 1e-6

FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "diagnosis",
        "arrhythmia",
        "afib",
        "disease",
        "severity",
        "risk",
        "ml_score",
        "alert",
        "emergency",
        "treatment",
        "medication",
        "dosage",
        "recommendation",
    }
)

ALLOWED_QUALITY_FLAGS = frozenset(
    {
        "short_window",
        "sample_count_mismatch",
        "high_zero_ratio",
        "high_invalid_sample_ratio",
        "possible_clipping",
        "baseline_drift_estimated",
        "noise_estimated",
    }
)


class RawSignalFeatureComputeError(Exception):
    """Raised when sample validation or feature computation fails."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ComputeResult:
    features: Dict[str, Any]
    quality: Dict[str, Any]


def _validate_no_forbidden_keys(payload: Mapping[str, Any], *, context: str) -> None:
    for key in payload:
        key_lower = str(key).lower()
        if key_lower in FORBIDDEN_OUTPUT_KEYS:
            raise RawSignalFeatureComputeError(
                "FORBIDDEN_OUTPUT_KEY",
                f"forbidden clinical key in {context}: {key}",
            )


def _parse_numeric_samples(samples: Sequence[Any]) -> Tuple[List[float], int]:
    """Return valid floats and invalid count."""
    valid: List[float] = []
    invalid_count = 0
    for item in samples:
        if isinstance(item, bool):
            invalid_count += 1
            continue
        if isinstance(item, (int, float)):
            value = float(item)
            if not math.isfinite(value):
                invalid_count += 1
                continue
            valid.append(value)
            continue
        invalid_count += 1
    return valid, invalid_count


def _clip_bounds(metadata: Optional[Mapping[str, Any]]) -> Tuple[float, float]:
    if metadata is None:
        return DEFAULT_ADC_MIN, DEFAULT_ADC_MAX
    low = metadata.get("adc_min", DEFAULT_ADC_MIN)
    high = metadata.get("adc_max", DEFAULT_ADC_MAX)
    try:
        low_f = float(low)
        high_f = float(high)
    except (TypeError, ValueError):
        return DEFAULT_ADC_MIN, DEFAULT_ADC_MAX
    if high_f <= low_f:
        return DEFAULT_ADC_MIN, DEFAULT_ADC_MAX
    return low_f, high_f


def _baseline_drift_estimate(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    block_size = max(1, len(values) // 10)
    means: List[float] = []
    for start in range(0, len(values), block_size):
        block = values[start : start + block_size]
        if block:
            means.append(statistics.fmean(block))
    if len(means) < 2:
        return 0.0
    n = len(means)
    x_mean = (n - 1) / 2.0
    y_mean = statistics.fmean(means)
    numerator = sum((i - x_mean) * (means[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _estimated_noise_level(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    diffs = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
    return statistics.fmean(diffs) if diffs else 0.0


def compute_raw_signal_features(
    *,
    samples: Sequence[Any],
    started_at: datetime,
    ended_at: datetime,
    declared_sample_rate_hz: float,
    declared_sample_count: int,
    metadata: Optional[Mapping[str, Any]] = None,
    quality_metadata: Optional[Mapping[str, Any]] = None,
    storage_backend: str = "postgres_json",
    processing_version: str = "gate5c_v1",
) -> ComputeResult:
    """
    Compute non-diagnostic technical features from raw numeric samples.
    Pure function — no DB or side effects.
    """
    if metadata is not None:
        _validate_no_forbidden_keys(metadata, context="metadata")
    if quality_metadata is not None:
        _validate_no_forbidden_keys(quality_metadata, context="quality_metadata")

    duration_seconds = max(0.0, (ended_at - started_at).total_seconds())
    valid_values, invalid_count = _parse_numeric_samples(samples)
    actual_sample_count = len(samples)
    valid_count = len(valid_values)

    if valid_count == 0:
        raise RawSignalFeatureComputeError("SAMPLES_EMPTY", "no valid numeric samples")

    expected_sample_count = int(round(duration_seconds * declared_sample_rate_hz)) if duration_seconds > 0 else 0
    sample_count_mismatch = actual_sample_count != declared_sample_count

    effective_sample_rate_hz = (
        valid_count / duration_seconds if duration_seconds > 0 else 0.0
    )

    min_value = min(valid_values)
    max_value = max(valid_values)
    mean_value = statistics.fmean(valid_values)
    std_dev = statistics.pstdev(valid_values) if valid_count > 1 else 0.0

    zero_ratio = sum(1 for v in valid_values if v == 0.0) / valid_count
    invalid_sample_ratio = invalid_count / actual_sample_count if actual_sample_count > 0 else 1.0

    clip_low, clip_high = _clip_bounds(metadata)
    clipped = sum(1 for v in valid_values if v <= clip_low or v >= clip_high)
    clipping_ratio = clipped / valid_count

    estimated_noise_level = _estimated_noise_level(valid_values)
    baseline_drift_estimate = _baseline_drift_estimate(valid_values)

    features: Dict[str, Any] = {
        "duration_seconds": duration_seconds,
        "declared_sample_rate_hz": float(declared_sample_rate_hz),
        "effective_sample_rate_hz": effective_sample_rate_hz,
        "expected_sample_count": expected_sample_count,
        "actual_sample_count": actual_sample_count,
        "declared_sample_count": declared_sample_count,
        "sample_count_mismatch": sample_count_mismatch,
        "min_value": min_value,
        "max_value": max_value,
        "mean_value": mean_value,
        "std_dev": std_dev,
        "zero_ratio": zero_ratio,
        "invalid_sample_ratio": invalid_sample_ratio,
        "clipping_ratio": clipping_ratio,
        "estimated_noise_level": estimated_noise_level,
        "baseline_drift_estimate": baseline_drift_estimate,
    }

    quality_flags: List[str] = []
    if duration_seconds < SHORT_WINDOW_SECONDS:
        quality_flags.append("short_window")
    if sample_count_mismatch:
        quality_flags.append("sample_count_mismatch")
    if zero_ratio > ZERO_RATIO_THRESHOLD:
        quality_flags.append("high_zero_ratio")
    if invalid_sample_ratio > INVALID_RATIO_THRESHOLD:
        quality_flags.append("high_invalid_sample_ratio")
    if clipping_ratio > CLIPPING_RATIO_THRESHOLD:
        quality_flags.append("possible_clipping")
    if abs(baseline_drift_estimate) > BASELINE_DRIFT_THRESHOLD:
        quality_flags.append("baseline_drift_estimated")
    if estimated_noise_level > 0:
        quality_flags.append("noise_estimated")

    for flag in quality_flags:
        if flag not in ALLOWED_QUALITY_FLAGS:
            raise RawSignalFeatureComputeError("INVALID_QUALITY_FLAG", f"invalid quality flag: {flag}")

    quality: Dict[str, Any] = {
        "quality_flags": quality_flags,
        "ingest_quality_metadata": dict(quality_metadata) if quality_metadata else None,
        "processing_version": processing_version,
        "storage_backend": storage_backend,
    }

    _validate_no_forbidden_keys(features, context="features")
    _validate_no_forbidden_keys(quality, context="quality")

    return ComputeResult(features=features, quality=quality)
