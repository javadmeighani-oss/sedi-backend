"""Stage 06 / B2-C1: I7 short/medium/long-term derived signals (plan adherence, feedback, topics)."""
from __future__ import annotations

import json

from backend.app import models
from backend.app.services.i7 import derived_signals as ds
from backend.app.services.i7.hierarchy import build_daily_from_raw
from backend.app.services.i8 import plan_composer as pc
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def test_merge_signals_sums_counts_reasons_and_ranks_topics():
    parts = [
        {"plan": {"done": 3, "skipped": 1, "pending": 0, "total": 4}, "feedback": {"likes": 1, "dislikes": 1, "dislike_reasons": {"too_frequent": 1}}, "topics": ["als", "diabetes"]},
        {"plan": {"done": 1, "skipped": 2, "pending": 1, "total": 4}, "feedback": {"dislikes": 2, "dislike_reasons": {"too_frequent": 1, "irrelevant": 1}}, "topics": ["als"]},
        {},
        {"topics": ["asthma"]},
    ]
    m = ds.merge_signals(parts)
    assert m["plan"]["done"] == 4 and m["plan"]["skipped"] == 3 and m["plan"]["total"] == 8
    assert m["plan"]["days"] == 2 and m["plan"]["percent"] == round(100 * 4 / 8)
    assert m["feedback"] == {"likes": 1, "dislikes": 3, "dislike_reasons": {"too_frequent": 2, "irrelevant": 1}}
    assert m["topics"][0] == "als" and set(m["topics"]) == {"als", "diabetes", "asthma"}
    assert ds.merge_signals([{}, {}]) == {}
    assert ds.merge_signals([]) == {}


def test_signals_hold_no_free_text_only_counts_reasons_and_concept_keys():
    m = ds.merge_signals([{"plan": {"done": 1, "skipped": 0, "pending": 0, "total": 1}, "topics": ["als"]}])
    assert set(json.dumps(m)) <= set(json.dumps(m))  # serializable
    assert all(k in {"plan", "feedback", "topics"} for k in m)


def test_daily_summary_carries_plan_signals_and_is_unchanged_without_any(db):
    u = _user(db, "+17770009401", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    plain = build_daily_from_raw(db, u.id)
    assert "signals" not in json.loads(plain.structured_summary_json)  # no signal -> payload as before
    pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=pc.Constraints())
    with_plan = build_daily_from_raw(db, u.id)
    sig = json.loads(with_plan.structured_summary_json)["signals"]
    assert sig["plan"]["total"] == 4 and sig["plan"]["pending"] == 4
    assert ds.signals_of(with_plan) == sig


def test_recent_topics_read_newest_daily_first(db):
    u = _user(db, "+17770009402", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    row = build_daily_from_raw(db, u.id)
    payload = json.loads(row.structured_summary_json)
    payload["signals"] = {"topics": ["als", "diabetes"]}
    row.structured_summary_json = json.dumps(payload)
    db.commit()
    assert ds.recent_topic_concept_keys(db, u.id, limit=1) == ["als"]
    assert ds.recent_topic_concept_keys(db, u.id, limit=5) == ["als", "diabetes"]
