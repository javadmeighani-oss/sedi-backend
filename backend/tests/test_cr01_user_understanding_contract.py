"""CR-01 — User-understanding I6 contract ownership and I2 projection bounds."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from unittest.mock import patch

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.intelligence.adapters import LifestyleContextAdapter
from backend.app.services.intelligence.context_types import (
    ContextSection,
    ContextSnapshot,
)
from backend.app.services.memory.memory_contract import (
    ALLOWED_DOMAINS,
    ALLOWED_KEYS,
    CANONICAL_HEALTH,
    CANONICAL_I6,
    CANONICAL_MEDICATION,
    CANONICAL_PROFILE,
    CANONICAL_VITALS_I9,
    DOMAIN_OWNERSHIP_DEFAULT,
    I6_CONTEXT_EXCLUDED_DOMAINS,
    I6_CONTEXT_EXCLUDED_KEYS,
    KEY_OWNERSHIP_OVERRIDES,
    LEGACY_KEY_ALIASES,
    MemoryContract,
)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key="cr01-contract", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _lifestyle_only(db, user_id: int):
    with patch.object(
        LifestyleContextAdapter, "_load_gate2_lifestyle", return_value=[]
    ):
        return LifestyleContextAdapter().load(
            db, authenticated_user_id=user_id, user_context_pack=None
        )


def _snapshot_from_items(user_id: int, items):
    return ContextSnapshot(
        request_id="cr01-i2",
        owner_user_id=user_id,
        sections={
            "lifestyle": ContextSection(name="lifestyle", items=list(items)),
            "profile": ContextSection(name="profile", items=[]),
        },
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=("CONTEXT_ASSEMBLED",),
        adapter_order=("lifestyle",),
    )


def test_cr01_new_domains_and_keys_are_canonical_i6():
    for domain in ("work", "education", "social", "values", "barriers"):
        assert domain in ALLOWED_DOMAINS
        assert DOMAIN_OWNERSHIP_DEFAULT[domain] == CANONICAL_I6
        for key in ALLOWED_KEYS[domain]:
            assert MemoryContract.classify_ownership(domain, key) == CANONICAL_I6
            assert MemoryContract.is_valid_key(domain, key)
            ok, err = MemoryContract.validate_fact(domain, key)
            assert ok, err
            assert MemoryContract.is_i6_context_projectable(domain, key)


def test_cr01_preferences_extensions_are_canonical_i6():
    for key in (
        "response_length",
        "interaction_style",
        "follow_up_preference",
        "listen_before_advice",
        "proactive_checkin_preference",
    ):
        assert key in ALLOWED_KEYS["preferences"]
        assert MemoryContract.classify_ownership("preferences", key) == CANONICAL_I6
        ok, err = MemoryContract.validate_fact("preferences", key)
        assert ok, err


def test_cr01_no_stronger_owner_duplication():
    assert MemoryContract.classify_ownership("preferences", "timezone") == CANONICAL_PROFILE
    assert MemoryContract.classify_ownership("preferences", "quiet_hours") == CANONICAL_PROFILE
    assert MemoryContract.classify_ownership("medical", "conditions") == CANONICAL_HEALTH
    assert MemoryContract.classify_ownership("medical", "medications") == CANONICAL_MEDICATION
    assert MemoryContract.classify_ownership("vitals", "heart_rate_bpm") == CANONICAL_VITALS_I9
    assert "medical" in I6_CONTEXT_EXCLUDED_DOMAINS
    assert "vitals" in I6_CONTEXT_EXCLUDED_DOMAINS
    assert "goals" in I6_CONTEXT_EXCLUDED_DOMAINS
    assert ("preferences", "timezone") in I6_CONTEXT_EXCLUDED_KEYS
    assert ("preferences", "quiet_hours") in I6_CONTEXT_EXCLUDED_KEYS
    assert ("preferences", "language_preference") in I6_CONTEXT_EXCLUDED_KEYS


def test_cr01_preserves_aliases_overrides_and_exclusions():
    assert LEGACY_KEY_ALIASES[("preferences", "language")] == (
        "preferences",
        "language_preference",
    )
    assert KEY_OWNERSHIP_OVERRIDES[("preferences", "timezone")] == CANONICAL_PROFILE
    assert KEY_OWNERSHIP_OVERRIDES[("medical", "conditions")] == CANONICAL_HEALTH
    banned_fragments = ("diagnosis", "personality", "depression", "anxiety_disorder")
    for _domain, keys in ALLOWED_KEYS.items():
        for key in keys:
            lowered = key.lower()
            assert not any(b in lowered for b in banned_fragments)


def test_cr01_i6_facts_reach_authorized_snapshot(db):
    user = _user(db, "cr01-snap")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "work", "occupation", "designer", commit=True)
    write_fact(db, user.id, "routines", "bedtime", "23:00", commit=True)
    write_fact(db, user.id, "preferences", "interaction_style", "brief", commit=True)
    write_fact(db, user.id, "social", "support_network", "family", commit=True)
    write_fact(db, user.id, "lifestyle", "sleep_quality", "fair", commit=True)

    items = _lifestyle_only(db, user.id)
    snap = _snapshot_from_items(user.id, items)
    keys = {i.canonical_key for i in snap.items}
    assert "work.occupation" in keys
    assert "routines.bedtime" in keys
    assert "preferences.interaction_style" in keys
    assert "social.support_network" in keys
    assert "lifestyle.sleep_quality" in keys
    assert all(i.provenance.owner_user_id == user.id for i in snap.items)


def test_cr01_consent_and_user_isolation(db):
    a = _user(db, "cr01-a")
    b = _user(db, "cr01-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "work", "occupation", "a-only", commit=True)
    write_fact(db, b.id, "work", "occupation", "b-only", commit=True)

    items_a = _lifestyle_only(db, a.id)
    items_b = _lifestyle_only(db, b.id)
    assert any(i.canonical_key == "work.occupation" for i in items_a)
    assert all(i.provenance.owner_user_id == a.id for i in items_a)
    assert all(i.provenance.owner_user_id == b.id for i in items_b)
    a_vals = [
        str(i.structured_value)
        for i in items_a
        if i.canonical_key == "work.occupation"
    ]
    b_vals = [
        str(i.structured_value)
        for i in items_b
        if i.canonical_key == "work.occupation"
    ]
    assert any("a-only" in v for v in a_vals)
    assert not any("a-only" in v for v in b_vals)

    revoke_memory_consent(db, a.id, commit=True)
    revoked = _lifestyle_only(db, a.id)
    assert not any(i.canonical_key.startswith("work.") for i in revoked)


def test_cr01_bounded_context_limits(db):
    user = _user(db, "cr01-bounds")
    grant_memory_consent(db, user.id, commit=True)
    for key in ("occupation", "work_schedule", "work_stressors"):
        write_fact(db, user.id, "work", key, f"w-{key}", commit=True)
    for domain, keys in (
        ("education", ("education_level", "field_of_study")),
        ("social", ("household_context", "support_network", "important_relationships")),
        ("values", ("important_values", "life_priorities")),
        (
            "barriers",
            ("time_constraints", "financial_constraints", "environmental_constraints"),
        ),
        ("routines", ("wake_time", "bedtime", "meal_times")),
        (
            "preferences",
            ("interaction_style", "response_length", "follow_up_preference"),
        ),
    ):
        for key in keys:
            write_fact(db, user.id, domain, key, f"{domain}-{key}", commit=True)

    understanding = LifestyleContextAdapter()._load_i6_user_understanding_facts(
        db, authenticated_user_id=user.id
    )
    assert len(understanding) <= 12
    by_domain: dict[str, int] = {}
    for item in understanding:
        domain = item.canonical_key.split(".", 1)[0]
        by_domain[domain] = by_domain.get(domain, 0) + 1
    assert all(n <= 3 for n in by_domain.values())
    for item in understanding:
        if item.canonical_key.startswith(("social.", "values.", "barriers.")):
            assert item.sensitivity == "high"
            assert item.may_send_to_llm is False


def test_cr01_no_raw_values_in_reason_codes(db):
    user = _user(db, "cr01-safe-codes")
    grant_memory_consent(db, user.id, commit=True)
    secret = "SECRET_OCCUPATION_VALUE_XYZ"
    write_fact(db, user.id, "work", "occupation", secret, commit=True)
    items = _lifestyle_only(db, user.id)
    snap = _snapshot_from_items(user.id, items)
    assert all(secret not in code for code in snap.reason_codes)
