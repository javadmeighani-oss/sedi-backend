# backend/app/behavior/config.py
"""Behavior Layer V1: config from env (single place for BEHAVIOR_V1_*)."""
import os


def is_behavior_v1_enabled() -> bool:
    """When False, behavior layer has zero effect. Default: False."""
    return os.environ.get("BEHAVIOR_V1_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def get_daily_engagement_budget() -> int:
    """Max Sedi-initiated engagements (lead-in + companion_ping) per user per day. Default: 1 (field-test safe)."""
    return int(os.environ.get("BEHAVIOR_V1_DAILY_BUDGET", "1") or "1")


def get_cooldown_minutes() -> int:
    """Min minutes between Sedi-initiated actions. Default: 60."""
    return int(os.environ.get("BEHAVIOR_V1_COOLDOWN_MINUTES", "60") or "60")


def get_quiet_hours_use_notification_runtime() -> bool:
    """If True, use notification_runtime.quiet_hours for quiet hours. Default: True."""
    return os.environ.get("BEHAVIOR_V1_QUIET_HOURS_USE_RUNTIME", "true").strip().lower() in ("true", "1", "yes")
