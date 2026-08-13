"""I6 consent-gated memory writes on existing user_consents / user_memory_facts."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timedelta, timezone

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import (
    PERM_FORGET,
    PERM_READ,
    PERM_WRITE,
    ConsentDenied,
    expire_due_consents,
    grant_memory_consent,
    has_permission,
    revoke_memory_consent,
)
from backend.app.services.i6.memory_writes import (
    MemoryWriteError,
    assert_user_isolation,
    correct_fact,
    delete_fact,
    forget_all,
    list_facts,
    write_fact,
)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key="i6-test", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def test_i6_create_update_idempotent_retry(db):
    user = _user(db, "i6-create")
    grant_memory_consent(db, user.id, commit=True)
    first = write_fact(db, user.id, "lifestyle", "diet_notes", "vegetarian", commit=True)
    same = write_fact(db, user.id, "lifestyle", "diet_notes", "vegetarian", commit=True)
    assert first.id == same.id
    updated = write_fact(db, user.id, "lifestyle", "diet_notes", "omnivore", commit=True)
    assert updated.id != first.id
    db.refresh(first)
    assert first.fact_status == "superseded"
    assert updated.fact_status == "active"
    assert updated.supersedes_fact_id == first.id


def test_i6_correction_and_deletion(db):
    user = _user(db, "i6-correct")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "tea", commit=True)
    corrected = correct_fact(db, user.id, "lifestyle", "food_habits", "coffee", commit=True)
    assert corrected.source == "correction"
    assert corrected.provenance_class == "USER_CONFIRMED"
    assert delete_fact(db, user.id, "lifestyle", "food_habits", commit=True) is True
    assert list_facts(db, user.id, domain="lifestyle") == []


def test_i6_forget(db):
    user = _user(db, "i6-forget")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "mood", "calm", commit=True)
    write_fact(db, user.id, "goals", "health_goals", "walk", commit=True)
    n = forget_all(db, user.id, commit=True)
    assert n == 2
    assert list_facts(db, user.id) == []


def test_i6_consent_deny(db):
    user = _user(db, "i6-deny")
    with pytest.raises(ConsentDenied):
        write_fact(db, user.id, "lifestyle", "mood", "okay", commit=True)


def test_i6_consent_revoke(db):
    user = _user(db, "i6-revoke")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "mood", "okay", commit=True)
    assert revoke_memory_consent(db, user.id, commit=True) is True
    assert has_permission(db, user.id, PERM_WRITE) is False
    with pytest.raises(ConsentDenied):
        write_fact(db, user.id, "lifestyle", "mood", "later", commit=True)


def test_i6_consent_expiry(db):
    user = _user(db, "i6-expiry")
    consent = grant_memory_consent(db, user.id, commit=True)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    assert expire_due_consents(db, user.id, commit=True) == 1
    with pytest.raises(ConsentDenied):
        write_fact(db, user.id, "lifestyle", "mood", "expired", commit=True)


def test_i6_temporary_memory_expiry(db):
    user = _user(db, "i6-temp")
    grant_memory_consent(db, user.id, commit=True)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    write_fact(
        db,
        user.id,
        "lifestyle",
        "mood",
        "transient",
        durable=False,
        valid_until=past,
        commit=True,
    )
    assert list_facts(db, user.id) == []


def test_i6_contradiction_supersede(db):
    user = _user(db, "i6-contra")
    grant_memory_consent(db, user.id, commit=True)
    a = write_fact(db, user.id, "lifestyle", "diet_notes", "vegan", commit=True)
    b = write_fact(db, user.id, "lifestyle", "diet_notes", "pescatarian", commit=True)
    db.refresh(a)
    assert a.fact_status == "superseded"
    assert b.fact_status == "active"
    active = list_facts(db, user.id, domain="lifestyle")
    assert len(active) == 1
    assert active[0].id == b.id


def test_i6_rollback_uncommitted_write(db):
    user = _user(db, "i6-rollback")
    grant_memory_consent(db, user.id, commit=True)
    uid = user.id
    write_fact(db, uid, "lifestyle", "mood", "will-rollback", commit=False)
    db.rollback()
    assert db.query(models.UserMemoryFact).filter_by(user_id=uid).count() == 0


def test_i6_cross_user_isolation(db):
    a = _user(db, "i6-iso-a")
    b = _user(db, "i6-iso-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    fact = write_fact(db, a.id, "lifestyle", "mood", "private", commit=True)
    assert list_facts(db, b.id) == []
    with pytest.raises(ConsentDenied):
        assert_user_isolation(db, b.id, fact.id)
    assert_user_isolation(db, a.id, fact.id)


def test_i6_unsupported_medical_inference_and_forget_scope(db):
    user = _user(db, "i6-med")
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE, PERM_READ), commit=True)
    with pytest.raises(MemoryWriteError, match="UNSUPPORTED_MEDICAL_INFERENCE"):
        write_fact(db, user.id, "medical", "diagnosis", "inferred", commit=True)
    write_fact(db, user.id, "lifestyle", "mood", "okay", commit=True)
    with pytest.raises(ConsentDenied):
        delete_fact(db, user.id, "lifestyle", "mood", commit=True)
    with pytest.raises(ConsentDenied):
        forget_all(db, user.id, commit=True)
