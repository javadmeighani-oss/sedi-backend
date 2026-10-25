"""R-021 / M2: smart extraction proposes, deterministic validation disposes (offline: the LLM call is injected)."""
from __future__ import annotations

import json

from backend.app import models
from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty
from backend.app.services.i7 import life_events as le
from backend.app.services.knowledge import llm_memory_extractor_v2 as x
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

HAIR = "خیلی سال هست که ریزش مو دارم و تا کنون دو بار مو کاشتم اما همچنان ریزش دارم"


def _llm(payload):
    return lambda _m: json.dumps(payload, ensure_ascii=False)


def _facts(db, uid):
    return {(f.domain, f.key): json.loads(f.value_json) for f in list_facts_readonly_or_empty(db, uid)}


def test_hair_loss_story_becomes_a_fact_and_a_timeline_event(db):
    u = _user(db, "+17770022001", tz="Asia/Tehran")
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    out = x.run_llm_extraction(db, u.id, HAIR, "fa", llm_call=_llm({
        "facts": [{"key": "health_concerns", "value": ["ریزش مو"], "evidence": "ریزش مو دارم"}],
        "events": [{"kind": "procedure", "subject": "self", "summary": "دو بار کاشت مو", "when": "", "evidence": "دو بار مو کاشتم"}],
    }))
    assert out == {"facts": 1, "events": 1}
    assert _facts(db, u.id)[("medical", "health_concerns")] == ["ریزش مو"]
    tl = le.list_life_events(db, u.id)
    assert tl[0]["kind"] == "procedure" and tl[0]["title"] == "دو بار کاشت مو" and tl[0]["subject"] == "self"


def test_unsupported_or_misattributed_items_are_dropped(db):
    u = _user(db, "+17770022002", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    msg = "مادرم دیابت داشت و من تازه شغلم رو عوض کردم"
    out = x.run_llm_extraction(db, u.id, msg, "fa", llm_call=_llm({
        "facts": [
            {"key": "health_concerns", "value": "دیابت", "evidence": "مادرم دیابت داشت"},   # relative's condition
            {"key": "health_concerns", "value": "فشار خون", "evidence": "فشار خون دارم"},   # evidence not in the message
            {"key": "occupation", "value": "پزشک", "evidence": "پزشک هستم"},               # invented
            {"key": "ssn", "value": "123", "evidence": "مادرم"},                            # key not allowed
            {"key": "family_history", "value": "مادر: دیابت", "evidence": "مادرم دیابت داشت"},  # the right home
        ],
        "events": [],
    }))
    assert out["facts"] == 1
    facts = _facts(db, u.id)
    assert facts[("medical", "family_history")] == ["مادر: دیابت"]
    assert ("medical", "health_concerns") not in facts and ("work", "occupation") not in facts


def test_family_loss_event_gets_subject_one_timeline_row_and_one_checkin(db):
    u = _user(db, "+17770022003", tz="Asia/Tehran")
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    msg = "مادرم دیروز فوت کرد و حالم خیلی بده"
    from backend.app.services.knowledge.conversation_extraction_service import process_message

    process_message(db, u.id, msg, "fa")  # the deterministic extractor already recorded the event (subject unknown)
    x.run_llm_extraction(db, u.id, msg, "fa", llm_call=_llm({
        "facts": [],
        "events": [{"kind": "loss", "subject": "mother", "summary": "فوت مادر", "when": "دیروز", "evidence": "مادرم دیروز فوت کرد"}],
    }))
    tl = le.list_life_events(db, u.id)
    assert len(tl) == 1 and tl[0]["subject"] == "mother" and tl[0]["title"] == "فوت مادر"
    assert db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).count() == 1


def test_no_consent_garbage_and_failures_store_nothing(db):
    u = _user(db, "+17770022004", tz="Asia/Tehran")  # no consent
    good = {"facts": [{"key": "occupation", "value": "معلم", "evidence": "معلم هستم"}], "events": []}
    assert x.run_llm_extraction(db, u.id, "من معلم هستم و دوست دارم", "fa", llm_call=_llm(good))["facts"] == 0
    assert not list_facts_readonly_or_empty(db, u.id)
    assert db.query(models.KcFactCandidate).filter(models.KcFactCandidate.user_id == u.id).count() == 0
    _seed_consent(db, u.id)
    for bad in ("not json", "[]", '{"facts": "x"}', ""):
        assert x.run_llm_extraction(db, u.id, "من معلم هستم و دوست دارم", "fa", llm_call=lambda _m, b=bad: b) == {"facts": 0, "events": 0}

    def boom(_m):
        raise RuntimeError("provider down")

    assert x.run_llm_extraction(db, u.id, "من معلم هستم و دوست دارم", "fa", llm_call=boom) == {"facts": 0, "events": 0}


def test_intake_facts_stated_in_chat_use_the_same_i6_keys_and_merge(db):
    u = _user(db, "+17770022005", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    for msg, key, val in (("به گردو حساسیت دارم و بادام زمینی هم", "allergies", ["گردو"]),
                          ("به بادام زمینی هم حساسیت دارم خیلی", "allergies", ["بادام زمینی"])):
        x.run_llm_extraction(db, u.id, msg, "fa", llm_call=_llm({"facts": [{"key": key, "value": val, "evidence": "حساسیت دارم"}], "events": []}))
    assert _facts(db, u.id)[("intake", "allergies")] == ["گردو", "بادام زمینی"]


def test_when_parser_and_scheduling_gates(monkeypatch):
    from datetime import datetime

    now = datetime(2026, 10, 24, 12, 0)
    assert x.parse_when("دیروز", now) == (datetime(2026, 10, 23, 12, 0), "day")
    assert x.parse_when("سال ۱۳۹۸", now)[1] == "year"
    assert x.parse_when("", now) == (now, "approx")
    monkeypatch.delenv("SEDI_MEMORY_LLM_EXTRACTION_ENABLED", raising=False)
    assert x.schedule_llm_extraction(1, "یک پیام به اندازه‌ی کافی طولانی برای استخراج", "fa") is False  # flag OFF
    monkeypatch.setenv("SEDI_MEMORY_LLM_EXTRACTION_ENABLED", "true")
    assert x.schedule_llm_extraction(1, "کوتاه", "fa") is False  # too short
    assert x._worth_extracting("آیا این درسته؟") is False
