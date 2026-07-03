"""Gate 4 environment-driven feature flags (default OFF)."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(name: str) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return raw in _TRUE_VALUES


def gate4_policy_shadow_enabled() -> bool:
    """When True, compute/log policy decisions without changing enqueue behavior."""
    return _env_flag_enabled("SEDI_GATE4_POLICY_SHADOW")


def gate4_policy_enforce_enabled() -> bool:
    """When True, policy may suppress enqueue when should_enqueue=False."""
    return _env_flag_enabled("SEDI_GATE4_POLICY_ENFORCE")


def gate4_policy_log_decisions_enabled() -> bool:
    """When True, emit structured policy decision logs (shadow or enforce)."""
    return _env_flag_enabled("SEDI_GATE4_POLICY_LOG_DECISIONS")


def gate4_policy_active() -> bool:
    """True when shadow or enforce mode is enabled."""
    return gate4_policy_shadow_enabled() or gate4_policy_enforce_enabled()


def gate4_delivery_policy_enabled() -> bool:
    """When True, delivery-time policy may defer/skip send."""
    return _env_flag_enabled("SEDI_GATE4_DELIVERY_POLICY")


def gate4_delivery_policy_shadow_enabled() -> bool:
    """When True, compute/log delivery policy without changing send behavior."""
    return _env_flag_enabled("SEDI_GATE4_DELIVERY_POLICY_SHADOW")


def gate4_delivery_policy_active() -> bool:
    """True when delivery policy enforce or shadow mode is enabled."""
    return gate4_delivery_policy_enabled() or gate4_delivery_policy_shadow_enabled()


def gate4_daily_0800_enabled() -> bool:
    """When True, morning scheduler uses Gate 4 daily time + prefs (default 08:00)."""
    return _env_flag_enabled("SEDI_GATE4_DAILY_0800_ENABLED")


def gate4_feedback_policy_enabled() -> bool:
    """When True, NOT_NOW/TALK_LATER feedback updates guard state and policy."""
    return _env_flag_enabled("SEDI_GATE4_FEEDBACK_POLICY")


def gate4_active_conversation_defer_enabled() -> bool:
    """When True, recent chat events can defer non-critical delivery."""
    return _env_flag_enabled("SEDI_GATE4_ACTIVE_CONVERSATION_DEFER")
