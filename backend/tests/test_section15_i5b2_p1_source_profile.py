"""Section 15-I5-B2-P1 / Fix1 — governed source profile persistence tests (authored; not executed)."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.models import GovernedSourceProfile, GovernedSourceProfileVersion, KnowledgeSource
from backend.app.services.governance.contracts import (
    AutomationStatus,
    AuthorityTier,
    ClinicalJurisdictionScope,
    FreshnessStatus,
    LicenseStatus,
    PermissionDecision,
    SourceClass,
    SourceOperationalStatus,
    VerificationMethod,
)
from backend.app.services.governance import kb_b2_source_profile_persistence as p1
from backend.app.services.governance.kb_b2_source_profile_persistence import (
    REASON_EXISTING_FINGERPRINT_IS_NOT_CURRENT,
    REASON_LOCATOR_URL_INVALID,
    REASON_SUPERSEDES_CYCLE,
    SNAPSHOT_SCHEMA_VERSION,
    SourceProfilePersistenceError,
    append_profile_version,
    assert_no_legacy_seed_in_p1,
    canonicalize_governance_evidence,
    coerce_governance_evidence,
    compute_snapshot_fingerprint,
    create_or_get_profile,
    get_current_profile_version,
    get_exact_profile_version,
    get_profile,
    get_profile_by_canonical_key,
    normalize_canonical_key,
    normalize_locator,
    profile_is_fetch_eligible,
    reject_immutable_version_mutation,
)


def _pg_only(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _require_postgres(db) -> None:
    if not _pg_only(db):
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


def _base_evidence(**overrides):
    base = {
        "publisher_authority_identity": "Ministry of Health IR",
        "source_class": SourceClass.KNOWLEDGE_DOCUMENT.value,
        "authority_evidence_tier": AuthorityTier.OFFICIAL_NATIONAL.value,
        "jurisdiction_scope": ClinicalJurisdictionScope.COUNTRY.value,
        "jurisdiction_country_code": "IR",
        "jurisdiction_subdivision_code": None,
        "jurisdiction_organization_id": None,
        "primary_language": "fa",
        "specialty_domain": "preventive_care",
        "license_status": LicenseStatus.EXPLICIT_GRANT.value,
        "permitted_use_restriction": "non_commercial_display_only",
        "storage_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "transformation_permission": PermissionDecision.DENY_EXPLICIT.value,
        "display_redistribution_permission": PermissionDecision.ALLOW_EXPLICIT.value,
        "automation_status": AutomationStatus.DISABLED.value,
        "verification_method": VerificationMethod.HUMAN_REVIEWED_DOCUMENT.value,
        "freshness_policy_days": 180,
        "freshness_status": FreshnessStatus.UNKNOWN_AGE.value,
        "fetch_policy": "manual_upload_only",
        "iran_first_applicable": True,
        "policy_version_reference": "policy-v1",
        "configuration_version_reference": "cfg-v1",
        "effective_at": datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Identity / URL normalization (F3)
# ---------------------------------------------------------------------------


def test_normalize_canonical_key_trim_casefold_nfc() -> None:
    assert normalize_canonical_key("  MoH-IR  ") == "moh-ir"
    with pytest.raises(SourceProfilePersistenceError, match="canonical_key_empty"):
        normalize_canonical_key("   ")


def test_url_locator_scheme_host_only_casefold() -> None:
    a = normalize_locator("URL", "HTTPS://Example.COM/Path")
    b = normalize_locator("url", "https://example.com/Path")
    assert a == b
    assert a[1] == "https://example.com/Path"


def test_url_locator_unicode_hostname_idna_equivalence() -> None:
    # German sharp s / IDNA: münchen.example → xn--mnchen-3ya.example
    unicode_form = normalize_locator("url", "https://münchen.example/Path")
    ascii_form = normalize_locator("url", "https://xn--mnchen-3ya.example/Path")
    assert unicode_form == ascii_form
    assert unicode_form[1] == "https://xn--mnchen-3ya.example/Path"


def test_url_locator_ipv4_with_port() -> None:
    kind, loc = normalize_locator("url", "https://192.0.2.10:8443/Path")
    assert kind == "url"
    assert loc == "https://192.0.2.10:8443/Path"


def test_url_locator_ipv6_with_port_and_compression() -> None:
    expanded = normalize_locator(
        "url", "https://[2001:0db8:0000:0000:0000:0000:0000:0001]:8443/Path"
    )
    compact = normalize_locator("url", "https://[2001:db8::1]:8443/Path")
    assert expanded == compact
    assert compact[1] == "https://[2001:db8::1]:8443/Path"


def test_url_locator_path_and_query_case_preserved() -> None:
    assert normalize_locator("url", "https://example.com/Path") != normalize_locator(
        "url", "https://example.com/path"
    )
    assert normalize_locator("url", "https://example.com/?A=1") != normalize_locator(
        "url", "https://example.com/?a=1"
    )
    assert normalize_locator("url", "https://example.com/a") != normalize_locator(
        "url", "https://example.com/a/"
    )


def test_url_locator_credentials_rejected() -> None:
    with pytest.raises(SourceProfilePersistenceError, match="locator_credentials_forbidden"):
        normalize_locator("url", "https://user:secret@example.com/x")


def test_url_locator_malformed_port_typed() -> None:
    with pytest.raises(SourceProfilePersistenceError, match=REASON_LOCATOR_URL_INVALID):
        normalize_locator("url", "https://example.com:99999/x")
    with pytest.raises(SourceProfilePersistenceError, match=REASON_LOCATOR_URL_INVALID):
        normalize_locator("url", "https://example.com:notaport/x")


def test_url_locator_malformed_ipv6_typed() -> None:
    with pytest.raises(SourceProfilePersistenceError, match=REASON_LOCATOR_URL_INVALID):
        normalize_locator("url", "https://[gggg::1]/x")
    with pytest.raises(SourceProfilePersistenceError, match=REASON_LOCATOR_URL_INVALID):
        normalize_locator("url", "https://[::1/x")


def test_url_locator_missing_host_typed() -> None:
    with pytest.raises(SourceProfilePersistenceError, match="locator_url_host_required"):
        normalize_locator("url", "https:///path")


def test_url_locator_invalid_hostname_encoding_typed() -> None:
    with pytest.raises(SourceProfilePersistenceError, match=REASON_LOCATOR_URL_INVALID):
        # Empty DNS label rejected by IDNA (not an IP literal).
        normalize_locator("url", "https://example..com/x")


def test_normalize_locator_pair_rules() -> None:
    assert normalize_locator(None, None) == (None, None)
    with pytest.raises(
        SourceProfilePersistenceError, match="locator_kind_required_when_locator_present"
    ):
        normalize_locator(None, "https://x.example")
    with pytest.raises(
        SourceProfilePersistenceError, match="locator_required_when_locator_kind_present"
    ):
        normalize_locator("url", None)
    with pytest.raises(SourceProfilePersistenceError, match="locator_empty"):
        normalize_locator("url", "   ")
    with pytest.raises(
        SourceProfilePersistenceError, match="locator_required_when_locator_kind_present"
    ):
        normalize_locator("url", "")


# ---------------------------------------------------------------------------
# Fingerprint / timezone / microsecond precision (FIX1-A1/A2)
# ---------------------------------------------------------------------------


def test_fingerprint_timezone_equivalent_offsets() -> None:
    plus_0330 = timezone(timedelta(hours=3, minutes=30))
    e1 = coerce_governance_evidence(
        _base_evidence(effective_at=datetime(2026, 1, 1, 12, 0, 0, 100000, tzinfo=plus_0330))
    )
    e2 = coerce_governance_evidence(
        _base_evidence(
            effective_at=datetime(2026, 1, 1, 8, 30, 0, 100000, tzinfo=timezone.utc)
        )
    )
    assert compute_snapshot_fingerprint(e1) == compute_snapshot_fingerprint(e2)
    assert "2026-01-01T08:30:00.100000Z" in canonicalize_governance_evidence(e1)


def test_fingerprint_microseconds_preserved_and_distinct() -> None:
    e100 = coerce_governance_evidence(
        _base_evidence(
            effective_at=datetime(2026, 1, 1, 8, 30, 0, 100000, tzinfo=timezone.utc)
        )
    )
    e900 = coerce_governance_evidence(
        _base_evidence(
            effective_at=datetime(2026, 1, 1, 8, 30, 0, 900000, tzinfo=timezone.utc)
        )
    )
    assert compute_snapshot_fingerprint(e100) != compute_snapshot_fingerprint(e900)
    assert "2026-01-01T08:30:00.100000Z" in canonicalize_governance_evidence(e100)
    assert "2026-01-01T08:30:00.900000Z" in canonicalize_governance_evidence(e900)


def test_fingerprint_zero_microseconds_deterministic() -> None:
    e = coerce_governance_evidence(
        _base_evidence(effective_at=datetime(2026, 1, 1, 8, 30, 0, 0, tzinfo=timezone.utc))
    )
    payload = canonicalize_governance_evidence(e)
    assert "2026-01-01T08:30:00.000000Z" in payload


def test_fingerprint_different_effective_instant() -> None:
    e1 = coerce_governance_evidence(_base_evidence())
    e2 = coerce_governance_evidence(
        _base_evidence(effective_at=datetime(2026, 1, 16, 12, 0, tzinfo=timezone.utc))
    )
    assert compute_snapshot_fingerprint(e1) != compute_snapshot_fingerprint(e2)


def test_fingerprint_order_and_schema() -> None:
    e1 = coerce_governance_evidence(_base_evidence())
    e2 = coerce_governance_evidence(dict(reversed(list(_base_evidence().items()))))  # type: ignore[arg-type]
    assert compute_snapshot_fingerprint(e1) == compute_snapshot_fingerprint(e2)
    assert compute_snapshot_fingerprint(e1) != compute_snapshot_fingerprint(
        e1, snapshot_schema_version="i5b2_p1_v2"
    )
    payload = canonicalize_governance_evidence(e1)
    assert "created_at" not in payload
    assert "version_seq" not in payload


def test_naive_effective_at_rejected() -> None:
    with pytest.raises(SourceProfilePersistenceError, match="naive_datetime"):
        coerce_governance_evidence(_base_evidence(effective_at=datetime(2026, 1, 1)))


# ---------------------------------------------------------------------------
# Profile defaults / identity
# ---------------------------------------------------------------------------


def test_create_profile_defaults_fail_closed(db) -> None:
    profile = create_or_get_profile(db, canonical_key="src-a")
    db.commit()
    assert profile.operational_status == SourceOperationalStatus.DISABLED.value
    assert profile_is_fetch_eligible(profile) is False
    assert profile.current_profile_version_id is None


def test_canonical_key_uniqueness_and_exact_reuse(db) -> None:
    p1_row = create_or_get_profile(db, canonical_key="Same-Key")
    p2_row = create_or_get_profile(db, canonical_key="same-key")
    assert p1_row.id == p2_row.id


def test_conflicting_identity_fail_closed(db) -> None:
    create_or_get_profile(
        db, canonical_key="conflict-key", locator_kind="url", locator="https://a.example/x"
    )
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match="canonical_key_identity_conflict"):
        create_or_get_profile(
            db,
            canonical_key="conflict-key",
            locator_kind="url",
            locator="https://b.example/y",
        )


def test_locator_uniqueness(db) -> None:
    create_or_get_profile(
        db, canonical_key="loc-1", locator_kind="url", locator="https://unique.example/Path"
    )
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match="locator_identity_conflict"):
        create_or_get_profile(
            db,
            canonical_key="loc-2",
            locator_kind="url",
            locator="HTTPS://unique.example/Path",
        )


def test_legacy_reference_unique_and_conflict(db) -> None:
    ks = KnowledgeSource(
        slug="p1-legacy-unique-source",
        name="P1 Legacy Unique",
        category="other",
        trust_level="editorial",
        locale="fa",
        ingestion_status="draft",
    )
    db.add(ks)
    db.flush()
    create_or_get_profile(db, canonical_key="leg-1", legacy_knowledge_source_id=ks.id)
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match="legacy_knowledge_source_conflict"):
        create_or_get_profile(db, canonical_key="leg-2", legacy_knowledge_source_id=ks.id)


def test_no_hidden_version_on_profile_create(db) -> None:
    profile = create_or_get_profile(db, canonical_key="no-auto-version")
    db.commit()
    assert get_current_profile_version(db, profile_id=profile.id, required=False) is None


# ---------------------------------------------------------------------------
# F1 pointer cases A/B/C/D
# ---------------------------------------------------------------------------


def test_case_a_idempotent_already_current_no_row_version_bump(db) -> None:
    profile = create_or_get_profile(db, canonical_key="case-a")
    db.commit()
    evidence = _base_evidence()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    profile = get_profile(db, profile.id)
    row_before = profile.row_version
    current_before = profile.current_profile_version_id
    v2 = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    profile = get_profile(db, profile.id)
    assert v1.id == v2.id
    assert profile.current_profile_version_id == current_before == v1.id
    assert profile.row_version == row_before


def test_case_b_old_fingerprint_cannot_move_pointer_backward(db) -> None:
    profile = create_or_get_profile(db, canonical_key="case-b")
    db.commit()
    e1 = _base_evidence()
    e2 = _base_evidence(specialty_domain="nutrition")
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=e1)
    db.commit()
    v2 = append_profile_version(db, profile_id=profile.id, governance_evidence=e2)
    db.commit()
    profile = get_profile(db, profile.id)
    assert profile.current_profile_version_id == v2.id
    row_before = profile.row_version
    with pytest.raises(
        SourceProfilePersistenceError, match=REASON_EXISTING_FINGERPRINT_IS_NOT_CURRENT
    ):
        append_profile_version(db, profile_id=profile.id, governance_evidence=e1)
    db.rollback()
    profile = get_profile(db, profile.id)
    assert profile.current_profile_version_id == v2.id
    assert profile.row_version == row_before
    assert v1.id != v2.id


def test_case_c_null_pointer_initializes_only_if_latest(db) -> None:
    profile = create_or_get_profile(db, canonical_key="case-c")
    db.commit()
    evidence = _base_evidence()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    # Simulate drifted null pointer while version exists (service-supported recovery path).
    profile = get_profile(db, profile.id)
    profile.current_profile_version_id = None
    db.flush()
    db.commit()
    profile = get_profile(db, profile.id)
    assert profile.current_profile_version_id is None
    row_before = profile.row_version
    recovered = append_profile_version(
        db, profile_id=profile.id, governance_evidence=evidence
    )
    db.commit()
    profile = get_profile(db, profile.id)
    assert recovered.id == v1.id
    assert profile.current_profile_version_id == v1.id
    assert profile.row_version == row_before + 1


def test_case_c_null_pointer_rejects_non_latest_fingerprint(db) -> None:
    profile = create_or_get_profile(db, canonical_key="case-c-old")
    db.commit()
    e1 = _base_evidence()
    e2 = _base_evidence(specialty_domain="later")
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=e1)
    db.commit()
    v2 = append_profile_version(db, profile_id=profile.id, governance_evidence=e2)
    db.commit()
    profile = get_profile(db, profile.id)
    profile.current_profile_version_id = None
    db.flush()
    db.commit()
    row_before = get_profile(db, profile.id).row_version
    with pytest.raises(
        SourceProfilePersistenceError, match=REASON_EXISTING_FINGERPRINT_IS_NOT_CURRENT
    ):
        append_profile_version(db, profile_id=profile.id, governance_evidence=e1)
    db.rollback()
    profile = get_profile(db, profile.id)
    assert profile.current_profile_version_id is None
    assert profile.row_version == row_before
    assert v1.id != v2.id


def test_case_d_normal_append_advances(db) -> None:
    profile = create_or_get_profile(db, canonical_key="case-d")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    v2 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="cardio"),
        supersedes_version_id=v1.id,
    )
    db.commit()
    assert v2.version_seq == 2
    assert get_current_profile_version(db, profile_id=profile.id).id == v2.id


def test_same_fingerprint_allowed_on_other_profile(db) -> None:
    a = create_or_get_profile(db, canonical_key="fp-a")
    b = create_or_get_profile(db, canonical_key="fp-b")
    db.commit()
    evidence = _base_evidence()
    va = append_profile_version(db, profile_id=a.id, governance_evidence=evidence)
    vb = append_profile_version(db, profile_id=b.id, governance_evidence=evidence)
    db.commit()
    assert va.id != vb.id
    assert va.snapshot_fingerprint == vb.snapshot_fingerprint


# ---------------------------------------------------------------------------
# Supersedes integrity (F5)
# ---------------------------------------------------------------------------


def test_supersedes_cross_profile_rejected(db) -> None:
    a = create_or_get_profile(db, canonical_key="sup-a")
    b = create_or_get_profile(db, canonical_key="sup-b")
    db.commit()
    va = append_profile_version(db, profile_id=a.id, governance_evidence=_base_evidence())
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match="supersedes_version_not_found"):
        append_profile_version(
            db,
            profile_id=b.id,
            governance_evidence=_base_evidence(specialty_domain="x"),
            supersedes_version_id=va.id,
        )


def test_supersedes_self_rejected_after_flush_path(db) -> None:
    # Service rejects chain that already self-points; also DB CHECK exists.
    profile = create_or_get_profile(db, canonical_key="sup-self")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    # Force corrupt self-supersede via SQL when PG CHECK allows detection path.
    _require_postgres(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE governed_source_profile_versions "
                "SET supersedes_version_id = id WHERE id = :id"
            ),
            {"id": v1.id},
        )
        db.flush()
    db.rollback()


def test_supersedes_linear_chain_accepted(db) -> None:
    profile = create_or_get_profile(db, canonical_key="sup-linear")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    v2 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="b"),
        supersedes_version_id=v1.id,
    )
    db.commit()
    v3 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="c"),
        supersedes_version_id=v2.id,
    )
    db.commit()
    assert v3.supersedes_version_id == v2.id


def test_supersedes_two_node_cycle_fail_closed(db) -> None:
    """Corrupt A↔B via SQL; next append that walks the chain fails closed (no repair)."""
    _require_postgres(db)
    profile = create_or_get_profile(db, canonical_key="sup-cycle-2")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    v2 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="b"),
        supersedes_version_id=v1.id,
    )
    db.commit()
    db.execute(
        text(
            "UPDATE governed_source_profile_versions "
            "SET supersedes_version_id = :v2 WHERE id = :v1"
        ),
        {"v2": v2.id, "v1": v1.id},
    )
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match=REASON_SUPERSEDES_CYCLE):
        append_profile_version(
            db,
            profile_id=profile.id,
            governance_evidence=_base_evidence(specialty_domain="c"),
            supersedes_version_id=v2.id,
        )


def test_supersedes_multi_node_cycle_fail_closed(db) -> None:
    _require_postgres(db)
    profile = create_or_get_profile(db, canonical_key="sup-cycle-3")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    v2 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="b"),
        supersedes_version_id=v1.id,
    )
    db.commit()
    v3 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="c"),
        supersedes_version_id=v2.id,
    )
    db.commit()
    db.execute(
        text(
            "UPDATE governed_source_profile_versions "
            "SET supersedes_version_id = :v3 WHERE id = :v1"
        ),
        {"v3": v3.id, "v1": v1.id},
    )
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match=REASON_SUPERSEDES_CYCLE):
        append_profile_version(
            db,
            profile_id=profile.id,
            governance_evidence=_base_evidence(specialty_domain="d"),
            supersedes_version_id=v3.id,
        )


def test_postgres_cross_profile_supersedes_fk(db) -> None:
    _require_postgres(db)
    a = create_or_get_profile(db, canonical_key="fk-sup-a")
    b = create_or_get_profile(db, canonical_key="fk-sup-b")
    db.commit()
    va = append_profile_version(db, profile_id=a.id, governance_evidence=_base_evidence())
    vb = append_profile_version(
        db, profile_id=b.id, governance_evidence=_base_evidence(specialty_domain="z")
    )
    db.commit()
    db.execute(
        text(
            "UPDATE governed_source_profile_versions "
            "SET supersedes_version_id = :other WHERE id = :id"
        ),
        {"other": va.id, "id": vb.id},
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# Locator DB check (F4)
# ---------------------------------------------------------------------------


def test_postgres_locator_pair_check_constraint(db) -> None:
    _require_postgres(db)
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO governed_source_profiles "
                "(canonical_key, locator_kind, normalized_locator, operational_status, row_version) "
                "VALUES ('bad-loc', 'url', NULL, 'disabled', 1)"
            )
        )
        db.flush()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO governed_source_profiles "
                "(canonical_key, locator_kind, normalized_locator, operational_status, row_version) "
                "VALUES ('bad-loc2', NULL, 'https://x.example', 'disabled', 1)"
            )
        )
        db.flush()
    db.rollback()


def test_both_null_locator_accepted(db) -> None:
    p = create_or_get_profile(db, canonical_key="null-loc")
    db.commit()
    assert p.locator_kind is None
    assert p.normalized_locator is None


def test_postgres_current_pointer_rejects_cross_profile_version(db) -> None:
    """Runtime PG proof: current pointer cannot reference another profile's version.

    Composite FK is DEFERRABLE INITIALLY DEFERRED — violation surfaces at commit.
    """
    _require_postgres(db)
    a = create_or_get_profile(db, canonical_key="ptr-fk-a")
    b = create_or_get_profile(db, canonical_key="ptr-fk-b")
    db.commit()
    vb = append_profile_version(
        db, profile_id=b.id, governance_evidence=_base_evidence(specialty_domain="b-only")
    )
    db.commit()
    a = get_profile(db, a.id)
    assert a.current_profile_version_id is None
    a.current_profile_version_id = vb.id
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    a = get_profile(db, a.id)
    assert a.current_profile_version_id is None
    # Outer session usable after rollback.
    assert get_profile_by_canonical_key(db, "ptr-fk-a").id == a.id


def test_postgres_same_profile_current_pointer_accepted(db) -> None:
    _require_postgres(db)
    profile = create_or_get_profile(db, canonical_key="ptr-same")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    profile = get_profile(db, profile.id)
    assert profile.current_profile_version_id == v1.id
    v2 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="next"),
        supersedes_version_id=v1.id,
    )
    db.commit()
    profile = get_profile(db, profile.id)
    assert profile.current_profile_version_id == v2.id
    assert v2.profile_id == profile.id


# ---------------------------------------------------------------------------
# Concurrency / IntegrityError / session (savepoint)
# ---------------------------------------------------------------------------


def test_stale_row_version_and_current_rejected(db) -> None:
    profile = create_or_get_profile(db, canonical_key="cas-profile")
    db.commit()
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match="stale_row_version"):
        append_profile_version(
            db,
            profile_id=profile.id,
            governance_evidence=_base_evidence(specialty_domain="x"),
            expected_row_version=1,
        )
    with pytest.raises(SourceProfilePersistenceError, match="stale_current_version"):
        append_profile_version(
            db,
            profile_id=profile.id,
            governance_evidence=_base_evidence(specialty_domain="y"),
            expected_current_version_id=v1.id + 999,
        )


def test_failed_append_rolls_back_pointer(db) -> None:
    profile = create_or_get_profile(db, canonical_key="rollback-profile")
    db.commit()
    before = get_profile(db, profile.id)
    with pytest.raises(SourceProfilePersistenceError):
        append_profile_version(
            db,
            profile_id=profile.id,
            governance_evidence=_base_evidence(source_class="not_a_real_class"),
        )
    db.rollback()
    after = get_profile(db, profile.id)
    assert after.current_profile_version_id is None
    assert after.row_version == before.row_version


def test_postgres_duplicate_sequence_integrity(db) -> None:
    _require_postgres(db)
    profile = create_or_get_profile(db, canonical_key="pg-seq")
    db.commit()
    append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO governed_source_profile_versions ("
                "profile_id, version_seq, snapshot_schema_version, snapshot_fingerprint, "
                "effective_at, publisher_authority_identity, source_class, "
                "authority_evidence_tier, jurisdiction_scope, primary_language, "
                "specialty_domain, license_status, permitted_use_restriction, "
                "storage_permission, transformation_permission, "
                "display_redistribution_permission, automation_status, "
                "verification_method, freshness_policy_days, freshness_status, "
                "fetch_policy, iran_first_applicable, policy_version_reference, "
                "configuration_version_reference"
                ") VALUES ("
                ":pid, 1, 'i5b2_p1_v1', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef', "
                "now(), 'x', 'knowledge_document', "
                "'editorial', 'global', 'fa', 'd', 'unknown', 'r', "
                "'unknown_deny', 'unknown_deny', 'unknown_deny', 'disabled', "
                "'human_reviewed_document', 1, 'unknown_age', 'manual', false, 'p', 'c')"
            ),
            {"pid": profile.id},
        )
        db.commit()
    db.rollback()


def test_postgres_same_fingerprint_race_resolves_via_savepoint(db) -> None:
    """Same-fingerprint unique race: nested savepoint rolls back; outer session stays usable.

    PostgreSQL-only. Competing row is inserted under a separate connection while the
    primary session holds the profile lock and has already passed the empty-fingerprint
    pre-check; append then recovers via IntegrityError → pointer Case A.
    """
    _require_postgres(db)
    from sqlalchemy.orm import sessionmaker

    profile = create_or_get_profile(db, canonical_key="race-fp")
    db.commit()
    evidence = _base_evidence(specialty_domain="race-domain")
    coerced = coerce_governance_evidence(evidence)
    fingerprint = compute_snapshot_fingerprint(coerced)

    # Primary: lock profile and confirm no fingerprint row yet (mirrors service pre-check).
    locked = (
        db.query(GovernedSourceProfile)
        .filter(GovernedSourceProfile.id == profile.id)
        .with_for_update()
        .one()
    )
    assert (
        db.query(GovernedSourceProfileVersion)
        .filter(
            GovernedSourceProfileVersion.profile_id == locked.id,
            GovernedSourceProfileVersion.snapshot_fingerprint == fingerprint,
        )
        .one_or_none()
        is None
    )

    # Competitor: insert same fingerprint without waiting on profile lock, then commit.
    OtherSession = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    other = OtherSession()
    try:
        other.execute(
            text(
                "INSERT INTO governed_source_profile_versions ("
                "profile_id, version_seq, snapshot_schema_version, snapshot_fingerprint, "
                "effective_at, publisher_authority_identity, source_class, "
                "authority_evidence_tier, jurisdiction_scope, jurisdiction_country_code, "
                "primary_language, specialty_domain, license_status, "
                "permitted_use_restriction, storage_permission, transformation_permission, "
                "display_redistribution_permission, automation_status, verification_method, "
                "freshness_policy_days, freshness_status, fetch_policy, iran_first_applicable, "
                "policy_version_reference, configuration_version_reference"
                ") VALUES ("
                ":pid, 1, :schema, :fp, :eff, :pub, :sc, :tier, :jscope, :jcc, "
                ":lang, :spec, :lic, :pur, :stor, :xform, :disp, :auto, :ver, "
                ":fpd, :fst, :fetch, :iran, :pol, :cfg)"
            ),
            {
                "pid": locked.id,
                "schema": SNAPSHOT_SCHEMA_VERSION,
                "fp": fingerprint,
                "eff": coerced.effective_at.replace(tzinfo=None),
                "pub": coerced.publisher_authority_identity,
                "sc": coerced.source_class,
                "tier": coerced.authority_evidence_tier,
                "jscope": coerced.jurisdiction_scope,
                "jcc": coerced.jurisdiction_country_code,
                "lang": coerced.primary_language,
                "spec": coerced.specialty_domain,
                "lic": coerced.license_status,
                "pur": coerced.permitted_use_restriction,
                "stor": coerced.storage_permission,
                "xform": coerced.transformation_permission,
                "disp": coerced.display_redistribution_permission,
                "auto": coerced.automation_status,
                "ver": coerced.verification_method,
                "fpd": coerced.freshness_policy_days,
                "fst": coerced.freshness_status,
                "fetch": coerced.fetch_policy,
                "iran": coerced.iran_first_applicable,
                "pol": coerced.policy_version_reference,
                "cfg": coerced.configuration_version_reference,
            },
        )
        other.commit()
    finally:
        other.close()

    # Service append: sees committed competitor on pre-check (Case C init or Case A).
    # Also prove nested-savepoint recovery path remains healthy by forcing a duplicate
    # insert under begin_nested after unlock, then continuing with append.
    db.rollback()  # release FOR UPDATE; outer usability restored for service call
    profile = get_profile(db, profile.id)
    # Pointer still null; competitor row exists → Case C initializes to latest.
    v = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    assert v.snapshot_fingerprint == fingerprint
    assert (
        db.query(GovernedSourceProfileVersion)
        .filter(GovernedSourceProfileVersion.profile_id == profile.id)
        .count()
        == 1
    )
    row_before = get_profile(db, profile.id).row_version
    # Nested savepoint: duplicate insert IntegrityError must not poison outer session.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO governed_source_profile_versions ("
                    "profile_id, version_seq, snapshot_schema_version, snapshot_fingerprint, "
                    "effective_at, publisher_authority_identity, source_class, "
                    "authority_evidence_tier, jurisdiction_scope, primary_language, "
                    "specialty_domain, license_status, permitted_use_restriction, "
                    "storage_permission, transformation_permission, "
                    "display_redistribution_permission, automation_status, "
                    "verification_method, freshness_policy_days, freshness_status, "
                    "fetch_policy, iran_first_applicable, policy_version_reference, "
                    "configuration_version_reference"
                    ") VALUES ("
                    ":pid, 2, :schema, :fp, now(), 'x', 'knowledge_document', "
                    "'editorial', 'global', 'fa', 'd', 'unknown', 'r', "
                    "'unknown_deny', 'unknown_deny', 'unknown_deny', 'disabled', "
                    "'human_reviewed_document', 1, 'unknown_age', 'manual', false, 'p', 'c')"
                ),
                {
                    "pid": profile.id,
                    "schema": SNAPSHOT_SCHEMA_VERSION,
                    "fp": fingerprint,
                },
            )
            db.flush()
    v2 = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    assert v2.id == v.id
    assert get_profile(db, profile.id).row_version == row_before
    assert get_profile_by_canonical_key(db, "race-fp").id == profile.id


def test_postgres_append_integrityerror_same_fingerprint_savepoint_recovery(db, monkeypatch) -> None:
    """Hide pre-check once so insert hits unique; savepoint recovery applies Case A."""
    _require_postgres(db)
    from sqlalchemy.orm.query import Query

    profile = create_or_get_profile(db, canonical_key="ie-savepoint")
    db.commit()
    evidence = _base_evidence(specialty_domain="ie-save")
    v1 = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    row_before = get_profile(db, profile.id).row_version

    state = {"hide_fp_once": True}
    orig = Query.one_or_none

    def one_or_none_wrapper(self):  # type: ignore[no-untyped-def]
        result = orig(self)
        if state["hide_fp_once"] and result is not None:
            where_txt = str(self.whereclause) if self.whereclause is not None else ""
            if "snapshot_fingerprint" in where_txt:
                state["hide_fp_once"] = False
                return None
        return result

    monkeypatch.setattr(Query, "one_or_none", one_or_none_wrapper)
    v2 = append_profile_version(db, profile_id=profile.id, governance_evidence=evidence)
    db.commit()
    assert v2.id == v1.id
    assert get_profile(db, profile.id).row_version == row_before
    assert get_profile_by_canonical_key(db, "ie-savepoint").id == profile.id
    assert (
        db.query(GovernedSourceProfileVersion)
        .filter(GovernedSourceProfileVersion.profile_id == profile.id)
        .count()
        == 1
    )


def test_postgres_unrelated_integrity_not_treated_as_idempotency(db) -> None:
    """Sequence uniqueness IntegrityError must stay fail-closed (not fingerprint recovery)."""
    _require_postgres(db)
    profile = create_or_get_profile(db, canonical_key="race-unrelated")
    db.commit()
    append_profile_version(db, profile_id=profile.id, governance_evidence=_base_evidence())
    db.commit()
    # Duplicate version_seq with a different fingerprint — not an idempotent race.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                text(
                    "INSERT INTO governed_source_profile_versions ("
                    "profile_id, version_seq, snapshot_schema_version, snapshot_fingerprint, "
                    "effective_at, publisher_authority_identity, source_class, "
                    "authority_evidence_tier, jurisdiction_scope, primary_language, "
                    "specialty_domain, license_status, permitted_use_restriction, "
                    "storage_permission, transformation_permission, "
                    "display_redistribution_permission, automation_status, "
                    "verification_method, freshness_policy_days, freshness_status, "
                    "fetch_policy, iran_first_applicable, policy_version_reference, "
                    "configuration_version_reference"
                    ") VALUES ("
                    ":pid, 1, 'i5b2_p1_v1', "
                    "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                    "now(), 'x', 'knowledge_document', "
                    "'editorial', 'global', 'fa', 'd', 'unknown', 'r', "
                    "'unknown_deny', 'unknown_deny', 'unknown_deny', 'disabled', "
                    "'human_reviewed_document', 1, 'unknown_age', 'manual', false, 'p', 'c')"
                ),
                {"pid": profile.id},
            )
            db.flush()
    # Outer session usable; service append with new evidence still works (seq=2).
    v2 = append_profile_version(
        db,
        profile_id=profile.id,
        governance_evidence=_base_evidence(specialty_domain="after-unrelated"),
    )
    db.commit()
    assert v2.version_seq == 2
    assert get_profile_by_canonical_key(db, "race-unrelated").id == profile.id


# ---------------------------------------------------------------------------
# Retrieval / immutability honesty
# ---------------------------------------------------------------------------


def test_missing_profile_fail_closed(db) -> None:
    with pytest.raises(SourceProfilePersistenceError, match="profile_not_found"):
        get_profile(db, 999999)


def test_legacy_seed_guard() -> None:
    with pytest.raises(SourceProfilePersistenceError, match="legacy_seed_deferred_to_p1_l1"):
        assert_no_legacy_seed_in_p1()


def test_immutable_update_api_rejected() -> None:
    with pytest.raises(
        SourceProfilePersistenceError, match="immutable_profile_version_update_forbidden"
    ):
        reject_immutable_version_mutation(version_id=1, specialty_domain="hack")
    # No production update function exported.
    assert not hasattr(p1, "update_profile_version")
    assert not hasattr(p1, "patch_profile_version")


def test_explicit_fields_round_trip(db) -> None:
    profile = create_or_get_profile(db, canonical_key="round-trip")
    db.commit()
    version = append_profile_version(
        db, profile_id=profile.id, governance_evidence=_base_evidence()
    )
    db.commit()
    loaded = get_exact_profile_version(db, profile_id=profile.id, version_id=version.id)
    assert loaded.source_class == SourceClass.KNOWLEDGE_DOCUMENT.value
    assert loaded.snapshot_schema_version == SNAPSHOT_SCHEMA_VERSION


def test_no_authority_json_blob_on_model() -> None:
    colnames = {c.name for c in GovernedSourceProfileVersion.__table__.columns}
    for forbidden in ("authority_json", "snapshot_json", "immutable_snapshot", "metadata_json"):
        assert forbidden not in colnames


# ---------------------------------------------------------------------------
# Migration / purity / scope
# ---------------------------------------------------------------------------


def test_migration_051_source_static() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "051_i5b2_governed_source_profile.py"
    )
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "051_i5b2_governed_source_profile"' in source
    assert 'down_revision: Union[str, None] = "050_gate4_event_idem"' in source
    assert "ck_governed_source_profiles_locator_pair" in source
    assert "ck_gspv_supersedes_not_self" in source
    assert "fk_gspv_supersedes_same_profile" in source
    assert "fk_gsp_current_version_same_profile" in source
    assert "No seed" in source
    assert 'server_default=sa.text("now()")' in source
    assert "op.alter_table(\"knowledge_sources\"" not in source
    assert "def downgrade" in source
    assert "CREATE TRIGGER" not in source.upper()


def test_orm_migration_timestamp_server_default_parity() -> None:
    """FIX1-A8: ORM server_default=func.now() matches migration now()."""
    profile_created = GovernedSourceProfile.__table__.c.created_at
    profile_updated = GovernedSourceProfile.__table__.c.updated_at
    version_created = GovernedSourceProfileVersion.__table__.c.created_at
    assert profile_created.server_default is not None
    assert profile_updated.server_default is not None
    assert version_created.server_default is not None
    for col in (profile_created, profile_updated, version_created):
        rendered = str(col.server_default.arg)
        assert "now" in rendered.casefold()
    mig = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "051_i5b2_governed_source_profile.py"
    ).read_text(encoding="utf-8")
    assert mig.count('server_default=sa.text("now()")') == 3


def test_p1_module_purity_and_scope_regression() -> None:
    path = Path(inspect.getsourcefile(p1) or "")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            assert not node.module.startswith("backend.app.routers")
            assert "scheduler" not in node.module
    for root in ("requests", "httpx", "fastapi", "alembic", "apscheduler"):
        assert root not in imported
    assert "No DB trigger" in source
    assert "existing_fingerprint_is_not_current" in source
    assert "begin_nested" in source
    assert "Normal approved service writers serialize on the profile row" in source
    assert "final defense" in source
    assert 'timespec="microseconds"' in source
    assert "ipaddress" in source
    assert REASON_LOCATOR_URL_INVALID in source
    assert "_canonical_utc_instant" in source
    # Second-only strftime must not be the fingerprint time path.
    assert 'strftime("%Y-%m-%dT%H:%M:%SZ")' not in source


def test_models_have_no_p2_p3_tables() -> None:
    import backend.app.models as models

    names = set(models.Base.metadata.tables)
    assert "governed_source_profiles" in names
    assert "governed_source_profile_versions" in names
    for forbidden in (
        "raw_acquisition_objects",
        "governed_fetch_runs",
        "publication_releases",
        "provenance_records",
    ):
        assert forbidden not in names


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_class", "bogus"),
        ("license_status", "bogus"),
        ("freshness_policy_days", True),
        ("iran_first_applicable", 1),
        ("effective_at", datetime(2026, 1, 1)),
    ],
)
def test_governance_evidence_validation_fail_closed(field: str, value: object) -> None:
    raw = _base_evidence()
    raw[field] = value
    with pytest.raises(SourceProfilePersistenceError):
        coerce_governance_evidence(raw)


def test_cross_profile_version_retrieval_fail_closed(db) -> None:
    a = create_or_get_profile(db, canonical_key="iso-a")
    b = create_or_get_profile(db, canonical_key="iso-b")
    db.commit()
    va = append_profile_version(db, profile_id=a.id, governance_evidence=_base_evidence())
    db.commit()
    with pytest.raises(SourceProfilePersistenceError, match="profile_version_not_found"):
        get_exact_profile_version(db, profile_id=b.id, version_id=va.id)
