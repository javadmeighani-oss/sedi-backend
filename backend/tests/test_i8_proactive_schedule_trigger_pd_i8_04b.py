"""PD-I8-04B: trusted schedule trigger + flag-gated bounded scan foundation tests."""

from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services.i8.evaluation_identity import build_evaluation_identity_key
from backend.app.services.i8.feature_flags import (
    I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV,
    I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG,
    i8_proactive_schedule_scan_batch_size,
    i8_proactive_schedule_scan_interval_minutes,
    i8_proactive_schedule_trigger_enabled,
)
from backend.app.services.i8.schedule_adapter import adapt_trusted_schedule_trigger
from backend.app.services.i8.schedule_rules import (
    DEFAULT_V1_SCHEDULE_RULE_ID,
    SCHEDULE_RULE_ALLOWLIST_V1,
    SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
    is_allowed_schedule_rule,
)
from backend.app.services.i8.schedule_scan import (
    I8_SCHEDULE_SCAN_JOB_ID,
    apply_schedule_scan_cursor_progression,
    get_schedule_scan_cursor,
    iter_eligible_schedule_user_ids,
    reset_schedule_scan_cursors,
    run_i8_proactive_schedule_scan,
)
from backend.app.services.i8.trusted_trigger import (
    TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
    TrustedTriggerV1,
    TrustedTriggerValidationError,
    validate_trusted_schedule_trigger,
)


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, raising=False)
    assert i8_proactive_schedule_trigger_enabled() is False


def test_feature_flag_on(monkeypatch):
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, "true")
    assert i8_proactive_schedule_trigger_enabled() is True


def test_batch_size_bounds(monkeypatch):
    monkeypatch.delenv("SEDI_I8_PROACTIVE_SCHEDULE_SCAN_BATCH_SIZE", raising=False)
    assert i8_proactive_schedule_scan_batch_size() == 50
    monkeypatch.setenv("SEDI_I8_PROACTIVE_SCHEDULE_SCAN_BATCH_SIZE", "999")
    assert i8_proactive_schedule_scan_batch_size() == 200
    monkeypatch.setenv("SEDI_I8_PROACTIVE_SCHEDULE_SCAN_BATCH_SIZE", "0")
    assert i8_proactive_schedule_scan_batch_size() == 1


def test_cadence_config_bounds_and_fallback(monkeypatch):
    monkeypatch.delenv(I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV, raising=False)
    assert i8_proactive_schedule_scan_interval_minutes() == 15
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV, "30")
    assert i8_proactive_schedule_scan_interval_minutes() == 30
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV, "1")
    assert i8_proactive_schedule_scan_interval_minutes() == 5
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV, "99999")
    assert i8_proactive_schedule_scan_interval_minutes() == 1440
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_SCAN_INTERVAL_ENV, "abc")
    assert i8_proactive_schedule_scan_interval_minutes() == 15


def test_schedule_rule_allowlist():
    assert SCHEDULE_RULE_DAILY_WELLBEING_CHECK in SCHEDULE_RULE_ALLOWLIST_V1
    assert is_allowed_schedule_rule(DEFAULT_V1_SCHEDULE_RULE_ID)
    assert not is_allowed_schedule_rule("free_form_rule")
    assert not is_allowed_schedule_rule("")


def test_trusted_trigger_validation_and_identity():
    d = date(2026, 8, 22)
    ok = TrustedTriggerV1(
        producer_id=TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
        user_id=7,
        trigger_family="schedule",
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=d,
        producer_attempt_id="attempt-1",
        bounded_metadata={"timezone_snapshot": "Asia/Tehran"},
    )
    trusted = validate_trusted_schedule_trigger(ok)
    assert trusted.canonical_identity_parts() == (
        "schedule",
        7,
        SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        "2026-08-22",
    )
    key_a = build_evaluation_identity_key(
        trigger_family="schedule",
        user_id=7,
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=d,
    )
    key_b = build_evaluation_identity_key(
        trigger_family="schedule",
        user_id=7,
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=d,
    )
    assert key_a == key_b
    assert key_a == build_evaluation_identity_key(
        trigger_family="schedule",
        user_id=trusted.user_id,
        schedule_rule_id=trusted.schedule_rule_id,
        user_local_date=trusted.user_local_date,
    )


@pytest.mark.parametrize(
    "bad",
    [
        dict(producer_id="evil"),
        dict(user_id=0),
        dict(trigger_family="event"),
        dict(schedule_rule_id="not_allowed"),
        dict(producer_attempt_id=""),
        dict(bounded_metadata={"notification_title": "x"}),
    ],
)
def test_trusted_trigger_rejects_untrusted(bad):
    base = dict(
        producer_id=TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
        user_id=1,
        trigger_family="schedule",
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=date(2026, 8, 22),
        producer_attempt_id="a1",
        bounded_metadata={},
    )
    base.update(bad)
    with pytest.raises(TrustedTriggerValidationError):
        validate_trusted_schedule_trigger(TrustedTriggerV1(**base))


