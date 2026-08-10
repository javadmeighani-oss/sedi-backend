"""Physiological measurement idempotency key builder (§270.L)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def build_physiological_idempotency_key(
    *,
    device_id: int | str,
    measurement_type: str,
    measured_at: datetime,
    sensor_id: Optional[int | str] = None,
    source_sequence: Optional[str] = None,
) -> str:
    """Deterministic idempotency key.

    Derived from device + sensor + measurement_type + measured_at_bucket_or_sequence.
    Must NOT use received_at alone.
    """
    if source_sequence:
        seq = str(source_sequence).strip()
        return f"pm:{device_id}:{sensor_id or 'nosensor'}:{measurement_type}:seq:{seq}"

    # Second-precision bucket of measured_at (not received_at).
    if measured_at.tzinfo is not None:
        stamp = measured_at.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    else:
        stamp = measured_at.strftime("%Y-%m-%dT%H:%M:%S")
    return f"pm:{device_id}:{sensor_id or 'nosensor'}:{measurement_type}:at:{stamp}"
