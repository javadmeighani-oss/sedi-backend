"""Gate 4D-2 environment-driven policy feature flags (default OFF)."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUE_VALUES


def gate4_policy_shadow_enabled() -> bool:
    """When True, future runtime may compute/log policy without changing enqueue."""
    return _env_flag_enabled("SEDI_GATE4_POLICY_SHADOW")


def gate4_policy_enforce_enabled() -> bool:
    """When True, future runtime may apply policy to enqueue decisions."""
    return _env_flag_enabled("SEDI_GATE4_POLICY_ENFORCE")


def gate4_policy_log_decisions_enabled() -> bool:
    """When True, future runtime may emit structured policy decision logs."""
    return _env_flag_enabled("SEDI_GATE4_POLICY_LOG_DECISIONS")


def gate4_policy_active() -> bool:
    """True when shadow or enforce mode is enabled."""
    return gate4_policy_shadow_enabled() or gate4_policy_enforce_enabled()