def test_adapter_delegates_to_orchestrator(monkeypatch):
    calls = {}

    def _fake_eval(db, **kwargs):
        calls.update(kwargs)
        return SimpleNamespace(
            status="NO_ACTION",
            outcome="NO_ACTION",
            reused=False,
            evaluation_identity_key="k",
        )

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_adapter.evaluate_proactive_trigger",
        _fake_eval,
    )
    trigger = TrustedTriggerV1(
        producer_id=TRUSTED_PRODUCER_I8_SCHEDULE_SCAN_V1,
        user_id=42,
        trigger_family="schedule",
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=date(2026, 8, 22),
        producer_attempt_id="a",
    )
    result = adapt_trusted_schedule_trigger(MagicMock(), trigger)
    assert result.outcome == "NO_ACTION"
    assert calls["user_id"] == 42
    assert calls["trigger_family"] == "schedule"
    assert calls["schedule_rule_id"] == SCHEDULE_RULE_DAILY_WELLBEING_CHECK
    assert calls["user_local_date"] == date(2026, 8, 22)


def test_flag_off_zero_scan(monkeypatch):
    monkeypatch.delenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, raising=False)
    db = MagicMock()
    stats = run_i8_proactive_schedule_scan(db)
    assert stats.flag_enabled is False
    assert stats.eligible_scanned == 0
    assert stats.trigger_attempts == 0
    assert stats.evaluation_success == 0
    db.query.assert_not_called()


def test_bounded_keyset_query_uses_limit():
    db = MagicMock()
    query = db.query.return_value
    filtered = query.filter.return_value
    ordered = filtered.order_by.return_value
    ordered.limit.return_value.all.return_value = [(10,), (20,)]
    ids = iter_eligible_schedule_user_ids(db, after_user_id=5, limit=2)
    assert ids == [10, 20]
    ordered.limit.assert_called_once_with(2)


def test_flag_on_scan_isolates_failures(monkeypatch):
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, "1")
    db = MagicMock()

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.iter_eligible_schedule_user_ids",
        lambda *_a, **_k: [1, 2, 3],
    )

    def _window(_db, user_id, *, now_utc=None):
        return SimpleNamespace(
            user_local_date=date(2026, 8, 22),
            timezone_snapshot="Asia/Tehran",
        )

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.resolve_local_day_window",
        _window,
    )

    def _adapt(_db, trigger):
        if trigger.user_id == 2:
            raise RuntimeError("boom")
        return SimpleNamespace(
            status="NO_ACTION",
            outcome="NO_ACTION",
            reused=False,
        )

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.adapt_trusted_schedule_trigger",
        _adapt,
    )
    stats = run_i8_proactive_schedule_scan(db, batch_size=10)
    assert stats.flag_enabled is True
    assert stats.eligible_scanned == 3
    assert stats.trigger_attempts == 3
    assert stats.evaluation_success == 2
    assert stats.isolated_failures == 1
    assert stats.no_action == 2
    assert stats.completed is True
    assert stats.next_after_user_id == 3


def test_scheduler_registers_i8_schedule_job():
    from backend.app.core import scheduler as sched_mod

    src = inspect.getsource(sched_mod.start_scheduler)
    assert "I8_SCHEDULE_SCAN_JOB_ID" in src
    assert "run_i8_proactive_schedule_scan_job" in src
    assert "max_instances=1" in src
    assert "coalesce=True" in src
    assert "I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG" in src
    assert "i8_proactive_schedule_scan_interval_minutes" in src
    assert I8_SCHEDULE_SCAN_JOB_ID == "i8_proactive_schedule_scan_v1"
    assert I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG == "SEDI_I8_PROACTIVE_SCHEDULE_TRIGGER_ENABLED"
    # I8 job must not hard-code product cadence.
    i8_block = src.split("PD-I8-04B", 1)[1].split("scheduler.start()", 1)[0]
    assert "minutes=15" not in i8_block
    assert "minutes=i8_scan_interval_min" in i8_block


def test_adapter_source_has_no_decision_engine():
    from backend.app.services.i8 import schedule_adapter, schedule_scan

    for mod in (schedule_adapter, schedule_scan):
        src = inspect.getsource(mod)
        assert "generate_operational_action" not in src
        assert "retrieve_governed_knowledge" not in src
        assert "notification_title" not in src


