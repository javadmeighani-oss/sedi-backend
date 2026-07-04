# Gate 5-E — Expected dataset contract for heart/ECG research (non-production)

## Purpose

Document the expected format for offline evaluation datasets used with
`ml_model_registry.metrics_json`. This is research-only — not used for clinical
decisions or user-facing outputs.

## Window record format

Each evaluation window should reference an already-extracted feature row:

```json
{
  "window_id": "string",
  "user_id": "integer (anonymized in research exports)",
  "signal_family": "ecg | heart | heart_rate",
  "features": {
    "duration_seconds": 8.0,
    "std_dev": 12.5,
    "zero_ratio": 0.01,
    "invalid_sample_ratio": 0.0,
    "estimated_noise_level": 2.1
  },
  "quality_flags": ["short_window"],
  "label": "optional_research_label_not_clinical"
}
```

## Future public datasets (reference only)

- PhysioNet MIT-BIH Arrhythmia Database — research reference only; not for V1 diagnosis
- Other ECG corpora — require explicit ethics review before any production use

## Metrics JSON shape (compatible with ml_model_registry)

```json
{
  "evaluation_kind": "offline_baseline",
  "window_count": 100,
  "output_type_counts": {
    "possible_anomaly": 3,
    "signal_quality_issue": 10,
    "low_confidence": 20,
    "insufficient_data": 5
  },
  "notes": "Non-clinical baseline only"
}
```

## Safety

- No diagnosis labels in production paths
- No arrhythmia classification claims
- Research labels must not flow to user-visible notifications
