"""I5 weekly cron registration verifier contract (production activation Step7).

Mirrors the bash grep used by:
  .github/workflows/w6p01-prod-activate-weekly.yml
  .github/workflows/i5-prod-multisource-weekly-activation.yml

Governed production contract (do not treat INTERVAL as trigger proof):
  trigger=cron day_of_week=fri hour=3 minute=30 timezone=Asia/Tehran
  max_instances=1 coalesce=True enabled=True
"""
from __future__ import annotations

import re

# Keep in sync with workflow Step7 cron registration checks.
WEEKLY_CRON_REGISTRATION_RE = re.compile(
    r"weekly_international_knowledge_crawler registered"
    r".*trigger=cron"
    r".*day_of_week=fri"
    r".*hour=3"
    r".*minute=30"
    r".*timezone=Asia/Tehran"
    r".*max_instances=1"
    r".*coalesce=True"
    r".*enabled=True"
)

# Exact bash Extended RegEx used in workflows (must stay byte-identical intent).
WORKFLOW_CRON_GREP_ERE = (
    r"weekly_international_knowledge_crawler registered"
    r".*trigger=cron"
    r".*day_of_week=fri"
    r".*hour=3"
    r".*minute=30"
    r".*timezone=Asia/Tehran"
    r".*max_instances=1"
    r".*coalesce=True"
    r".*enabled=True"
)

STALE_INTERVAL_GREP_ERE = r"interval_min=10080"


def accepts_weekly_cron_registration_line(line: str) -> bool:
    """Return True iff line proves the governed weekly cron registration."""
    if not line or not str(line).strip():
        return False
    return WEEKLY_CRON_REGISTRATION_RE.search(str(line)) is not None


def sample_valid_production_registration_line() -> str:
    return (
        "[Sedi Scheduler] weekly_international_knowledge_crawler registered "
        "trigger=cron day_of_week=fri hour=3 minute=30 timezone=Asia/Tehran "
        "max_instances=1 coalesce=True enabled=True "
        "next_calendar_fire=2026-08-28T03:30:00+03:30 first_run_delay_sec=ignored"
    )
