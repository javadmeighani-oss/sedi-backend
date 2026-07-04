"""Gate 5-F — Baseline anomaly engine tests."""

from __future__ import annotations

import pytest

from backend.app.services.gate5.ml_baseline_anomaly import (
    BaselineAnomalyError,
    evaluate_baseline_from_features,
    run_baseline_anomaly,
)
from backend.app.services.gate5.ml_safety import FORBIDDEN_OUTPUT_TYPES
from backend.ml_research.heart_signal_baseline import evaluate_windows, sample_evaluation


def test_insufficient_data():
    output_type, score, confidence, summary = evaluate_baseline_from_features(
        {"valid_sample_count": 3, "duration_seconds": 0.5, "std_dev": 0.0},
    )
    assert output_type == "insufficient_data"
    assert confidence <= 0.3
    assert "engine" in summary or "valid_sample_count" in summary


def test_signal_quality_issue():
    output_type, score, confidence, _ = evaluate_baseline_from_features(
        {
            "valid_sample_count": 2000,
            "duration_seconds": 8.0,
            "std_dev": 10.0,
            "zero_ratio": 0.5,
            "invalid_sample_ratio": 0.1,
            "estimated_noise_level": 5.0,
        },
        quality={"quality_flags": ["sample_count_mismatch"]},
    )
    assert output_type == "signal_quality_issue"


def test_possible_anomaly():
    output_type, score, confidence, summary = evaluate_baseline_from_features(
        {
            "valid_sample_count": 2000,
            "duration_seconds": 8.0,
            "std_dev": 600.0,
            "zero_ratio": 0.0,
            "invalid_sample_ratio": 0.0,
            "estimated_noise_level": 1.0,
        },
    )
    assert output_type == "possible_anomaly"
    assert score > 0
    assert "diagnosis" not in summary
    assert "arrhythmia" not in str(summary).lower()


def test_does_not_emit_forbidden_keys():
    _, _, _, summary = evaluate_baseline_from_features(
        {
            "valid_sample_count": 2000,
            "duration_seconds": 8.0,
            "std_dev": 600.0,
            "zero_ratio": 0.0,
            "invalid_sample_ratio": 0.0,
            "estimated_noise_level": 1.0,
        },
    )
    for forbidden in FORBIDDEN_OUTPUT_TYPES:
        assert forbidden not in summary


def test_empty_features_returns_insufficient_data():
    output_type, _, _, _ = evaluate_baseline_from_features({})
    assert output_type == "insufficient_data"


def test_offline_sample_evaluation():
    metrics = sample_evaluation()
    assert metrics["window_count"] == 2
    assert "output_type_counts" in metrics
    assert metrics["evaluation_kind"] == "offline_baseline"


def test_offline_evaluate_windows():
    metrics = evaluate_windows(
        [
            {
                "window_id": "w1",
                "features": {
                    "valid_sample_count": 2000,
                    "duration_seconds": 8.0,
                    "std_dev": 20.0,
                    "zero_ratio": 0.0,
                    "invalid_sample_ratio": 0.0,
                    "estimated_noise_level": 1.0,
                },
            }
        ]
    )
    assert metrics["window_count"] == 1


def test_run_baseline_missing_feature(db):
    with pytest.raises(BaselineAnomalyError) as exc:
        run_baseline_anomaly(db, 999999)
    assert exc.value.status_code == 404
