"""Minimal governed V1 schedule_rule allowlist (PD-I8-04B). No DB enum."""

from __future__ import annotations

SCHEDULE_RULE_DAILY_WELLBEING_CHECK = "daily_wellbeing_check"

SCHEDULE_RULE_ALLOWLIST_V1 = frozenset(
    {
        SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
    }
)

DEFAULT_V1_SCHEDULE_RULE_ID = SCHEDULE_RULE_DAILY_WELLBEING_CHECK


def is_allowed_schedule_rule(schedule_rule_id: str | None) -> bool:
    if not schedule_rule_id:
        return False
    return schedule_rule_id.strip() in SCHEDULE_RULE_ALLOWLIST_V1
