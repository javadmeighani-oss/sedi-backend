"""I6 read governance, ownership, and vocabulary reconciliation (v636)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models import (
    MedicalCondition,
    NotificationPrefs,
    User,
    UserCondition,
    UserMemoryFact,
    UserProfileCore,
)
from backend.app.services.i6.consent_service import (
    ConsentDenied,
    grant_memory_consent,
    revoke_memory_consent,
)
from backend.app.services.i6.memory_writes import (
    MemoryWriteError,
    delete_fact,
    list_facts,
    write_fact,
)
from backend.app.services.memory.memory_context import build_memory_context
from backend.app.services.memory.memory_contract import MemoryContract
from backend.app.services.memory.memory_repository import MemoryRepository
from backend.app.services.memory_context_service import build_memory_context as build_unified_memory_context
from backend.app.services.user_context import UserContextService


def _user(db, name: str) -> User:
    row = User(name=name, secret_key="i6-read", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_read_without_permission_is_denied(db):
    user = _user(db, "i6-no-read")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "mood", "calm", commit=True)
    revoke_memory_consent(db, user.id, commit=True)
    with pytest.raises(ConsentDenied):
        list_facts(db, user.id)
    repo = MemoryRepository(db)
    assert repo.get_all_facts(user.id) == []
    assert repo.get_fact(user.id, "lifestyle", "mood") is None


def test_authorized_active_fact_is_readable(db):
    user = _user(db, "i6-active-read")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "mood", "calm", commit=True)
    rows = list_facts(db, user.id, domain="lifestyle")
    assert len(rows) == 1
    assert rows[0].key == "mood"
    ctx = build_memory_context(db, user.id)
    assert ctx.mood == "calm"


def test_superseded_fact_cannot_reenter_context(db):
    user = _user(db, "i6-superseded")
    grant_memory_consent(db, user.id, commit=True)
    first = write_fact(db, user.id, "lifestyle", "diet_notes", "vegan", commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "pescatarian", commit=True)
    db.refresh(first)
    assert first.fact_status == "superseded"
    keys = {r.key: r for r in list_facts(db, user.id, domain="lifestyle")}
    assert "diet_notes" in keys
    assert keys["diet_notes"].id != first.id
    ctx = build_memory_context(db, user.id)
    assert ctx.diet_notes == "pescatarian"
    repo = MemoryRepository(db)
    current = repo.get_fact(user.id, "lifestyle", "diet_notes")
    assert current is not None and current.id != first.id


def test_rejected_fact_cannot_reenter_context(db):
    user = _user(db, "i6-rejected")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "tea", commit=True)
    assert delete_fact(db, user.id, "lifestyle", "food_habits", commit=True) is True
    assert list_facts(db, user.id, domain="lifestyle") == []
    ctx = build_memory_context(db, user.id)
    assert ctx.food_habits is None


def test_expired_fact_cannot_reenter_context(db):
    user = _user(db, "i6-expired")
    grant_memory_consent(db, user.id, commit=True)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    write_fact(
        db,
        user.id,
        "lifestyle",
        "mood",
        "stale",
        valid_until=past,
        durable=True,
        commit=True,
    )
    assert list_facts(db, user.id) == []
    ctx = build_memory_context(db, user.id)
    assert ctx.mood is None


def test_soft_invalidated_fact_cannot_reenter_context(db):
    user = _user(db, "i6-invalidated")
    grant_memory_consent(db, user.id, commit=True)
    row = write_fact(db, user.id, "lifestyle", "stress_level", "low", commit=True)
    row.soft_invalidated_at = datetime.now(timezone.utc)
    row.invalidation_reason = "test_invalidation"
    db.commit()
    assert list_facts(db, user.id) == []
    repo = MemoryRepository(db)
    assert repo.get_facts_by_domain(user.id, "lifestyle") == []


def test_legacy_vocabulary_does_not_create_competing_keys(db):
    user = _user(db, "i6-vocab")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "preferences", "language", "fa", commit=True)
    rows = list_facts(db, user.id, domain="preferences")
    assert [r.key for r in rows] == ["language_preference"]
    repo = MemoryRepository(db)
    aliased = repo.get_fact(user.id, "preferences", "language")
    canonical = repo.get_fact(user.id, "preferences", "language_preference")
    assert aliased is not None and canonical is not None
    assert aliased.id == canonical.id
    with pytest.raises(MemoryWriteError):
        write_fact(db, user.id, "preferences", "preferred_name", "Ali", commit=True)
    leftover_keys = {r.key for r in db.query(UserMemoryFact).filter_by(user_id=user.id).all()}
    assert "preferred_name" not in leftover_keys
    assert "language" not in leftover_keys


def test_canonical_vocabulary_assembled_consistently(db):
    user = _user(db, "i6-canon-vocab")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "preferences", "communication_style", "warm", commit=True)
    write_fact(db, user.id, "preferences", "interests", "cycling", commit=True)
    ctx = build_memory_context(db, user.id)
    assert ctx.preferences.get("communication_style") == "warm"
    assert ctx.preferences.get("interests") == "cycling"
    unified = build_unified_memory_context(db, user.id)
    pref_keys = {item["key"] for item in unified.get("memory_facts", {}).get("preferences", [])}
    assert "communication_style" in pref_keys
    assert "timezone" not in pref_keys
    assert "quiet_hours" not in pref_keys


def test_profile_owned_fields_are_not_competing_i6_truth(db):
    user = _user(db, "ProfileOwner")
    db.add(UserProfileCore(user_id=user.id, timezone="Europe/Paris", language="fr"))
    db.commit()
    grant_memory_consent(db, user.id, commit=True)
    with pytest.raises(MemoryWriteError):
        write_fact(db, user.id, "preferences", "timezone", {"tz": "Asia/Tehran"}, commit=True)
    leftover = UserMemoryFact(
        user_id=user.id,
        domain="preferences",
        key="timezone",
        value_json='{"tz": "Asia/Tehran"}',
        confidence=0.9,
        source="legacy",
    )
    db.add(leftover)
    db.commit()
    pack = UserContextService(db).get_user_context(user.id)
    assert pack.timezone == "Europe/Paris"
    assert pack.preferred_name == "ProfileOwner"
    assert pack.language in {"en", "fr"}
    assert MemoryContract.classify_ownership("preferences", "timezone") == "CANONICAL_PROFILE"


def test_condition_and_medication_writes_are_not_i6_truth(db):
    user = _user(db, "i6-health-owner")
    grant_memory_consent(db, user.id, commit=True)
    with pytest.raises(MemoryWriteError):
        write_fact(db, user.id, "medical", "conditions", "hypertension", commit=True)
    with pytest.raises(MemoryWriteError):
        write_fact(db, user.id, "medical", "medications", "losartan", commit=True)
    cond = MedicalCondition(name="I6ReadGov Hypertension", description="test", category="chronic")
    db.add(cond)
    db.flush()
    db.add(UserCondition(user_id=user.id, condition_id=cond.id))
    db.commit()
    unified = build_unified_memory_context(db, user.id)
    assert "Hypertension" in unified["conditions"]
    assert unified.get("memory_facts", {}).get("medical") in (None, {})
    assert MemoryContract.classify_ownership("medical", "conditions") == "CANONICAL_HEALTH"
    assert MemoryContract.classify_ownership("medical", "medications") == "CANONICAL_MEDICATION"


def test_raw_vitals_are_not_stable_i6_memory(db):
    user = _user(db, "i6-vitals")
    grant_memory_consent(db, user.id, commit=True)
    with pytest.raises(MemoryWriteError):
        write_fact(db, user.id, "vitals", "heart_rate_bpm", {"bpm": 94}, commit=True)
    leftover = UserMemoryFact(
        user_id=user.id,
        domain="vitals",
        key="heart_rate_bpm",
        value_json='{"bpm": 94}',
        confidence=0.9,
        source="device",
    )
    db.add(leftover)
    db.commit()
    ctx = build_memory_context(db, user.id)
    assert getattr(ctx, "heart_rate_bpm", None) is None
    unified = build_unified_memory_context(db, user.id)
    assert "vitals" not in unified.get("memory_facts", {})
    assert MemoryContract.classify_ownership("vitals", "heart_rate_bpm") == "CANONICAL_VITALS_I9"


def test_context_assembly_preserves_user_isolation(db):
    a = _user(db, "iso-a")
    b = _user(db, "iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "lifestyle", "mood", "a-only", commit=True)
    write_fact(db, b.id, "lifestyle", "mood", "b-only", commit=True)
    assert [r.value_json for r in list_facts(db, a.id)] == ['"a-only"']
    assert build_memory_context(db, a.id).mood == "a-only"
    assert build_memory_context(db, b.id).mood == "b-only"
    pack_a = UserContextService(db).get_user_context(a.id)
    assert pack_a.user_id == a.id


def test_legacy_repository_cannot_bypass_read_governance(db):
    user = _user(db, "i6-bypass")
    grant_memory_consent(db, user.id, commit=True)
    active = write_fact(db, user.id, "lifestyle", "mood", "ok", commit=True)
    stale = UserMemoryFact(
        user_id=user.id,
        domain="lifestyle",
        key="diet_notes",
        value_json='"stale"',
        confidence=0.9,
        source="legacy",
        fact_status="superseded",
        soft_invalidated_at=datetime.now(timezone.utc),
    )
    db.add(stale)
    db.commit()
    repo = MemoryRepository(db)
    assert {r.id for r in repo.get_all_facts(user.id)} == {active.id}
    revoke_memory_consent(db, user.id, commit=True)
    assert repo.get_all_facts(user.id) == []
    with pytest.raises(ConsentDenied):
        write_fact(db, user.id, "lifestyle", "mood", "later", commit=True)


def test_quiet_hours_canonical_owner_is_notification_prefs(db):
    user = _user(db, "i6-qh")
    db.add(
        NotificationPrefs(
            user_id=user.id,
            quiet_hours_enabled=True,
            quiet_start="21:00",
            quiet_end="07:00",
        )
    )
    db.commit()
    pack = UserContextService(db).get_user_context(user.id)
    assert pack.quiet_hours.start == "21:00"
    assert pack.quiet_hours.end == "07:00"
    assert MemoryContract.classify_ownership("preferences", "quiet_hours") == "CANONICAL_PROFILE"


def test_previous_write_governance_not_regressed(db):
    user = _user(db, "i6-write-reg")
    with pytest.raises(ConsentDenied):
        write_fact(db, user.id, "lifestyle", "mood", "nope", commit=True)
    grant_memory_consent(db, user.id, commit=True)
    row = write_fact(db, user.id, "lifestyle", "mood", "ok", commit=True)
    assert row.fact_status == "active"
    revoke_memory_consent(db, user.id, commit=True)
    with pytest.raises(ConsentDenied):
        write_fact(db, user.id, "lifestyle", "mood", "after-revoke", commit=True)
