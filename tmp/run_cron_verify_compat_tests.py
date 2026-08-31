"""Offline runner for cron verify compat tests (no Postgres required)."""
from __future__ import annotations

from pathlib import Path

from backend.tests.helpers.i5_weekly_cron_registration_verify import (
    STALE_INTERVAL_GREP_ERE,
    WORKFLOW_CRON_GREP_ERE,
    accepts_weekly_cron_registration_line,
    sample_valid_production_registration_line,
)

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOWS = [
    _REPO / ".github" / "workflows" / "w6p01-prod-activate-weekly.yml",
    _REPO / ".github" / "workflows" / "i5-prod-multisource-weekly-activation.yml",
]


def main() -> None:
    assert accepts_weekly_cron_registration_line(sample_valid_production_registration_line())
    assert not accepts_weekly_cron_registration_line(
        sample_valid_production_registration_line().replace("day_of_week=fri", "day_of_week=mon")
    )
    assert not accepts_weekly_cron_registration_line(
        sample_valid_production_registration_line().replace("hour=3", "hour=4")
    )
    assert not accepts_weekly_cron_registration_line(
        sample_valid_production_registration_line().replace("minute=30", "minute=0")
    )
    assert not accepts_weekly_cron_registration_line(
        sample_valid_production_registration_line().replace("timezone=Asia/Tehran", "timezone=UTC")
    )
    assert not accepts_weekly_cron_registration_line("")
    assert not accepts_weekly_cron_registration_line("[Sedi Scheduler] Background scheduler started")
    stale = (
        "[Sedi Scheduler] weekly_international_knowledge_crawler registered "
        "interval_min=10080 enabled=True"
    )
    assert STALE_INTERVAL_GREP_ERE in stale
    assert not accepts_weekly_cron_registration_line(stale)
    for path in _WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert WORKFLOW_CRON_GREP_ERE in text, path
        assert "grep -Eq 'interval_min=10080'" not in text, path
        assert 'env_flag_equals "${FLAG_INT}" "10080"' in text, path
        assert ("fail_closed_recover_nhs" in text) or ("fail_closed_dormant" in text), path
    print("CRON_CONTRACT_TESTS=PASS")


if __name__ == "__main__":
    main()
