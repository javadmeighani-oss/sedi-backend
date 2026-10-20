"""R-011 item 4: wellbeing (mood/stress/energy/sleep/pain) on the existing I7 derived signals — counts only."""
from __future__ import annotations

import json
from types import SimpleNamespace

from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.i7 import derived_signals as ds
from backend.app.services.i7.hierarchy import build_daily_from_raw
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def _turns(*messages):
    return [SimpleNamespace(user_message=m) for m in messages]


def test_wellbeing_signal_counts_voiced_categories_in_fa_en_ar_without_text():
    sig = ds._wellbeing_signal(
        _turns(
            "امروز خیلی خسته‌ام و استرس دارم",
            "چند شبه خوابم نمیاد",
            "I'm so tired and my back hurts",
            "أشعر بالحزن وأبكي",
            "امروز خیلی خوب بود، خوشحالم",
        )
    )
    assert sig == {"fatigue": 2, "stress": 1, "sleep_issue": 1, "pain": 1, "low_mood": 1, "positive": 1}
    assert all(isinstance(v, int) for v in sig.values())
    assert ds._wellbeing_signal(_turns("سلام", "یه دستور غذا میخوام")) == {}


def test_merge_sums_wellbeing_over_days_for_medium_and_long_term():
    m = ds.merge_signals([{"wellbeing": {"low_mood": 2, "stress": 1}}, {}, {"wellbeing": {"low_mood": 1, "positive": 1}}])
    assert m["wellbeing"] == {"low_mood": 3, "stress": 1, "positive": 1, "days": 2}
    assert ds.merge_signals([{"topics": ["als"]}]).get("wellbeing") is None


def test_trend_decision_is_conservative():
    assert ds.decide_wellbeing_trend({"low_mood": 2, "stress": 1}) == {"trend": "low", "concerns": []}
    assert ds.decide_wellbeing_trend({"low_mood": 1, "stress": 1}) == {"trend": None, "concerns": []}
    assert ds.decide_wellbeing_trend({"positive": 3, "stress": 1})["trend"] == "good"
    assert ds.decide_wellbeing_trend({"low_mood": 3, "positive": 4})["trend"] == "good"
    assert ds.decide_wellbeing_trend({"sleep_issue": 2, "pain": 1}) == {"trend": None, "concerns": ["sleep_issue"]}


def test_recent_wellbeing_trend_reads_daily_summaries(db):
    u = _user(db, "+17770009411", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    row = build_daily_from_raw(db, u.id)
    payload = json.loads(row.structured_summary_json)
    payload["signals"] = {"wellbeing": {"low_mood": 3, "sleep_issue": 2}}
    row.structured_summary_json = json.dumps(payload)
    db.commit()
    assert ds.recent_wellbeing_trend(db, u.id) == {"trend": "low", "concerns": ["sleep_issue"]}


def test_persona_wellbeing_hint_is_bounded_unconfirmed_and_silent_without_signal():
    assert PersonaPolicyV1.wellbeing_hint(None, [], "fa") == ""
    for lang, marker in (("en", "unconfirmed"), ("fa", "تأییدنشده"), ("ar", "غير مؤكد")):
        hint = PersonaPolicyV1.wellbeing_hint("low", ["sleep_issue"], lang)
        assert marker in hint and len(hint) < 600
        assert "depress" not in hint.lower() and "افسرده" not in hint


def test_low_trend_engagement_copy_is_supportive_and_ignores_the_old_topic():
    from backend.app.services.notification_runtime.renderer import _ENGAGEMENT_LOW_PAIRS, render

    out = render("engagement", "fa", {"wellbeing_trend": "low", "last_topic_hint": "sleep"}, "low")
    assert out["title"] == _ENGAGEMENT_LOW_PAIRS["fa"][0][0]
    assert "sleep" not in out["body"]
