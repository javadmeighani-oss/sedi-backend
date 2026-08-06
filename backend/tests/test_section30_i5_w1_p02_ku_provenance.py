"""Section 30 / W1-P02 — KU / provenance / raw retention contracts (authored).

Static T1–T4 are NOT in the PostgreSQL runtime selector manifest.
Runtime T5+ are selected by w1p02-postgresql-knowledge-retention-runtime.yml.
"""

from __future__ import annotations

import importlib
from datetime import datetime
from typing import Any, Callable

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers


def _load_w1p02():
    models = importlib.import_module("backend.app.models")
    enums = importlib.import_module("backend.app.services.i5.enums")
    ku_svc = importlib.import_module("backend.app.services.i5.knowledge_unit_service")
    prov_svc = importlib.import_module("backend.app.services.i5.provenance_service")
    return models, enums, ku_svc, prov_svc


def _model_by_name(name: str):
    models, *_ = _load_w1p02()
    return getattr(models, name)


def _pg_only(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _require_postgres(db) -> None:
    if not _pg_only(db):
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


def _constraint_blob(exc: BaseException) -> str:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    parts = [str(name or ""), str(orig or ""), str(exc)]
    return " | ".join(parts)


NAMED_INTEGRITY_OVERLAP_ACCEPT: dict[str, frozenset[str]] = {
    "ck_ire_retention_mode_vocab": frozenset(
        {"ck_ire_retention_mode_vocab", "ck_ire_prohibited_requires_excluded_mode"}
    ),
    "ck_ire_prohibited_requires_excluded_mode": frozenset(
        {"ck_ire_prohibited_requires_excluded_mode", "ck_ire_retention_mode_vocab"}
    ),
    "ck_ku_runtime_eligibility_vocab": frozenset(
        {"ck_ku_runtime_eligibility_vocab", "ck_ku_eligible_requires_provenance"}
    ),
    "ck_ku_eligible_requires_provenance": frozenset(
        {"ck_ku_eligible_requires_provenance", "ck_ku_runtime_eligibility_vocab"}
    ),
}


def _expect_named_integrity(
    db, *, constraint: str, mutate, accept_any_of: frozenset[str] | None = None
) -> None:
    _require_postgres(db)
    with pytest.raises(IntegrityError) as ei:
        with db.begin_nested():
            mutate()
            db.flush()
    blob = _constraint_blob(ei.value)
    if accept_any_of is None:
        accept_any_of = NAMED_INTEGRITY_OVERLAP_ACCEPT.get(constraint)
    allowed = accept_any_of if accept_any_of is not None else frozenset({constraint})
    assert constraint in allowed
    assert any(name in blob for name in allowed), (sorted(allowed), blob)


VALID_HASH = "a" * 64
_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


W1P02_ENUM_CLASSES: tuple[str, ...] = (
    "RawRetentionMode",
    "RawStorageMode",
    "RightsTermsState",
    "RobotsAccessState",
    "RedactionState",
    "ProhibitedDataState",
    "ExpiryState",
    "KnowledgeType",
    "EvidenceStrength",
    "MedicalSafetyState",
    "ConflictState",
    "FreshnessState",
    "ReviewState",
    "PublicationState",
    "KnowledgeUnitRuntimeEligibility",
)

EXPECTED_CHECK_NAMES: frozenset[str] = frozenset(
    {
        "ck_ku_eligible_requires_provenance",
        "ck_ire_retention_mode_vocab",
        "ck_ire_content_hash_format",
        "ck_ire_prohibited_requires_excluded_mode",
        "ck_ku_knowledge_type_vocab",
        "ck_ku_canonical_hash_format",
        "ck_ku_runtime_eligibility_vocab",
        "ck_kp_retrieval_method_nonempty",
        "uq_ku_deduplication_key",
        "uq_kp_knowledge_unit_id",
        "fk_kp_knowledge_unit_id",
        "fk_ire_source_profile_id",
        "fk_knowledge_gaps_target_knowledge_unit_id",
    }
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_gsp(**overrides):
    models, *_ = _load_w1p02()
    base = dict(
        canonical_key="w1p02-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


def _build_raw_evidence(source_profile_id: int, **overrides):
    models, *_ = _load_w1p02()
    base = dict(
        source_profile_id=source_profile_id,
        retrieval_timestamp=datetime(2026, 1, 1, 12, 0, 0),
        canonical_url="https://example.test/w1p02/" + _det_hex(4),
        content_hash=_det_hex(32),
        hash_algorithm="SHA-256",
        storage_mode="NONE",
        retention_mode="RAW_MINIMAL_EVIDENCE_ONLY",
        rights_terms_state="UNKNOWN",
        robots_access_state="UNKNOWN",
        redaction_state="NONE",
        prohibited_data_state="UNKNOWN",
        expiry_state="ACTIVE",
    )
    base.update(overrides)
    return models.I5RawEvidence(**base)


def _build_ku(**overrides):
    models, *_ = _load_w1p02()
    stmt = overrides.pop("normalized_statement", "W1-P02 demo normalized statement")
    domain = overrides.get("domain", "neurology")
    knowledge_type = overrides.get("knowledge_type", "FACT")
    dedupe = overrides.pop("deduplication_key", None) or _det_hex(32)
    canon = overrides.pop("canonical_hash", None) or _det_hex(32)
    base = dict(
        canonical_unit_id="ku-" + _det_hex(8),
        immutable_version_id="v-" + _det_hex(8),
        domain=domain,
        language="en",
        knowledge_type=knowledge_type,
        normalized_statement=stmt,
        evidence_strength="UNKNOWN",
        medical_safety_state="UNKNOWN",
        conflict_state="NONE",
        freshness_state="UNKNOWN",
        review_state="NOT_REVIEWED",
        publication_state="DRAFT",
        runtime_eligibility="NOT_ELIGIBLE",
        provenance_complete=False,
        deduplication_key=dedupe,
        canonical_hash=canon,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.KnowledgeUnit(**base)


def _build_provenance(knowledge_unit_id: int, source_profile_id: int, **overrides):
    models, *_ = _load_w1p02()
    base = dict(
        knowledge_unit_id=knowledge_unit_id,
        source_profile_id=source_profile_id,
        retrieval_method="MANUAL_FIXTURE",
    )
    base.update(overrides)
    return models.KnowledgeProvenance(**base)


def _build_gap(**overrides):
    models, *_ = _load_w1p02()
    base = dict(
        canonical_gap_key=_det_hex(32),
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        domain="neurology",
        gap_type="MISSING",
        title="w1p02 demo gap",
        priority="P2",
        severity="MEDIUM",
        urgency="NORMAL",
        status="OPEN",
    )
    base.update(overrides)
    return models.KnowledgeGap(**base)


# ===========================================================================
# T1 — enums (static)
# ===========================================================================


def test_W1P02_T1_enum_imports_and_literals() -> None:
    from enum import Enum

    _, enums, *_ = _load_w1p02()
    modes = list(enums.RawRetentionMode)
    assert len(modes) == 5
    assert {m.value for m in modes} == {
        "RAW_FULL_GOVERNED_RETENTION",
        "RAW_TRANSIENT_PROCESSING",
        "RAW_MINIMAL_EVIDENCE_ONLY",
        "RAW_LINK_AND_CITATION_ONLY",
        "RAW_EXCLUDED_PROTECTED_ELEMENTS",
    }
    for member in enums.KnowledgeUnitRuntimeEligibility:
        assert member.value == member.name
    for name in W1P02_ENUM_CLASSES:
        assert hasattr(enums, name), name
        cls = getattr(enums, name)
        assert issubclass(cls, Enum)
        for member in cls:
            assert member.value == member.name


# ===========================================================================
# T2 — configure_mappers / model presence / zero relationships (static)
# ===========================================================================


def test_W1P02_T2_models_configure_and_zero_relationships() -> None:
    models, *_ = _load_w1p02()
    configure_mappers()
    for name in ("I5RawEvidence", "KnowledgeUnit", "KnowledgeProvenance"):
        assert hasattr(models, name), name
    gap = models.KnowledgeGap
    tku_col = gap.__table__.c.target_knowledge_unit_id
    fk_targets = {fk.column.table.name for fk in tku_col.foreign_keys}
    assert "knowledge_units" in fk_targets
    for name in ("I5RawEvidence", "KnowledgeUnit", "KnowledgeProvenance"):
        mapper = sa_inspect(getattr(models, name))
        assert len(list(mapper.relationships)) == 0, name


# ===========================================================================
# T3 — metadata ledgers (static)
# ===========================================================================


def test_W1P02_T3_metadata_constraint_ledgers() -> None:
    models, *_ = _load_w1p02()
    names: set[str] = set()
    for table in (
        models.I5RawEvidence.__table__,
        models.KnowledgeUnit.__table__,
        models.KnowledgeProvenance.__table__,
        models.KnowledgeGap.__table__,
    ):
        for c in table.constraints:
            if isinstance(c, (CheckConstraint, UniqueConstraint, ForeignKeyConstraint)):
                if c.name:
                    names.add(c.name)
        for fk in table.foreign_keys:
            if fk.constraint is not None and fk.constraint.name:
                names.add(fk.constraint.name)
    for required in EXPECTED_CHECK_NAMES:
        assert required in names, required


# ===========================================================================
# T4 — pure services (static)
# ===========================================================================


def test_W1P02_T4_service_pure_functions() -> None:
    _, enums, ku_svc, prov_svc = _load_w1p02()
    k1 = ku_svc.build_deduplication_key("d", "t", "p", "j", "content")
    k2 = ku_svc.build_deduplication_key("d", "t", "p", "j", "content")
    assert k1 == k2
    assert len(k1) == 64
    assert k1 != ku_svc.build_deduplication_key("d", "t", "p", "j", "other")
    h = ku_svc.build_canonical_hash("stmt", "d", "FACT")
    assert len(h) == 64 and h == ku_svc.build_canonical_hash("stmt", "d", "FACT")
    elig = ku_svc.evaluate_runtime_eligibility(
        {"provenance_complete": False, "runtime_eligibility": "ELIGIBLE"}
    )
    assert elig is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    elig2 = ku_svc.evaluate_runtime_eligibility(
        {"provenance_complete": True, "runtime_eligibility": "ELIGIBLE"}
    )
    assert elig2 is enums.KnowledgeUnitRuntimeEligibility.ELIGIBLE
    with pytest.raises(ku_svc.KnowledgeUnitServiceError):
        ku_svc.validate_no_pii_markers("user password=secret")
    assert prov_svc.is_provenance_complete(
        {"knowledge_unit_id": 1, "source_profile_id": 2, "retrieval_method": "HTTP"}
    )
    assert not prov_svc.is_provenance_complete(
        {"knowledge_unit_id": 1, "source_profile_id": 2, "retrieval_method": ""}
    )
    lineage = prov_svc.attach_hash_lineage({}, content_hash=VALID_HASH)
    assert lineage["content_hash"] == VALID_HASH


# ===========================================================================
# T5 — metadata / catalog (runtime)
# ===========================================================================


def test_W1P02_T5_01_metadata_contains_ku_tables(db) -> None:
    _require_postgres(db)
    models, *_ = _load_w1p02()
    tables = set(models.Base.metadata.tables.keys())
    for name in ("i5_raw_evidence", "knowledge_units", "knowledge_provenance"):
        assert name in tables
    inspector = sa_inspect(db.get_bind())
    present = set(inspector.get_table_names())
    for name in ("i5_raw_evidence", "knowledge_units", "knowledge_provenance"):
        assert name in present


def test_W1P02_T5_02_named_checks_present_in_pg_catalog(db) -> None:
    _require_postgres(db)
    wanted = sorted(
        n for n in EXPECTED_CHECK_NAMES if n.startswith("ck_") or n.startswith("uq_") or n.startswith("fk_")
    )
    rows = db.execute(
        text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            WHERE nsp.nspname = 'public'
              AND rel.relname IN (
                'i5_raw_evidence', 'knowledge_units', 'knowledge_provenance', 'knowledge_gaps'
              )
            """
        )
    ).fetchall()
    present = {r[0] for r in rows}
    missing = [n for n in wanted if n not in present]
    assert not missing, missing


# ===========================================================================
# T6 — positive inserts (runtime)
# ===========================================================================


def test_W1P02_T6_01_positive_raw_evidence_insert(db) -> None:
    _require_postgres(db)
    gsp = _build_gsp()
    db.add(gsp)
    db.flush()
    raw = _build_raw_evidence(gsp.id)
    db.add(raw)
    db.flush()
    assert raw.id is not None


def test_W1P02_T6_02_positive_ku_insert_not_eligible(db) -> None:
    _require_postgres(db)
    ku = _build_ku(provenance_complete=False, runtime_eligibility="NOT_ELIGIBLE")
    db.add(ku)
    db.flush()
    assert ku.id is not None
    assert ku.provenance_complete is False
    assert ku.runtime_eligibility == "NOT_ELIGIBLE"


def test_W1P02_T6_03_positive_provenance_attach_eligible(db) -> None:
    _require_postgres(db)
    gsp = _build_gsp()
    db.add(gsp)
    db.flush()
    ku = _build_ku(provenance_complete=False, runtime_eligibility="NOT_ELIGIBLE")
    db.add(ku)
    db.flush()
    prov = _build_provenance(ku.id, gsp.id)
    db.add(prov)
    db.flush()
    ku.provenance_complete = True
    ku.runtime_eligibility = "ELIGIBLE"
    db.flush()
    assert prov.id is not None
    assert ku.provenance_complete is True
    assert ku.runtime_eligibility == "ELIGIBLE"


def test_W1P02_T6_04_positive_gap_target_ku_fk(db) -> None:
    _require_postgres(db)
    ku = _build_ku()
    db.add(ku)
    db.flush()
    gap = _build_gap(target_knowledge_unit_id=ku.id)
    db.add(gap)
    db.flush()
    assert gap.target_knowledge_unit_id == ku.id


# ===========================================================================
# T7 — negative CHECKs (runtime, parametrized)
# ===========================================================================


def _t7_cases() -> list[tuple[str, Callable]]:
    cases: list[tuple[str, Callable]] = []

    def add(name: str, factory: Callable) -> None:
        cases.append((name, factory))

    add(
        "ck_ire_retention_mode_vocab",
        lambda db: _mutate_raw(db, retention_mode="NOT_A_MODE"),
    )
    add(
        "ck_ire_content_hash_format",
        lambda db: _mutate_raw(db, content_hash="not-a-hash"),
    )
    add(
        "ck_ire_prohibited_requires_excluded_mode",
        lambda db: _mutate_raw(
            db,
            prohibited_data_state="CONFIRMED_PROHIBITED",
            retention_mode="RAW_FULL_GOVERNED_RETENTION",
        ),
    )
    add(
        "ck_ire_storage_mode_vocab",
        lambda db: _mutate_raw(db, storage_mode="DISK_CRATE"),
    )
    add(
        "ck_ire_byte_hash_format",
        lambda db: _mutate_raw(db, byte_hash="zz"),
    )
    add(
        "ck_ire_hash_algorithm_constant",
        lambda db: _mutate_raw(db, hash_algorithm="MD5"),
    )
    add(
        "ck_ire_canonical_url_nonempty",
        lambda db: _mutate_raw(db, canonical_url=""),
    )
    add(
        "ck_ku_knowledge_type_vocab",
        lambda db: _mutate_ku(db, knowledge_type="NOT_A_TYPE"),
    )
    add(
        "ck_ku_canonical_hash_format",
        lambda db: _mutate_ku(db, canonical_hash="bad"),
    )
    add(
        "ck_ku_eligible_requires_provenance",
        lambda db: _mutate_ku(
            db, provenance_complete=False, runtime_eligibility="ELIGIBLE"
        ),
    )
    add(
        "ck_ku_runtime_eligibility_vocab",
        lambda db: _mutate_ku(db, runtime_eligibility="YES_PLEASE"),
    )
    add(
        "ck_ku_deduplication_key_format",
        lambda db: _mutate_ku(db, deduplication_key="short"),
    )
    add(
        "ck_ku_hash_algorithm_constant",
        lambda db: _mutate_ku(db, hash_algorithm="SHA1"),
    )
    add(
        "ck_ku_canonicalization_version_constant",
        lambda db: _mutate_ku(db, canonicalization_version="v2"),
    )
    add(
        "ck_ku_normalized_statement_nonempty",
        lambda db: _mutate_ku(db, normalized_statement=""),
    )
    add(
        "ck_ku_evidence_strength_vocab",
        lambda db: _mutate_ku(db, evidence_strength="SUPER"),
    )
    add(
        "ck_ku_publication_state_vocab",
        lambda db: _mutate_ku(db, publication_state="LIVE"),
    )
    add(
        "ck_ku_medical_safety_state_vocab",
        lambda db: _mutate_ku(db, medical_safety_state="UNSAFE"),
    )
    add(
        "ck_kp_retrieval_method_nonempty",
        lambda db: _mutate_prov(db, retrieval_method=""),
    )
    add(
        "ck_kp_content_hash_format",
        lambda db: _mutate_prov(db, content_hash="nope"),
    )
    return cases


def _ensure_gsp(db):
    gsp = _build_gsp()
    db.add(gsp)
    db.flush()
    return gsp


def _mutate_raw(db, **overrides) -> None:
    gsp = _ensure_gsp(db)
    db.add(_build_raw_evidence(gsp.id, **overrides))


def _mutate_ku(db, **overrides) -> None:
    db.add(_build_ku(**overrides))


def _mutate_prov(db, **overrides) -> None:
    gsp = _ensure_gsp(db)
    ku = _build_ku()
    db.add(ku)
    db.flush()
    db.add(_build_provenance(ku.id, gsp.id, **overrides))


_T7_CASES = _t7_cases()


@pytest.mark.parametrize(
    "constraint,factory",
    _T7_CASES,
    ids=[f"W1P02-T7-{c}" for c, _ in _T7_CASES],
)
def test_W1P02_T7_negative_check_constraints(db, constraint: str, factory) -> None:
    _require_postgres(db)
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: factory(db))


# ===========================================================================
# T8 — UQ / FK negatives (runtime)
# ===========================================================================


def _t8_cases() -> list[tuple[str, Callable]]:
    cases: list[tuple[str, Callable]] = []

    def uq_dedupe(db) -> None:
        key = _det_hex(32)
        db.add(_build_ku(deduplication_key=key))
        db.flush()
        db.add(_build_ku(deduplication_key=key))

    def uq_prov(db) -> None:
        gsp = _ensure_gsp(db)
        ku = _build_ku()
        db.add(ku)
        db.flush()
        db.add(_build_provenance(ku.id, gsp.id))
        db.flush()
        db.add(_build_provenance(ku.id, gsp.id, retrieval_method="SECOND"))

    def uq_canon_ver(db) -> None:
        cid, vid = "canon-" + _det_hex(4), "ver-" + _det_hex(4)
        db.add(
            _build_ku(
                canonical_unit_id=cid,
                immutable_version_id=vid,
                deduplication_key=_det_hex(32),
            )
        )
        db.flush()
        db.add(
            _build_ku(
                canonical_unit_id=cid,
                immutable_version_id=vid,
                deduplication_key=_det_hex(32),
            )
        )

    def fk_kp_ku(db) -> None:
        gsp = _ensure_gsp(db)
        db.add(_build_provenance(999999001, gsp.id))

    def fk_kp_gsp(db) -> None:
        ku = _build_ku()
        db.add(ku)
        db.flush()
        db.add(_build_provenance(ku.id, 999999002))

    def fk_ire_gsp(db) -> None:
        db.add(_build_raw_evidence(999999003))

    def fk_kp_raw(db) -> None:
        gsp = _ensure_gsp(db)
        ku = _build_ku()
        db.add(ku)
        db.flush()
        db.add(_build_provenance(ku.id, gsp.id, raw_evidence_id=999999004))

    def fk_gap_tku(db) -> None:
        db.add(_build_gap(target_knowledge_unit_id=999999005))

    cases.append(("uq_ku_deduplication_key", uq_dedupe))
    cases.append(("uq_kp_knowledge_unit_id", uq_prov))
    cases.append(("uq_ku_canonical_version", uq_canon_ver))
    cases.append(("fk_kp_knowledge_unit_id", fk_kp_ku))
    cases.append(("fk_kp_source_profile_id", fk_kp_gsp))
    cases.append(("fk_ire_source_profile_id", fk_ire_gsp))
    cases.append(("fk_kp_raw_evidence_id", fk_kp_raw))
    cases.append(("fk_knowledge_gaps_target_knowledge_unit_id", fk_gap_tku))
    return cases


_T8_CASES = _t8_cases()


@pytest.mark.parametrize(
    "constraint,factory",
    _T8_CASES,
    ids=[f"W1P02-T8-{c}" for c, _ in _T8_CASES],
)
def test_W1P02_T8_uq_fk_runtime_negative(db, constraint: str, factory) -> None:
    _require_postgres(db)
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: factory(db))


# ===========================================================================
# T9 — service + retention modes (runtime)
# ===========================================================================


def test_W1P02_T9_01_service_eligibility_evaluation(db) -> None:
    _require_postgres(db)
    _, enums, ku_svc, _ = _load_w1p02()
    # Persist only a CHECK-valid row; service fail-closed is evaluated in-memory
    # (ELIGIBLE + provenance_complete=False is rejected by ck_ku_eligible_requires_provenance).
    ku = _build_ku(provenance_complete=False, runtime_eligibility="NOT_ELIGIBLE")
    db.add(ku)
    db.flush()
    assert (
        ku_svc.evaluate_runtime_eligibility(
            {"provenance_complete": False, "runtime_eligibility": "ELIGIBLE"}
        )
        is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    )
    assert (
        ku_svc.evaluate_runtime_eligibility(ku)
        is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    )
    ku.provenance_complete = True
    ku.runtime_eligibility = "ELIGIBLE"
    db.flush()
    assert (
        ku_svc.evaluate_runtime_eligibility(ku)
        is enums.KnowledgeUnitRuntimeEligibility.ELIGIBLE
    )


@pytest.mark.parametrize(
    "retention_mode",
    [
        "RAW_FULL_GOVERNED_RETENTION",
        "RAW_TRANSIENT_PROCESSING",
        "RAW_MINIMAL_EVIDENCE_ONLY",
        "RAW_LINK_AND_CITATION_ONLY",
        "RAW_EXCLUDED_PROTECTED_ELEMENTS",
    ],
    ids=[
        "W1P02-T9-RAW_FULL_GOVERNED_RETENTION",
        "W1P02-T9-RAW_TRANSIENT_PROCESSING",
        "W1P02-T9-RAW_MINIMAL_EVIDENCE_ONLY",
        "W1P02-T9-RAW_LINK_AND_CITATION_ONLY",
        "W1P02-T9-RAW_EXCLUDED_PROTECTED_ELEMENTS",
    ],
)
def test_W1P02_T9_02_raw_retention_mode_insertable(db, retention_mode: str) -> None:
    _require_postgres(db)
    gsp = _ensure_gsp(db)
    prohibited = (
        "CONFIRMED_PROHIBITED"
        if retention_mode == "RAW_EXCLUDED_PROTECTED_ELEMENTS"
        else "CLEARED"
    )
    raw = _build_raw_evidence(
        gsp.id,
        retention_mode=retention_mode,
        prohibited_data_state=prohibited,
        content_hash=_det_hex(32),
        canonical_url="https://example.test/mode/" + retention_mode.lower(),
    )
    db.add(raw)
    db.flush()
    assert raw.id is not None
    assert raw.retention_mode == retention_mode
