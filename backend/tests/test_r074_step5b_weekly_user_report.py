"""R-074 step 5b (A): the unified weekly user report (offline; owners patched)."""
from __future__ import annotations

from datetime import date

import pytest

from backend.app import sedi_copy
from backend.app.services.i7 import user_done
from backend.app.services.i8 import weekly_review as wr
from backend.app.services.i8 import weekly_user_report as rep

TODAY = date(2026, 11, 8)


@pytest.fixture
def owners(monkeypatch):
    done = {
        date(2026, 11, 8): {"medication": 2, "nutrition": 1},
        date(2026, 11, 7): {"medication": 1},
        date(2026, 11, 2): {"exercise": 5},  # first day of the window
    }
    not_done = {
        date(2026, 11, 8): {"medication": 1, "reason.too_busy": 1},
        date(2026, 11, 5): {"nutrition": 2, "reason.too_busy": 1, "reason.tired": 1},
    }
    monkeypatch.setattr(user_done, "done_counts_for_day", lambda db, uid, day: dict(done.get(day, {})))
    monkeypatch.setattr(user_done, "not_done_counts_for_day", lambda db, uid, day: dict(not_done.get(day, {})))
    monkeypatch.setattr(
        wr, "build_weekly_review", lambda db, uid, domain, **kw: {"state": "ready", "percent": 60, "previous_percent": 40, "delta": 20, "done": 3, "skipped": 2, "total": 7, "extra": "x"}
    )


def test_the_week_adds_up_by_domain_and_totals(owners):
    r = rep.build_weekly_user_report(object(), 7, language="en", today=TODAY)
    assert r["state"] == "ready" and r["week_start"] == "2026-11-02" and r["week_end"] == "2026-11-08"
    assert r["by_domain"]["medication"] == {"done": 3, "not_done": 1, "percent": 75}
    assert r["by_domain"]["nutrition"] == {"done": 1, "not_done": 2, "percent": 33}
    assert r["by_domain"]["exercise"] == {"done": 5, "not_done": 0, "percent": 100}
    assert r["totals"] == {"done": 9, "not_done": 3, "percent": 75}


def test_reasons_are_split_out_and_ordered_by_count(owners):
    r = rep.build_weekly_user_report(object(), 7, language="en", today=TODAY)
    assert list(r["reasons"].items()) == [("too_busy", 2), ("tired", 1)]
    assert "reason.too_busy" not in r["by_domain"]


def test_the_plan_reviews_are_included_with_only_the_public_fields(owners):
    r = rep.build_weekly_user_report(object(), 7, language="en", today=TODAY)
    assert set(r["plans"]) == {"nutrition", "exercise"}
    assert r["plans"]["nutrition"]["percent"] == 60 and r["plans"]["nutrition"]["delta"] == 20
    assert "extra" not in r["plans"]["nutrition"]


def test_a_week_without_anything_marked_is_empty_with_the_quiet_message(monkeypatch):
    monkeypatch.setattr(user_done, "done_counts_for_day", lambda *a: {})
    monkeypatch.setattr(user_done, "not_done_counts_for_day", lambda *a: {})
    monkeypatch.setattr(wr, "build_weekly_review", lambda *a, **k: {"state": "empty"})
    for lang in ("fa", "ar", "en"):
        r = rep.build_weekly_user_report(object(), 7, language=lang, today=TODAY)
        assert r["state"] == "empty" and r["totals"] == {"done": 0, "not_done": 0, "percent": None}
        assert r["message"] == sedi_copy.t("weekly_report.summary.quiet", lang)


def test_the_active_message_carries_the_real_numbers_in_every_language(owners):
    for lang in ("fa", "ar", "en"):
        m = rep.build_weekly_user_report(object(), 7, language=lang, today=TODAY)["message"]
        assert "9" in m and "3" in m and "{" not in m


def test_one_failing_part_does_not_hide_the_rest(owners, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("plan down")

    monkeypatch.setattr(wr, "build_weekly_review", boom)
    r = rep.build_weekly_user_report(object(), 7, language="en", today=TODAY)
    assert r["state"] == "ready" and r["plans"]["nutrition"] == {"state": "unavailable"}


def test_a_failing_day_is_skipped_not_fatal(monkeypatch):
    calls = {"n": 0}

    def flaky(db, uid, day):
        calls["n"] += 1
        if day == date(2026, 11, 6):
            raise RuntimeError("x")
        return {"medication": 1}

    monkeypatch.setattr(user_done, "done_counts_for_day", flaky)
    monkeypatch.setattr(user_done, "not_done_counts_for_day", lambda *a: {})
    monkeypatch.setattr(wr, "build_weekly_review", lambda *a, **k: {"state": "empty"})
    r = rep.build_weekly_user_report(object(), 7, language="en", today=TODAY)
    assert r["totals"]["done"] == 6 and calls["n"] == 7


def test_the_route_exists_and_is_owner_scoped():
    import inspect

    from backend.app.routers import lifestyle

    src = inspect.getsource(lifestyle.lifestyle_weekly_report)
    assert "get_current_user" in inspect.getsource(lifestyle) and "auth_user.id" in src
