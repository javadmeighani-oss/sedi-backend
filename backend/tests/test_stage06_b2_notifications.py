"""Stage 06 / B2-D4: plan-aware notifications (timed localized reminders, progress digest, feedback throttling)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.i10 import plan_progress as pp
from backend.app.services.i10.coaching_worker import _composer_item_due
from backend.app.services.i10.daily_wellness_digest import _plan_progress_body, _PLAN_TITLES
from backend.app.services.i10.plan_reminder_copy import composer_copy
from backend.app.services.i10.coaching_followup_types import CoachingPlanDomain
from backend.app.services.i8 import plan_composer as pc
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

NOW = datetime(2026, 10, 19, 12, 0, 0)


def _fb(action, reason=None, hours_ago=1):
    meta = '{"reason": "%s"}' % reason if reason else None
    return SimpleNamespace(action=action, meta_json=meta, created_at=NOW - timedelta(hours=hours_ago))


# ---------- feedback throttling ----------
def test_feedback_state_rules():
    """R-023: reactions ADAPT the digest (time slot, text type); `skip` is never True."""
    empty = pp.state_from_feedback([], NOW)
    assert empty == {"skip": False, "shift_time": False, "avoid_generic": False, "simple": False, "dislikes_7d": 0}
    assert pp.state_from_feedback([_fb("like")], NOW)["skip"] is False
    freq = pp.state_from_feedback([_fb("dislike", "too_frequent")], NOW)
    assert freq["skip"] is False and freq["shift_time"] is True
    timing = pp.state_from_feedback([_fb("dislike", "wrong_timing", hours_ago=24 * 5)], NOW)
    assert timing["skip"] is False and timing["shift_time"] is True
    irrelevant = pp.state_from_feedback([_fb("dislike", "irrelevant")], NOW)
    assert irrelevant["avoid_generic"] is True and irrelevant["skip"] is False and irrelevant["shift_time"] is False
    unclear = pp.state_from_feedback([_fb("dislike", "unclear")], NOW)
    assert unclear["simple"] is True and unclear["skip"] is False
    many = pp.state_from_feedback([_fb("dislike")] * 3, NOW)
    assert many["skip"] is False and many["simple"] is True and many["avoid_generic"] is True and many["dislikes_7d"] == 3


def test_digest_slot_moves_after_a_timing_dislike_and_never_disappears(db):
    """R-023: a wrong_timing / too_frequent dislike moves the digest to the evening slot - it is never dropped."""
    from backend.app.models import Notification, NotificationFeedback, User

    u = User(name="Slot User", secret_key="slot-u", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    assert pp.preferred_digest_local_time(db, u.id) == pp.DEFAULT_DIGEST_LOCAL_TIME
    n = Notification(user_id=u.id, type="DAILY_WELLNESS_DIGEST", title="T", body="B", priority="normal",
                     is_read=False, is_sent=True, created_at=datetime.utcnow())
    db.add(n)
    db.commit()
    db.refresh(n)
    db.add(NotificationFeedback(notification_id=n.id, user_id=u.id, action="dislike",
                                meta_json='{"reason": "wrong_timing"}', created_at=datetime.utcnow()))
    db.commit()
    assert pp.preferred_digest_local_time(db, u.id) == pp.SHIFTED_DIGEST_LOCAL_TIME


# ---------- time-aware reminders ----------
def _act(local_time, source="sedi_plan_catalog_v1", vf=datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)):
    pres = '{"source": "%s", "local_time": %s}' % (source, '"%s"' % local_time if local_time else "null")
    return SimpleNamespace(presentation_json=pres, valid_from=vf)


def test_composer_items_are_reminded_at_their_own_time_only():
    t = lambda h, m=0: datetime(2026, 10, 19, h, m, tzinfo=timezone.utc)
    a = _act("13:00")
    assert not _composer_item_due(a, t(12, 59))
    assert _composer_item_due(a, t(13, 0)) and _composer_item_due(a, t(15, 59))
    assert not _composer_item_due(a, t(16, 1))
    assert not _composer_item_due(_act(None), t(13, 0))  # rest day: never
    assert _composer_item_due(_act("13:00", source="other"), t(1, 0))  # legacy actions unchanged


@pytest.mark.parametrize("lang,needle", [("fa", "انجام شد"), ("en", "done"), ("ar", "تم")])
def test_reminder_copy_is_localized_timed_and_brand_safe(db, lang, needle):
    u = _user(db, f"+1777000931{lang == 'fa'}{lang == 'en'}", tz="Asia/Tehran")
    u.preferred_language = lang
    db.commit()
    act = SimpleNamespace(
        user_id=u.id,
        presentation_json='{"source": "sedi_plan_catalog_v1", "local_time": "13:00", "meal_slot": "lunch"}',
    )
    title, body, key = composer_copy(db, act, CoachingPlanDomain.NUTRITION, None, "Lentil soup")
    assert "(13:00)" in body and needle in body and "Lentil soup" in body and key == "nutrition_plan_follow_up"
    assert "سدی" not in title + body
    assert composer_copy(db, SimpleNamespace(user_id=u.id, presentation_json="{}"), CoachingPlanDomain.NUTRITION, None, "x") is None


# ---------- digest copy ----------
@pytest.mark.parametrize("lang", ["fa", "en", "ar"])
def test_digest_progress_copy_morning_and_evening(lang):
    p = {"done": 2, "skipped": 1, "pending": 1, "total": 4, "next": ["20:00 Dinner"]}
    morning = _plan_progress_body(p, "morning", lang)
    evening = _plan_progress_body(p, "evening", lang)
    assert "4" in morning and "20:00" in morning
    assert "2" in evening and "4" in evening and morning != evening
    assert _PLAN_TITLES["evening"][lang] != _PLAN_TITLES["morning"][lang]
    assert "سدی" not in morning + evening


# ---------- day progress (DB) ----------
def test_day_progress_counts_done_skipped_pending(db):
    from backend.app.services.i8.action_review import record_review
    from backend.app.services.lifestyle.a3_weekly_plan_projection import build_lifestyle_weekly_plan_projection

    u = _user(db, "+17770009351", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=pc.Constraints())
    proj = build_lifestyle_weekly_plan_projection(db, u.id)
    day = proj["days"][0]
    from datetime import date

    local = date.fromisoformat(day["local_date"])
    assert pp.day_progress(db, u.id, local)["total"] == 4
    record_review(db, actor_user_id=u.id, action_id=day["nutrition"][0]["id"], outcome="done")
    record_review(db, actor_user_id=u.id, action_id=day["nutrition"][1]["id"], outcome="skipped", reason="forgot")
    p = pp.day_progress(db, u.id, local)
    assert (p["done"], p["skipped"], p["pending"], p["total"]) == (1, 1, 2, 4) and len(p["next"]) == 2
    assert pp.day_progress(db, u.id, local + timedelta(days=30)) is None
