"""R-014 "second memory": explicit user statements are remembered (I6) and reach the model; nothing is invented."""
from __future__ import annotations

import json

import pytest

from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.knowledge.stated_facts_extractor_v1 import extract_stated_facts
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def _pairs(text):
    return {(f.fact_key, str(f.fact_value)) for f in extract_stated_facts(text)}


def test_own_conditions_are_extracted_only_when_explicit():
    assert ("health_concerns", "دیابت") in _pairs("من دیابت دارم و می‌خوام رژیم بگیرم")
    assert ("health_concerns", "فشار خون بالا") in _pairs("فشار خون بالا دارم")
    assert ("health_concerns", "diabetes") in _pairs("I have diabetes")
    # questions, negations, conditionals never become facts
    assert not _pairs("آیا دیابت دارم؟")
    assert not _pairs("دیابت ندارم")
    assert not _pairs("اگه دیابت داشته باشم چی می‌شه")
    # hedged statements stay below the auto-accept threshold
    hedged = extract_stated_facts("فکر کنم دیابت دارم")
    assert hedged and all(f.confidence < 0.85 for f in hedged)


def test_family_history_is_attributed_to_the_relative_not_the_user():
    got = _pairs("مادرم دیابت داشت")
    assert ("family_history", "مادر: دیابت") in got
    assert not any(k == "health_concerns" for k, _v in got)
    assert ("family_history", "father: heart disease") in _pairs("my father had heart disease")


def test_job_household_interest_sleep():
    assert ("occupation_stated", "معلم") in _pairs("من معلمم و خیلی خسته می‌شم")
    assert ("household_context", "تنها زندگی می‌کند") in _pairs("من تنها زندگی می‌کنم")
    assert ("interests", "کوهنوردی") in _pairs("به کوهنوردی علاقه دارم")
    assert ("sleep_duration_hours", "6") in _pairs("شب‌ها ۶ ساعت می‌خوابم")


def test_statements_are_remembered_merged_and_projected_to_the_model(db):
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty
    from backend.app.services.intelligence.adapters import HealthContextAdapter

    u = _user(db, "+17770014001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    process_message(db, u.id, "من دیابت دارم", "fa")
    process_message(db, u.id, "فشار خون بالا هم دارم", "fa")
    process_message(db, u.id, "مادرم دیابت داشت", "fa")

    by_key = {(r.domain, r.key): json.loads(r.value_json) for r in list_facts_readonly_or_empty(db, u.id, domain="medical")}
    assert by_key[("medical", "health_concerns")] == ["دیابت", "فشار خون بالا"]
    assert by_key[("medical", "family_history")] == ["مادر: دیابت"]

    items = HealthContextAdapter().load(db, authenticated_user_id=u.id)
    lines = {i.canonical_key: i.display_text for i in items}
    assert any(k.startswith("health.condition.") and "دیابت" in v for k, v in lines.items())
    assert any(k.startswith("health.condition.") and "فشار خون" in v for k, v in lines.items())
    assert lines["health.stated_family_history"].endswith("مادر: دیابت")


def test_nothing_is_stored_without_memory_consent(db):
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

    u = _user(db, "+17770014002", tz="Asia/Tehran")  # no consent seeded
    process_message(db, u.id, "من دیابت دارم", "fa")
    assert not [r for r in list_facts_readonly_or_empty(db, u.id, domain="medical") if r.key == "health_concerns"]


def test_profile_summary_shows_what_sedi_remembers(db):
    from backend.app.services.profile.a3_profile_summary import build_a3_profile_summary

    u = _user(db, "+17770014003", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    assert build_a3_profile_summary(db, u.id)["facts"] == []
    process_message(db, u.id, "من دیابت دارم", "fa")
    process_message(db, u.id, "من معلمم", "fa")
    facts = {f["key"]: f["value"] for f in build_a3_profile_summary(db, u.id)["facts"]}
    assert facts == {"health_concerns": "دیابت", "occupation": "معلم"}


def test_recap_falls_back_to_what_sedi_remembers_and_keeps_lock_screen_generic(db):
    from backend.app.services.i7 import conversation_recap as cr

    u = _user(db, "+17770014004", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    assert cr.recap_topic(db, u.id, "fa") is None
    process_message(db, u.id, "من دیابت دارم", "fa")
    assert cr.recap_topic(db, u.id, "fa", privacy="in_app") == "بیماری دیابت"
    lock = cr.recap_topic(db, u.id, "fa", privacy="lock_screen")
    assert lock and "دیابت" not in lock
