"""Gate 5-E/F/G — Environment-driven ML feature flags (default OFF)."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUE_VALUES


def ml_shadow_enabled() -> bool:
    """Allow storing shadow inference records via admin API."""
    return _env_flag_enabled("SEDI_GATE5_ML_SHADOW_ENABLED")


def ml_processing_enabled() -> bool:
    """Allow baseline anomaly processing on raw signal features."""
    return _env_flag_enabled("SEDI_GATE5_ML_PROCESSING_ENABLED")


def ml_care_bridge_enabled() -> bool:
    """Allow care bridge to create internal device events (not notifications)."""
    return _env_flag_enabled("SEDI_GATE5_ML_CARE_BRIDGE_ENABLED")


def ml_notification_enabled() -> bool:
    """Allow care bridge to deliver user notifications (requires care bridge)."""
    return _env_flag_enabled("SEDI_GATE5_ML_NOTIFICATION_ENABLED")


def ml_chat_context_enabled() -> bool:
    """Allow care bridge to attach chat/interaction context."""
    return _env_flag_enabled("SEDI_GATE5_ML_CHAT_CONTEXT_ENABLED")


def ml_log_decisions() -> bool:
    """Verbose decision logging for ML ops (no user-facing effect)."""
    return _env_flag_enabled("SEDI_GATE5_ML_LOG_DECISIONS")


def ml_flags_snapshot() -> dict[str, bool]:
    """Current ML flag states for ops diagnostics."""
    return {
        "SEDI_GATE5_ML_SHADOW_ENABLED": ml_shadow_enabled(),
        "SEDI_GATE5_ML_PROCESSING_ENABLED": ml_processing_enabled(),
        "SEDI_GATE5_ML_CARE_BRIDGE_ENABLED": ml_care_bridge_enabled(),
        "SEDI_GATE5_ML_NOTIFICATION_ENABLED": ml_notification_enabled(),
        "SEDI_GATE5_ML_CHAT_CONTEXT_ENABLED": ml_chat_context_enabled(),
        "SEDI_GATE5_ML_LOG_DECISIONS": ml_log_decisions(),
    }
