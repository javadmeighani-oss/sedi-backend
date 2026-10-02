"""CR-04C — I7 longitudinal semantic understanding (derived-only, no runtime wiring)."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

import json
import inspect

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import correct_fact, delete_fact, write_fact
from backend.app.services.i7.lifelong_profile import (
    GENERATOR_VERSION,
    SEMANTIC_PROFILE_VERSION,
    rebuild_lifelong_profile,
)
from backend.app.services.i8.context import (
    I8_PERSONAL_CONTEXT_TERM_SLICE,
    _bounded_i7_terms,
)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _payload(profile: models.UserLifelongProfile) -> dict:
    return json.loads(profile.structured_profile_json)


def _semantic(profile: models.UserLifelongProfile) -> dict:
    return _payload(profile)["semantic_profile"]


def _find_entry(groups: dict, canonical_key: str) -> dict | None:
    for name, entries in groups.items():
        if name == "version":
            continue
        for entry in entries or []:
            if entry.get("canonical_key") == canonical_key:
                return entry
    return None


def test_cr04c_top_level_compatibility_preserved(db):
    user = _user(db, "compat")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "vegetarian", commit=True)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    write_fact(db, user.id, "goals", "health_goals", "walk more", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    payload = _payload(profile)
    for key in (
        "authority",
        "profile_is_derived_only",
        "not_diagnosis",
        "generator_version",
        "fact_count",
        "keys",
        "habits",
        "preferences",
        "goals",
    ):
        assert key in payload
    assert payload["authority"] == "I6_FACTS_ARE_SOT"
    assert payload["profile_is_derived_only"] is True
    assert payload["not_diagnosis"] is True
    assert payload["generator_version"] == GENERATOR_VERSION
    assert "lifestyle.food_habits" in payload["habits"]
    assert "preferences.response_length" in payload["preferences"]
    assert "goals.health_goals" in payload["goals"]
    assert isinstance(payload["habits"], list)
    assert all(isinstance(x, str) for x in payload["habits"])


def test_cr04c_work_schedule_medium_semantic_with_source_id(db):
    user = _user(db, "work-sem")
    grant_memory_consent(db, user.id, commit=True)
    fact = write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        "night shifts",
        source="relationship_discovery",
        commit=True,
    )
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    sem = _semantic(profile)
    assert sem["version"] == SEMANTIC_PROFILE_VERSION
    entry = _find_entry(sem, "work.work_schedule")
    assert entry is not None
    assert entry["sensitivity"] == "medium"
    assert entry["source_fact_id"] == fact.id
    assert entry["value_compact"] == "night shifts"
    assert entry["change_state"] == "current"
    assert entry["supersedes_fact_id"] is None
    assert entry in sem["work_context"]


def test_cr04c_preferences_and_routines_safe_medium(db):
    user = _user(db, "pref-routine")
    grant_memory_consent(db, user.id, commit=True)
    pref = write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    routine = write_fact(db, user.id, "routines", "bedtime", "11:00 pm", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    sem = _semantic(profile)
    pref_e = _find_entry(sem, "preferences.response_length")
    bed_e = _find_entry(sem, "routines.bedtime")
    assert pref_e is not None and pref_e["value_compact"] == "brief"
    assert pref_e["source_fact_id"] == pref.id
    assert pref_e in sem["interaction_preferences"]
    assert bed_e is not None and "11:00" in bed_e["value_compact"]
    assert bed_e["source_fact_id"] == routine.id
    assert bed_e in sem["routines"]


def test_cr04c_high_sensitivity_metadata_only_no_raw(db):
    user = _user(db, "high-sens")
    grant_memory_consent(db, user.id, commit=True)
    raw_barrier = "I only have 20 minutes after work"
    raw_social = "family support network secret"
    raw_values = "faith community priority"
    b = write_fact(db, user.id, "barriers", "time_constraints", raw_barrier, commit=True)
    write_fact(db, user.id, "social", "support_network", raw_social, commit=True)
    write_fact(db, user.id, "values", "important_values", raw_values, commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    blob = profile.structured_profile_json or ""
    narrative = profile.narrative_compact or ""
    assert raw_barrier not in blob
    assert raw_social not in blob
    assert raw_values not in blob
    assert raw_barrier not in narrative
    assert raw_social not in narrative
    assert raw_values not in narrative
    sem = _semantic(profile)
    barrier = _find_entry(sem, "barriers.time_constraints")
    assert barrier is not None
    assert barrier["sensitivity"] == "high"
    assert barrier["source_fact_id"] == b.id
    assert "value_compact" not in barrier
    assert barrier in sem["high_sensitivity_context_refs"]
    assert _find_entry(sem, "social.support_network") in sem["high_sensitivity_context_refs"]
    assert _find_entry(sem, "values.important_values") in sem["high_sensitivity_context_refs"]


def test_cr04c1_row_high_work_and_preferences_metadata_only(db):
    user = _user(db, "row-high")
    grant_memory_consent(db, user.id, commit=True)
    raw_work = "night shifts confidential"
    raw_pref = "brief please secret"
    work = write_fact(
        db,
        user.id,
        "work",
        "work_schedule",
        raw_work,
        sensitivity_class="high",
        commit=True,
    )
    pref = write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        raw_pref,
        sensitivity_class="high",
        commit=True,
    )
    # Control: standard medium facts still expose compact values.
    write_fact(db, user.id, "work", "occupation", "designer", commit=True)
    write_fact(db, user.id, "preferences", "interaction_style", "brief", commit=True)

    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    blob = profile.structured_profile_json or ""
    narrative = profile.narrative_compact or ""
    assert raw_work not in blob
    assert raw_pref not in blob
    assert raw_work not in narrative
    assert raw_pref not in narrative

    sem = _semantic(profile)
    work_e = _find_entry(sem, "work.work_schedule")
    pref_e = _find_entry(sem, "preferences.response_length")
    assert work_e is not None
    assert pref_e is not None
    assert work_e["sensitivity"] == "high"
    assert pref_e["sensitivity"] == "high"
    assert "value_compact" not in work_e
    assert "value_compact" not in pref_e
    assert work_e in sem["high_sensitivity_context_refs"]
    assert pref_e in sem["high_sensitivity_context_refs"]
    assert work_e["source_fact_id"] == work.id
    assert pref_e["source_fact_id"] == pref.id

    occ = _find_entry(sem, "work.occupation")
    style = _find_entry(sem, "preferences.interaction_style")
    assert occ is not None and occ["value_compact"] == "designer"
    assert occ in sem["work_context"]
    assert style is not None and style["value_compact"] == "brief"
    assert style in sem["interaction_preferences"]


def test_cr04c1_provenance_unknown_system_confirmed(db):
    user = _user(db, "prov")
    grant_memory_consent(db, user.id, commit=True)
    from datetime import datetime

    now = datetime.utcnow()
    consent = (
        db.query(models.UserConsent)
        .filter_by(subject_user_id=user.id, status="active")
        .first()
    )
    rows = [
        models.UserMemoryFact(
            user_id=user.id,
            domain="routines",
            key="bedtime",
            value_json='"10pm"',
            confidence=0.9,
            source="manual",
            provenance_class=None,
            fact_status="active",
            consent_id=consent.id if consent else None,
            sensitivity_class="standard",
            created_at=now,
            updated_at=now,
        ),
        models.UserMemoryFact(
            user_id=user.id,
            domain="routines",
            key="wake_time",
            value_json='"7am"',
            confidence=0.9,
            source="system",
            provenance_class="SYSTEM_DERIVED",
            fact_status="active",
            consent_id=consent.id if consent else None,
            sensitivity_class="standard",
            created_at=now,
            updated_at=now,
        ),
        models.UserMemoryFact(
            user_id=user.id,
            domain="lifestyle",
            key="sleep_quality",
            value_json='"fair"',
            confidence=0.9,
            source="correction",
            provenance_class="USER_CONFIRMED",
            fact_status="active",
            consent_id=consent.id if consent else None,
            sensitivity_class="standard",
            created_at=now,
            updated_at=now,
        ),
    ]
    for row in rows:
        db.add(row)
    db.commit()

    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    sem = _semantic(profile)
    bed = _find_entry(sem, "routines.bedtime")
    wake = _find_entry(sem, "routines.wake_time")
    sleep = _find_entry(sem, "lifestyle.sleep_quality")
    assert bed is not None and bed["provenance_class"] == "UNKNOWN"
    assert wake is not None and wake["provenance_class"] == "SYSTEM_DERIVED"
    assert sleep is not None and sleep["provenance_class"] == "USER_CONFIRMED"
    # Never promote unknown/system to user-stated/confirmed.
    assert bed["provenance_class"] != "USER_STATED"
    assert wake["provenance_class"] != "USER_STATED"
    assert wake["provenance_class"] != "USER_CONFIRMED"

    from backend.app.services.i7.lifelong_profile import _provenance_class

    class _Fake:
        provenance_class = "   "

    assert _provenance_class(_Fake()) == "UNKNOWN"


def test_cr04c_medical_vitals_goals_excluded_from_semantic(db):
    user = _user(db, "excluded")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "medical", "health_concerns", "migraine notes", commit=True)
    write_fact(db, user.id, "goals", "health_goals", "walk daily", commit=True)
    write_fact(db, user.id, "lifestyle", "sleep_quality", "fair", commit=True)
    # Simulate non-projectable / non-I6-canonical rows if present in store.
    now = __import__("datetime").datetime.utcnow()
    db.add(
        models.UserMemoryFact(
            user_id=user.id,
            domain="vitals",
            key="heart_rate_bpm",
            value_json="72",
            confidence=0.9,
            source="manual",
            provenance_class="USER_STATED",
            fact_status="active",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        models.UserMemoryFact(
            user_id=user.id,
            domain="preferences",
            key="timezone",
            value_json='"UTC"',
            confidence=0.9,
            source="manual",
            provenance_class="USER_STATED",
            fact_status="active",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    payload = _payload(profile)
    # Legacy top-level may still list goals keys for I8.
    assert "goals.health_goals" in payload["goals"]
    sem = _semantic(profile)
    assert _find_entry(sem, "medical.health_concerns") is None
    assert _find_entry(sem, "vitals.heart_rate_bpm") is None
    assert _find_entry(sem, "goals.health_goals") is None
    assert _find_entry(sem, "preferences.timezone") is None
    assert _find_entry(sem, "lifestyle.sleep_quality") is not None
    assert "migraine notes" not in (profile.structured_profile_json or "")
    assert "walk daily" not in (profile.structured_profile_json or "")


def test_cr04c_source_fact_ids_exact_and_idempotent(db):
    user = _user(db, "lineage")
    grant_memory_consent(db, user.id, commit=True)
    f1 = write_fact(db, user.id, "work", "work_schedule", "9 to 5 weekdays", commit=True)
    f2 = write_fact(db, user.id, "routines", "wake_time", "7am", commit=True)
    p1 = rebuild_lifelong_profile(db, user.id, commit=True)
    ids = json.loads(p1.source_fact_ids_json)
    assert ids == sorted([f1.id, f2.id])
    p2 = rebuild_lifelong_profile(db, user.id, commit=True)
    assert p2.id == p1.id
    assert p2.version == p1.version
    # Same-value refresh must not force a new profile version.
    write_fact(db, user.id, "work", "work_schedule", "9 to 5 weekdays", commit=True)
    p3 = rebuild_lifelong_profile(db, user.id, commit=True)
    assert p3.id == p1.id
    assert p3.version == p1.version


def test_cr04c_correction_marks_stale_and_next_version(db):
    user = _user(db, "correct")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "work", "work_schedule", "day shift", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    correct_fact(db, user.id, "work", "work_schedule", "night shifts", commit=True)
    db.refresh(profile)
    assert profile.status == "stale"
    rebuilt = rebuild_lifelong_profile(db, user.id, commit=True)
    assert rebuilt.status == "active"
    assert rebuilt.version == profile.version + 1
    entry = _find_entry(_semantic(rebuilt), "work.work_schedule")
    assert entry is not None
    assert entry["value_compact"] == "night shifts"
    assert entry["change_state"] == "corrected"
    assert entry["supersedes_fact_id"] is not None


def test_cr04c_delete_forget_excluded_from_rebuild(db):
    user = _user(db, "forget")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "routines", "bedtime", "11pm", commit=True)
    work = write_fact(db, user.id, "work", "work_schedule", "night shifts", commit=True)
    first = rebuild_lifelong_profile(db, user.id, commit=True)
    assert _find_entry(_semantic(first), "work.work_schedule") is not None
    work_id = work.id
    delete_fact(db, user.id, "work", "work_schedule", commit=True)
    rebuilt = rebuild_lifelong_profile(db, user.id, commit=True)
    assert rebuilt.version == first.version + 1
    assert _find_entry(_semantic(rebuilt), "work.work_schedule") is None
    assert _find_entry(_semantic(rebuilt), "routines.bedtime") is not None
    ids = json.loads(rebuilt.source_fact_ids_json)
    assert work_id not in ids


def test_cr04c_user_isolation(db):
    a = _user(db, "iso-a")
    b = _user(db, "iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "work", "work_schedule", "a-only-schedule", commit=True)
    write_fact(db, b.id, "work", "work_schedule", "b-secret-schedule", commit=True)
    pa = rebuild_lifelong_profile(db, a.id, commit=True)
    pb = rebuild_lifelong_profile(db, b.id, commit=True)
    assert "b-secret-schedule" not in (pa.structured_profile_json or "")
    assert "a-only-schedule" not in (pb.structured_profile_json or "")
    assert _find_entry(_semantic(pa), "work.work_schedule")["value_compact"] == "a-only-schedule"
    assert _find_entry(_semantic(pb), "work.work_schedule")["value_compact"] == "b-secret-schedule"


def test_cr04c_no_diagnosis_personality_inference(db):
    user = _user(db, "safe-narrative")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "sleep_quality", "restless", commit=True)
    write_fact(db, user.id, "work", "work_schedule", "night shifts", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    payload = _payload(profile)
    assert payload["not_diagnosis"] is True
    narrative = (profile.narrative_compact or "").lower()
    banned = (
        "personality",
        "depression",
        "anxiety disorder",
        "hidden motive",
        "mental state",
        "diagnosed with",
        "clinical diagnosis",
    )
    for tok in banned:
        assert tok not in narrative
        assert tok not in (profile.structured_profile_json or "").lower()
    assert "not diagnosis" in narrative
    assert "i6 remains sot" in narrative


def test_cr04c_i8_lifelong_parser_compatibility(db):
    user = _user(db, "i8-compat")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "vegetarian meals", commit=True)
    write_fact(db, user.id, "preferences", "response_length", "detailed", commit=True)
    write_fact(db, user.id, "goals", "fitness_goals", "strength", commit=True)
    write_fact(db, user.id, "work", "work_schedule", "night shifts", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    payload = _payload(profile)
    habit_terms = _bounded_i7_terms(payload.get("habits"), limit=I8_PERSONAL_CONTEXT_TERM_SLICE)
    pref_terms = _bounded_i7_terms(payload.get("preferences"), limit=I8_PERSONAL_CONTEXT_TERM_SLICE)
    goal_terms = _bounded_i7_terms(payload.get("goals"), limit=I8_PERSONAL_CONTEXT_TERM_SLICE)
    assert "food habits" in habit_terms
    assert "response length" in pref_terms
    assert "fitness goals" in goal_terms
    # Semantic profile must not replace I8 key-list contract.
    assert isinstance(payload["habits"], list)
    assert payload["habits"][0].startswith("lifestyle.")
    assert "semantic_profile" in payload


def test_cr04c_no_runtime_wiring_in_orchestrator_or_i8():
    from backend.app.services.intelligence import orchestrator as orch_mod
    from backend.app.services.i8 import context as i8_ctx
    from backend.app.services.i8 import unified_core as i8_core

    orch_src = inspect.getsource(orch_mod)
    assert "rebuild_lifelong_profile" not in orch_src
    assert "rebuild_lifelong_profile" not in inspect.getsource(i8_ctx)
    assert "rebuild_lifelong_profile" not in inspect.getsource(i8_core)


def test_cr04c_cr04a_corpus_still_green():
    from backend.tests.test_cr04a_multilingual_semantic_quality import (
        _cases,
        _load_corpus,
        test_cr04a_corpus_schema,
        test_cr04a_semantic_contract,
    )

    corpus = _load_corpus()
    test_cr04a_corpus_schema(corpus)
    for case in _cases():
        test_cr04a_semantic_contract(case)


def test_cr04c_cr04b_regression_smoke():
    from backend.tests import test_cr04b_contextual_user_understanding as cr04b
    from backend.app.services.intelligence.contracts import IntentId
    from backend.app.services.intelligence.next_best_question import select_next_best_question

    intent = cr04b._intent(IntentId.GENERAL)
    d = select_next_best_question(
        snapshot=cr04b._snap([]),
        intent=intent,
        readiness=cr04b._ready(intent),
        language="en",
        message="My night shifts are making sleep difficult",
    )
    assert d is not None
    assert d.target_key == "work.work_schedule"
    from backend.app.services.i6.relationship_discovery import SUPPORTED_TARGETS

    assert "work.work_schedule" in SUPPORTED_TARGETS
    assert "barriers.time_constraints" in SUPPORTED_TARGETS
