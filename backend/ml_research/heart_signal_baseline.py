"""
Gate 5-E — Offline heart-signal baseline evaluation (research-only).

Pure functions — no DB, no network, no heavy ML dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from backend.app.services.gate5.ml_baseline_anomaly import evaluate_baseline_from_features


def load_feature_windows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize iterable of feature window dicts for evaluation."""
    out: List[Dict[str, Any]] = []
    for row in rows:
        features = row.get("features")
        if not isinstance(features, dict):
            continue
        out.append(
            {
                "window_id": row.get("window_id"),
                "features": dict(features),
                "quality": row.get("quality") if isinstance(row.get("quality"), dict) else None,
            }
        )
    return out


def evaluate_windows(windows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """
    Run baseline anomaly evaluation over feature windows.
    Returns metrics JSON compatible with ml_model_registry.metrics_json.
    """
    output_type_counts: Dict[str, int] = {}
    scores: List[float] = []
    evaluated = 0

    for window in load_feature_windows(windows):
        output_type, score, confidence, _summary = evaluate_baseline_from_features(
            window["features"],
            window.get("quality"),
        )
        output_type_counts[output_type] = output_type_counts.get(output_type, 0) + 1
        scores.append(score)
        evaluated += 1

    avg_score = sum(scores) / len(scores) if scores else 0.0
    return {
        "evaluation_kind": "offline_baseline",
        "engine": "gate5_baseline_anomaly_v1",
        "window_count": evaluated,
        "output_type_counts": output_type_counts,
        "average_score": round(avg_score, 4),
        "notes": "Research-only non-clinical baseline evaluation",
    }


def sample_evaluation() -> Dict[str, Any]:
    """Tiny built-in sample for smoke/documentation."""
    sample_windows = [
        {
            "window_id": "sample-1",
            "features": {
                "valid_sample_count": 2000,
                "duration_seconds": 8.0,
                "std_dev": 15.0,
                "zero_ratio": 0.01,
                "invalid_sample_ratio": 0.0,
                "estimated_noise_level": 2.0,
            },
        },
        {
            "window_id": "sample-2",
            "features": {
                "valid_sample_count": 5,
                "duration_seconds": 0.5,
                "std_dev": 0.0,
                "zero_ratio": 0.0,
                "invalid_sample_ratio": 0.0,
                "estimated_noise_level": 0.0,
            },
        },
    ]
    return evaluate_windows(sample_windows)