def test_multi_tick_fair_progression_and_wrap(monkeypatch):
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, "1")
    reset_schedule_scan_cursors()
    rule = SCHEDULE_RULE_DAILY_WELLBEING_CHECK
    pages = {
        0: [1, 2],
        2: [3, 4],
        4: [5],
        5: [],
    }
    seen_pages: list[list[int]] = []

    def _iter(_db, *, after_user_id=0, limit=2):
        page = list(pages.get(int(after_user_id), []))
        seen_pages.append(page)
        assert len(page) <= limit
        return page

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.iter_eligible_schedule_user_ids",
        _iter,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.resolve_local_day_window",
        lambda *_a, **_k: SimpleNamespace(
            user_local_date=date(2026, 8, 22),
            timezone_snapshot="Asia/Tehran",
        ),
    )
    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.adapt_trusted_schedule_trigger",
        lambda *_a, **_k: SimpleNamespace(
            status="NO_ACTION", outcome="NO_ACTION", reused=False
        ),
    )

    ticks = []
    for _ in range(4):
        cursor = get_schedule_scan_cursor(rule)
        stats = run_i8_proactive_schedule_scan(
            MagicMock(), after_user_id=cursor, batch_size=2, schedule_rule_id=rule
        )
        stats = apply_schedule_scan_cursor_progression(schedule_rule_id=rule, stats=stats)
        ticks.append(
            (
                list(seen_pages[-1]),
                stats.cursor_after,
                stats.cursor_wrapped,
                stats.eligible_scanned,
            )
        )

    assert ticks[0][0] == [1, 2] and ticks[0][1] == 2 and ticks[0][2] is False
    assert ticks[1][0] == [3, 4] and ticks[1][1] == 4 and ticks[1][2] is False
    assert ticks[2][0] == [5] and ticks[2][1] == 5 and ticks[2][2] is False
    assert ticks[3][0] == [] and ticks[3][1] == 0 and ticks[3][2] is True
    reachable = {u for page, *_ in ticks for u in page}
    assert reachable == {1, 2, 3, 4, 5}
    assert seen_pages[0] != seen_pages[1]
    assert get_schedule_scan_cursor(rule) == 0


def test_flag_off_does_not_move_cursor(monkeypatch):
    monkeypatch.delenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, raising=False)
    reset_schedule_scan_cursors()
    rule = SCHEDULE_RULE_DAILY_WELLBEING_CHECK
    from backend.app.services.i8.schedule_scan import set_schedule_scan_cursor

    set_schedule_scan_cursor(rule, 42)
    stats = run_i8_proactive_schedule_scan(
        MagicMock(), after_user_id=42, schedule_rule_id=rule
    )
    stats = apply_schedule_scan_cursor_progression(schedule_rule_id=rule, stats=stats)
    assert stats.flag_enabled is False
    assert stats.cursor_unchanged is True
    assert stats.cursor_advanced is False
    assert get_schedule_scan_cursor(rule) == 42


def test_partial_failure_still_advances_page(monkeypatch):
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, "1")
    reset_schedule_scan_cursors()
    rule = SCHEDULE_RULE_DAILY_WELLBEING_CHECK
    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.iter_eligible_schedule_user_ids",
        lambda *_a, **_k: [10, 20],
    )
    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.resolve_local_day_window",
        lambda *_a, **_k: SimpleNamespace(
            user_local_date=date(2026, 8, 22),
            timezone_snapshot="Asia/Tehran",
        ),
    )

    def _adapt(_db, trigger):
        if trigger.user_id == 10:
            raise RuntimeError("isolated")
        return SimpleNamespace(status="NO_ACTION", outcome="NO_ACTION", reused=False)

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.adapt_trusted_schedule_trigger",
        _adapt,
    )
    stats = run_i8_proactive_schedule_scan(
        MagicMock(), after_user_id=0, batch_size=2, schedule_rule_id=rule
    )
    stats = apply_schedule_scan_cursor_progression(schedule_rule_id=rule, stats=stats)
    assert stats.isolated_failures == 1
    assert stats.evaluation_success == 1
    assert stats.cursor_after == 20
    assert get_schedule_scan_cursor(rule) == 20


def test_catastrophic_query_failure_does_not_advance(monkeypatch):
    monkeypatch.setenv(I8_PROACTIVE_SCHEDULE_TRIGGER_FLAG, "1")
    reset_schedule_scan_cursors()
    rule = SCHEDULE_RULE_DAILY_WELLBEING_CHECK
    from backend.app.services.i8.schedule_scan import set_schedule_scan_cursor

    set_schedule_scan_cursor(rule, 7)

    def _boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "backend.app.services.i8.schedule_scan.iter_eligible_schedule_user_ids",
        _boom,
    )
    with pytest.raises(RuntimeError):
        run_i8_proactive_schedule_scan(
            MagicMock(), after_user_id=7, schedule_rule_id=rule
        )
    assert get_schedule_scan_cursor(rule) == 7


def test_retry_same_schedule_identity_stable():
    d = date(2026, 8, 22)
    a = build_evaluation_identity_key(
        trigger_family="schedule",
        user_id=9,
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=d,
    )
    b = build_evaluation_identity_key(
        trigger_family="schedule",
        user_id=9,
        schedule_rule_id=SCHEDULE_RULE_DAILY_WELLBEING_CHECK,
        user_local_date=d,
    )
    assert a == b
