"""CR-04E2.3 — I6 consumer reads must not dirty expired consent/fact rows."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timedelta, timezone

from backend.app import models
from backend.app.services.i6.consent_service import (
    PERM_READ,
    expire_due_consents,
    grant_memory_consent,
    has_permission_readonly,
    revoke_memory_consent,
)
from backend.app.services.i6.memory_writes import (
    list_facts,
    list_facts_readonly,
    list_facts_readonly_or_empty,
    write_fact,
)
from backend.app.services.i7.derived_continuity import (
    get_bounded_continuity_topic,
    should_project_derived_continuity,
)
from backend.app.services.i7.lifelong_profile import (
    current_readable_fact_ids,
    is_lifelong_profile_fresh,
    rebuild_lifelong_profile,
)
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.intelligence.adapters import (
    CurrentMemoryContextAdapter,
    LifestyleContextAdapter,
)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _grant(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=False)
    db.flush()


def _memory_consent(db, user_id: int) -> models.UserConsent:
    return (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.consent_type == "MEMORY",
            models.UserConsent.purpose == "PERSONAL_LONG_TERM_MEMORY",
            models.UserConsent.status == "active",
        )
        .one()
    )


def _snapshot_fact(fact: models.UserMemoryFact) -> tuple:
    return (
        fact.fact_status,
        fact.valid_until,
        fact.updated_at,
        fact.soft_invalidated_at,
        fact.value_json,
    )


def _snapshot_consent(consent: models.UserConsent) -> tuple:
    return (
        consent.status,
        consent.updated_at,
        consent.effective_until,
        consent.revoked_at,
        consent.revocation_reason,
    )


# ---- helpers ----


def test_cr04e23_list_facts_readonly_excludes_expired_without_mutation(db):
    user = _user(db, "ro-list")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    expired = write_fact(
        db,
        user.id,
        "lifestyle",
        "sleep_quality",
        "poor",
        valid_until=past,
        commit=False,
    )
    live = write_fact(
        db,
        user.id,
        "lifestyle",
        "food_habits",
        "vegetarian",
        commit=False,
    )
    db.flush()
    before = _snapshot_fact(expired)
    rows = list_facts_readonly(db, user.id, domain="lifestyle")
    keys = {r.key for r in rows}
    assert "food_habits" in keys
    assert "sleep_quality" not in keys
    assert list_facts_readonly_or_empty(db, user.id, domain="lifestyle") == rows
    db.commit()
    db.refresh(expired)
    assert _snapshot_fact(expired) == before
    assert expired.fact_status == "active"
    assert live.fact_status == "active"


# ---- A) A3/I2 expired fact ----


def test_cr04e23_a_expired_fact_adapter_excludes_unmutated_after_commit(db):
    user = _user(db, "a3-fact")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    fact = write_fact(
        db,
        user.id,
        "lifestyle",
        "activity_level",
        "moderate",
        valid_until=past,
        commit=False,
    )
    live = write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        commit=False,
    )
    db.flush()
    before = _snapshot_fact(fact)

    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    by_key = {i.canonical_key for i in items}
    assert "lifestyle.activity_level" not in by_key
    assert "preferences.response_length" in by_key

    mem = CurrentMemoryContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    assert isinstance(mem, list)

    db.commit()
    db.refresh(fact)
    db.refresh(live)
    assert fact.fact_status == "active"
    assert _snapshot_fact(fact) == before
    assert live.fact_status == "active"


# ---- B) Expired consent ----


def test_cr04e23_b_expired_consent_adapter_denies_unmutated_after_commit(db):
    user = _user(db, "a3-consent")
    _grant(db, user.id)
    write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        commit=False,
    )
    consent = _memory_consent(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    consent.effective_until = past
    db.flush()
    db.refresh(consent)
    assert consent.status == "active"
    before = _snapshot_consent(consent)
    consent_id = consent.id

    assert has_permission_readonly(db, user.id, PERM_READ) is False
    assert list_facts_readonly(db, user.id) == []
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    assert not any(i.canonical_key == "preferences.response_length" for i in items)
    mem = CurrentMemoryContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    assert mem == []

    db.commit()
    consent = db.query(models.UserConsent).filter(models.UserConsent.id == consent_id).one()
    assert consent.status == "active"
    assert _snapshot_consent(consent) == before


# ---- C) I7 nominal reads ----


def test_cr04e23_c_i7_readable_ids_fresh_no_mutation_after_commit(db):
    user = _user(db, "i7-ro")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = write_fact(
        db,
        user.id,
        "preferences",
        "response_length",
        "brief",
        valid_until=past,
        commit=False,
    )
    live = write_fact(
        db,
        user.id,
        "routines",
        "bedtime",
        "22:30",
        commit=False,
    )
    consent = _memory_consent(db, user.id)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.flush()
    db.refresh(expired)
    db.refresh(consent)
    before_fact = _snapshot_fact(expired)
    before_consent = _snapshot_consent(consent)
    consent_id = consent.id

    assert current_readable_fact_ids(db, user.id) == ()
    fake = models.UserLifelongProfile(
        user_id=user.id,
        version=1,
        status="active",
        structured_profile_json="{}",
        narrative_compact="",
        source_fact_ids_json=f"[{int(live.id)}]",
        source_event_refs_json="[]",
        generator_version="test",
    )
    assert is_lifelong_profile_fresh(db, user.id, fake) is False
    assert is_lifelong_profile_fresh(db, user.id, None) is False

    db.commit()
    db.refresh(expired)
    consent = db.query(models.UserConsent).filter(models.UserConsent.id == consent_id).one()
    assert _snapshot_fact(expired) == before_fact
    assert expired.fact_status == "active"
    assert consent.status == "active"
    assert _snapshot_consent(consent) == before_consent
    assert live.fact_status == "active"


# ---- D) I8 load_trusted_context ----


def test_cr04e23_d_i8_load_trusted_context_expired_consent_no_mutation(db):
    user = _user(db, "i8-ro")
    _grant(db, user.id)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=False)
    profile = rebuild_lifelong_profile(db, user.id, commit=False)
    db.flush()
    assert profile is not None

    consent = _memory_consent(db, user.id)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(hours=1)
    db.flush()
    db.refresh(consent)
    before = _snapshot_consent(consent)
    consent_id = consent.id

    ctx = load_trusted_context(db, user.id)
    assert ctx.lifelong_profile is None

    db.commit()
    consent = db.query(models.UserConsent).filter(models.UserConsent.id == consent_id).one()
    assert consent.status == "active"
    assert _snapshot_consent(consent) == before


# ---- E) Preserve ----


def test_cr04e23_e_valid_consent_reads_normally(db):
    user = _user(db, "valid-ok")
    _grant(db, user.id)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    rows = list_facts_readonly(db, user.id, domain="preferences")
    assert any(r.key == "response_length" for r in rows)
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=user.id, user_context_pack=None
    )
    assert any(i.canonical_key == "preferences.response_length" for i in items)
    ids = current_readable_fact_ids(db, user.id)
    assert len(ids) >= 1
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    assert is_lifelong_profile_fresh(db, user.id, profile) is True
    ctx = load_trusted_context(db, user.id)
    assert ctx.lifelong_profile is not None


def test_cr04e23_e_revoked_and_missing_neutral(db):
    missing = _user(db, "miss")
    assert list_facts_readonly(db, missing.id) == []
    assert current_readable_fact_ids(db, missing.id) == ()
    assert (
        LifestyleContextAdapter().load(
            db, authenticated_user_id=missing.id, user_context_pack=None
        )
        is not None
    )
    assert (
        CurrentMemoryContextAdapter().load(
            db, authenticated_user_id=missing.id, user_context_pack=None
        )
        == []
    )

    revoked = _user(db, "rev")
    _grant(db, revoked.id)
    write_fact(db, revoked.id, "preferences", "response_length", "brief", commit=False)
    revoke_memory_consent(db, revoked.id, commit=False)
    db.flush()
    assert list_facts_readonly(db, revoked.id) == []
    assert current_readable_fact_ids(db, revoked.id) == ()
    items = LifestyleContextAdapter().load(
        db, authenticated_user_id=revoked.id, user_context_pack=None
    )
    assert not any(i.canonical_key == "preferences.response_length" for i in items)
    assert (
        CurrentMemoryContextAdapter().load(
            db, authenticated_user_id=revoked.id, user_context_pack=None
        )
        == []
    )


def test_cr04e23_e_explicit_expire_due_consents_still_works(db):
    user = _user(db, "expire-life")
    _grant(db, user.id)
    consent = _memory_consent(db, user.id)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.flush()
    assert consent.status == "active"
    n = expire_due_consents(db, user.id, commit=True)
    assert n == 1
    db.refresh(consent)
    assert consent.status == "expired"


def test_cr04e23_e_mutating_list_facts_lifecycle_unchanged(db):
    """list_facts remains the mutating lifecycle API (still expires fact_status)."""
    user = _user(db, "mutate-list")
    _grant(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=4)
    fact = write_fact(
        db,
        user.id,
        "lifestyle",
        "mood",
        "ok",
        valid_until=past,
        commit=True,
    )
    assert fact.fact_status == "active"
    rows = list_facts(db, user.id, domain="lifestyle")
    assert all(r.id != fact.id for r in rows)
    assert fact.fact_status == "expired"
    db.commit()
    db.refresh(fact)
    assert fact.fact_status == "expired"


def test_cr04e23_e_rebuild_write_lifecycle_unchanged(db):
    user = _user(db, "rebuild-ok")
    _grant(db, user.id)
    write_fact(db, user.id, "preferences", "response_length", "brief", commit=True)
    first = rebuild_lifelong_profile(db, user.id, commit=True)
    again = rebuild_lifelong_profile(db, user.id, commit=True)
    assert first.id == again.id
    write_fact(db, user.id, "routines", "wake_time", "07:00", commit=True)
    next_row = rebuild_lifelong_profile(db, user.id, commit=True)
    assert next_row.version == first.version + 1


def test_cr04e231_derived_continuity_expired_consent_unmutated_after_commit(db):
    """CR-04E2.3.1: derived continuity nominal reads must not dirty expired consent."""
    user = _user(db, "derived-ro")
    _grant(db, user.id)
    consent = _memory_consent(db, user.id)
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    consent.effective_until = past
    db.flush()
    db.refresh(consent)
    assert consent.status == "active"
    before = _snapshot_consent(consent)
    consent_id = consent.id

    assert should_project_derived_continuity(db, user.id) is False
    assert get_bounded_continuity_topic(db, user.id) is None

    db.commit()
    consent = db.query(models.UserConsent).filter(models.UserConsent.id == consent_id).one()
    assert consent.status == "active"
    assert _snapshot_consent(consent) == before
