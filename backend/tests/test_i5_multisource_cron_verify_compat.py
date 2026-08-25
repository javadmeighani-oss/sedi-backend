"""PD-I5-V1-MULTISOURCE-ACTIVATION-CRON-VERIFY-COMPAT-01 targeted verifier tests."""
from __future__ import annotations

from pathlib import Path

from backend.tests.helpers.i5_weekly_cron_registration_verify import (
    STALE_INTERVAL_GREP_ERE,
    WORKFLOW_CRON_GREP_ERE,
    accepts_weekly_cron_registration_line,
    sample_valid_production_registration_line,
)

_REPO = Path(__file__).resolve().parents[2]
_WORKFLOWS = [
    _REPO / ".github" / "workflows" / "w6p01-prod-activate-weekly.yml",
    _REPO / ".github" / "workflows" / "i5-prod-multisource-weekly-activation.yml",
]


def test_A_valid_current_cron_line_pass() -> None:
    assert accepts_weekly_cron_registration_line(sample_valid_production_registration_line()) is True


def test_B_wrong_weekday_fail() -> None:
    line = sample_valid_production_registration_line().replace("day_of_week=fri", "day_of_week=mon")
    assert accepts_weekly_cron_registration_line(line) is False


def test_C_wrong_hour_or_minute_fail() -> None:
    bad_hour = sample_valid_production_registration_line().replace("hour=3", "hour=4")
    bad_min = sample_valid_production_registration_line().replace("minute=30", "minute=0")
    assert accepts_weekly_cron_registration_line(bad_hour) is False
    assert accepts_weekly_cron_registration_line(bad_min) is False


def test_D_wrong_timezone_fail() -> None:
    line = sample_valid_production_registration_line().replace("timezone=Asia/Tehran", "timezone=UTC")
    assert accepts_weekly_cron_registration_line(line) is False


def test_E_missing_registration_line_fail() -> None:
    assert accepts_weekly_cron_registration_line("") is False
    assert accepts_weekly_cron_registration_line("   ") is False
    assert accepts_weekly_cron_registration_line("[Sedi Scheduler] Background scheduler started") is False


def test_F_interval_only_historical_line_not_accepted() -> None:
    stale = (
        "[Sedi Scheduler] weekly_international_knowledge_crawler registered "
        "interval_min=10080 enabled=True"
    )
    assert accepts_weekly_cron_registration_line(stale) is False
    # Interval token alone must not satisfy cron contract.
    assert STALE_INTERVAL_GREP_ERE in stale
    assert accepts_weekly_cron_registration_line(stale) is False


def test_G_fail_closed_contract_still_present_in_workflows() -> None:
    for path in _WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        assert "fail_closed_recover_nhs" in text or "fail_closed_dormant" in text
        assert "SEDI_I5_MULTISOURCE_ENABLED" in text or "nhs_uk_live_well" in text
        # Cron contract installed; stale registration-line interval assert removed.
        assert WORKFLOW_CRON_GREP_ERE in text
        # Must not still require interval_min on the *registration line* check.
        assert (
            "grep -Eq 'interval_min=10080'" not in text
            and 'grep -Eq "interval_min=10080"' not in text
        )
        # Legacy env FLAG_INT=10080 may remain as config compatibility.
        assert 'env_flag_equals "${FLAG_INT}" "10080"' in text
