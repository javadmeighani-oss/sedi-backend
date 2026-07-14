"""Section 15 intelligence environment-driven feature flags (default OFF)."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUE_VALUES


def intelligence_orchestrator_v1_enabled() -> bool:
    """
    When True, orchestration runs in structured mode.
    When False (default), orchestration still runs in compatibility mode.
    The router always invokes IntelligenceOrchestrator either way.
    """
    return _env_flag_enabled("SEDI_INTELLIGENCE_ORCHESTRATOR_V1")
