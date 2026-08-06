"""Section 30 / W2-P01 — Knowledge Memory / Versioning / Diff / Supersession (authored).

Static T1–T4 are NOT in the PostgreSQL runtime selector manifest.
Runtime T5+ are selected by w2p01-postgresql-knowledge-memory-runtime.yml.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers


def _load_w2p01():
    models = importlib.import_module("backend.app.models")
    enums = importlib.import_module("backend.app.services.i5.enums")
    mem_svc = importlib.import_module("backend.app.services.i5.knowledge_memory_service")
    sup_svc = importlib.import_module("backend.app.services.i5.supersession_service")
    return models, enums, mem_svc, sup_svc


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
    "ck_kmi_runtime_eligibility_vocab": frozenset(
        {"ck_kmi_runtime_eligibility_vocab", "ck_kmi_eligible_requires_current"}
    ),
    "ck_kmi_eligible_requires_current": frozenset(
        {"ck_kmi_eligible_requires_current", "ck_kmi_runtime_eligibility_vocab"}
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


_DET_SEQ = 0
VALID_HASH = "b" * 64


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


EXPECTED_CHECK_NAMES: frozenset[str] = frozenset(
    {
        "ck_kmi_evidence_strength_vocab",
        "ck_kmi_freshness_state_vocab",
        "ck_kmi_conflict_state_vocab",
        "ck_kmi_medical_safety_state_vocab",
        "ck_kmi_runtime_eligibility_vocab",
        "ck_kmi_supersession_state_vocab",
        "ck_kmi_eligible_requires_current",
        "ck_kmt_transition_kind_vocab",
        "ck_kmt_change_kind_vocab",
        "ck_kmt_idempotency_key_format",
        "ck_kmt_diff_json_object",
        "uq_kmi_memory_item_id",
        "uq_kmi_knowledge_unit_id",
        "uq_kmt_idempotency_key",
        "fk_kmi_knowledge_unit_id",
        "fk_kmt_memory_item_row_id",
        "fk_kmt_from_knowledge_unit_id",
        "fk_kmt_to_knowledge_unit_id",
    }
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_gsp(**overrides):
    models, *_ = _load_w2p01()
    base = dict(
        canonical_key="w2p01-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


def _build_ku(**overrides):
    models, *_ = _load_w2p01()
    stmt = overrides.pop("normalized_statement", "W2-P01 demo normalized statement")
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
    models, *_ = _load_w2p01()
    base = dict(
        knowledge_unit_id=knowledge_unit_id,
        source_profile_id=source_profile_id,
        retrieval_method="MANUAL_FIXTURE",
    )
    base.update(overrides)
    return models.KnowledgeProvenance(**base)


def _build_memory(knowledge_unit_id: int, **overrides):
    models, _, mem_svc, _ = _load_w2p01()
    domain = overrides.pop("domain", "neurology")
    topic = overrides.pop("topic", "migraine")
    canonical_unit_id = overrides.pop("canonical_unit_id", "canon-" + _det_hex(4))
    mid = overrides.pop("memory_item_id", None) or mem_svc.build_memory_item_id(
        domain, topic, canonical_unit_id
    )
    base = dict(
        memory_item_id=mid,
        knowledge_unit_id=knowledge_unit_id,
        domain=domain,
        topic=topic,
        knowledge_version=overrides.pop("knowledge_version", "v-" + _det_hex(4)),
        evidence_strength="UNKNOWN",
        freshness_state="UNKNOWN",
        conflict_state="NONE",
        medical_safety_state="UNKNOWN",
        runtime_eligibility="NOT_ELIGIBLE",
        supersession_state="CURRENT",
    )
    base.update(overrides)
    return models.KnowledgeMemoryItem(**base)


def _build_transition(memory_row_id: int, memory_item_id: str, **overrides):
    models, *_ = _load_w2p01()
    base = dict(
        memory_row_id=memory_row_id,
        memory_item_id=memory_item_id,
        transition_kind="CREATED",
        change_kind="NO_MATERIAL_CHANGE",
        idempotency_key=_det_hex(32),
        process_id="W2P01_SUPERSESSION_SERVICE",
    )
    base.update(overrides)
    return models.KnowledgeMemoryTransition(**base)


def _ensure_ku(db, **overrides):
    ku = _build_ku(**overrides)
    db.add(ku)
    db.flush()
    return ku


def _ensure_memory(db, **overrides):
    ku = overrides.pop("ku", None) or _ensure_ku(db)
    mem = _build_memory(
        ku.id,
        canonical_unit_id=ku.canonical_unit_id,
        knowledge_version=ku.immutable_version_id,
        domain=ku.domain,
        topic=overrides.pop("topic", ku.topic_taxonomy or "migraine"),
        **overrides,
    )
    db.add(mem)
    db.flush()
    return ku, mem


# ===========================================================================
# T1 — enums (static)
# ===========================================================================


def test_W2P01_T1_enum_imports_and_literals() -> None:
    from enum import Enum

    _, enums, *_ = _load_w2p01()
    for name in ("SupersessionState", "MemoryChangeKind", "MemoryTransitionKind"):
        assert hasattr(enums, name), name
        cls = getattr(enums, name)
        assert issubclass(cls, Enum)
        for member in cls:
            assert member.value == member.name
    assert enums.SupersessionState.CURRENT.value == "CURRENT"
    assert enums.MemoryChangeKind.CONTENT_CHANGE.value == "CONTENT_CHANGE"
    assert enums.MemoryTransitionKind.SUPERSEDED.value == "SUPERSEDED"


# ===========================================================================
# T2 — configure_mappers / zero relationships (static)
# ===========================================================================


def test_W2P01_T2_models_configure_and_zero_relationships() -> None:
    models, *_ = _load_w2p01()
    configure_mappers()
    for name in ("KnowledgeMemoryItem", "KnowledgeMemoryTransition", "KnowledgeUnit"):
        assert hasattr(models, name), name
        mapper = sa_inspect(getattr(models, name))
        assert len(list(mapper.relationships)) == 0, name
    assert "supersedes_unit_id" in models.KnowledgeUnit.__table__.c
    assert "superseded_by" not in models.KnowledgeUnit.__table__.c


# ===========================================================================
# T3 — metadata ledgers (static)
# ===========================================================================


def test_W2P01_T3_metadata_constraint_ledgers() -> None:
    models, *_ = _load_w2p01()
    names: set[str] = set()
    for table in (
        models.KnowledgeMemoryItem.__table__,
        models.KnowledgeMemoryTransition.__table__,
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


def test_W2P01_T4_service_pure_functions() -> None:
    _, enums, mem_svc, sup_svc = _load_w2p01()
    mid = mem_svc.build_memory_item_id("neurology", "migraine", "canon-1")
    assert mid == mem_svc.build_memory_item_id("neurology", "migraine", "canon-1")
    assert len(mid) == 64
    with pytest.raises(mem_svc.KnowledgeMemoryServiceError):
        mem_svc.assert_not_user_memory_path("/data/user_memory/foo")
    elig = mem_svc.evaluate_memory_eligibility(
        {"supersession_state": "SUPERSEDED", "runtime_eligibility": "ELIGIBLE"}
    )
    assert elig is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    projected = mem_svc.project_from_knowledge_unit(
        {
            "id": 1,
            "domain": "neurology",
            "topic_taxonomy": "migraine",
            "canonical_unit_id": "c1",
            "immutable_version_id": "v1",
            "runtime_eligibility": "NOT_ELIGIBLE",
        }
    )
    assert projected["knowledge_unit_id"] == 1
    assert projected["knowledge_version"] == "v1"
    old = {
        "id": 1,
        "canonical_unit_id": "c1",
        "normalized_statement": "a",
        "canonical_hash": "a" * 64,
        "evidence_strength": "LOW",
        "medical_safety_state": "UNKNOWN",
        "conflict_state": "NONE",
        "freshness_state": "UNKNOWN",
        "publication_state": "PUBLISHED",
        "runtime_eligibility": "NOT_ELIGIBLE",
        "applicability": None,
        "exclusions": None,
        "retraction_reason": None,
    }
    new = dict(old, id=2, normalized_statement="b", canonical_hash="c" * 64)
    diff = sup_svc.compute_structured_diff(old, new)
    assert diff["change_kind"] == enums.MemoryChangeKind.CONTENT_CHANGE.value
    assert "normalized_statement" in diff["changed_fields"]
    with pytest.raises(sup_svc.SupersessionServiceError):
        sup_svc.validate_supersession_link(old, old)
    with pytest.raises(sup_svc.SupersessionServiceError):
        sup_svc.validate_supersession_link(
            dict(new, canonical_unit_id="other"), old
        )
    no_change = sup_svc.apply_no_change_result(
        memory_item_id=mid, canonical_hash="a" * 64
    )
    assert no_change["transition_kind"] == enums.MemoryTransitionKind.NO_CHANGE.value
    resolve = sup_svc.resolve_superseded_by({1: [2, 3]}, 1)
    assert resolve == [2, 3]


# ===========================================================================
# T5 — metadata / catalog (runtime)
# ===========================================================================


def test_W2P01_T5_01_metadata_contains_memory_tables(db) -> None:
    _require_postgres(db)
    models, *_ = _load_w2p01()
    tables = set(models.Base.metadata.tables.keys())
    for name in ("knowledge_memory_items", "knowledge_memory_transitions", "knowledge_units"):
        assert name in tables
    inspector = sa_inspect(db.get_bind())
    present = set(inspector.get_table_names())
    for name in ("knowledge_memory_items", "knowledge_memory_transitions", "knowledge_units"):
        assert name in present


def test_W2P01_T5_02_named_checks_present_in_pg_catalog(db) -> None:
    _require_postgres(db)
    wanted = sorted(
        n
        for n in EXPECTED_CHECK_NAMES
        if n.startswith("ck_") or n.startswith("uq_") or n.startswith("fk_")
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
                'knowledge_memory_items', 'knowledge_memory_transitions', 'knowledge_units'
              )
            """
        )
    ).fetchall()
    present = {r[0] for r in rows}
    missing = [n for n in wanted if n not in present]
    assert not missing, missing


# ===========================================================================
# T6 — positive paths (runtime)
# ===========================================================================


def test_W2P01_T6_01_create_memory_linked_to_ku(db) -> None:
    _require_postgres(db)
    models, enums, mem_svc, _ = _load_w2p01()
    gsp = _build_gsp()
    db.add(gsp)
    db.flush()
    ku = _build_ku(topic_taxonomy="migraine")
    db.add(ku)
    db.flush()
    db.add(_build_provenance(ku.id, gsp.id))
    db.flush()
    projected = mem_svc.project_from_knowledge_unit(
        {
            "id": ku.id,
            "domain": ku.domain,
            "topic_taxonomy": ku.topic_taxonomy,
            "canonical_unit_id": ku.canonical_unit_id,
            "immutable_version_id": ku.immutable_version_id,
            "evidence_strength": ku.evidence_strength,
            "freshness_state": ku.freshness_state,
            "conflict_state": ku.conflict_state,
            "medical_safety_state": ku.medical_safety_state,
            "runtime_eligibility": ku.runtime_eligibility,
            "supersession_state": enums.SupersessionState.CURRENT.value,
        }
    )
    mem = models.KnowledgeMemoryItem(**projected)
    db.add(mem)
    db.flush()
    assert mem.id is not None
    assert mem.knowledge_unit_id == ku.id
    assert mem.memory_item_id == mem_svc.build_memory_item_id(
        ku.domain, ku.topic_taxonomy or "", ku.canonical_unit_id
    )
    tr = _build_transition(
        mem.id,
        mem.memory_item_id,
        transition_kind="CREATED",
        to_knowledge_unit_id=ku.id,
    )
    db.add(tr)
    db.flush()
    assert tr.id is not None


def test_W2P01_T6_02_supersede_updates_memory_and_old_ku(db) -> None:
    _require_postgres(db)
    models, enums, mem_svc, sup_svc = _load_w2p01()
    old_ku = _ensure_ku(db, publication_state="PUBLISHED", runtime_eligibility="NOT_ELIGIBLE")
    _, mem = _ensure_memory(db, ku=old_ku)
    new_ku = _build_ku(
        canonical_unit_id=old_ku.canonical_unit_id,
        immutable_version_id="v-next-" + _det_hex(4),
        supersedes_unit_id=old_ku.id,
        normalized_statement="updated statement " + _det_hex(2),
        canonical_hash=_det_hex(32),
        deduplication_key=_det_hex(32),
        publication_state="PUBLISHED",
    )
    db.add(new_ku)
    db.flush()
    sup_svc.validate_supersession_link(new_ku, old_ku)
    old_ku.publication_state = "SUPERSEDED"
    old_ku.runtime_eligibility = "NOT_ELIGIBLE"
    mem.knowledge_unit_id = new_ku.id
    mem.knowledge_version = new_ku.immutable_version_id
    mem.supersession_state = enums.SupersessionState.CURRENT.value
    diff = sup_svc.compute_structured_diff(
        {
            "normalized_statement": "W2-P01 demo normalized statement",
            "canonical_hash": old_ku.canonical_hash,
            "evidence_strength": old_ku.evidence_strength,
            "medical_safety_state": old_ku.medical_safety_state,
            "conflict_state": old_ku.conflict_state,
            "freshness_state": old_ku.freshness_state,
            "publication_state": "PUBLISHED",
            "runtime_eligibility": "NOT_ELIGIBLE",
            "applicability": None,
            "exclusions": None,
            "retraction_reason": None,
        },
        {
            "normalized_statement": new_ku.normalized_statement,
            "canonical_hash": new_ku.canonical_hash,
            "evidence_strength": new_ku.evidence_strength,
            "medical_safety_state": new_ku.medical_safety_state,
            "conflict_state": new_ku.conflict_state,
            "freshness_state": new_ku.freshness_state,
            "publication_state": new_ku.publication_state,
            "runtime_eligibility": new_ku.runtime_eligibility,
            "applicability": None,
            "exclusions": None,
            "retraction_reason": None,
        },
    )
    tr = _build_transition(
        mem.id,
        mem.memory_item_id,
        transition_kind=enums.MemoryTransitionKind.SUPERSEDED.value,
        change_kind=diff["change_kind"],
        from_knowledge_unit_id=old_ku.id,
        to_knowledge_unit_id=new_ku.id,
        diff_json=sup_svc.structured_diff_to_json(diff),
        idempotency_key=sup_svc.build_idempotency_key(
            mem.memory_item_id, new_ku.canonical_hash, diff["change_kind"]
        ),
    )
    db.add(tr)
    db.flush()
    assert mem.knowledge_unit_id == new_ku.id
    assert old_ku.publication_state == "SUPERSEDED"
    assert old_ku.runtime_eligibility == "NOT_ELIGIBLE"
    assert tr.transition_kind == "SUPERSEDED"
    assert new_ku.supersedes_unit_id == old_ku.id
    _ = mem_svc  # linked projection path exercised above


def test_W2P01_T6_03_structured_diff_content_change(db) -> None:
    _require_postgres(db)
    _, enums, _, sup_svc = _load_w2p01()
    old_ku = _ensure_ku(db, normalized_statement="alpha statement", canonical_hash=_det_hex(32))
    new_ku = _ensure_ku(
        db,
        canonical_unit_id=old_ku.canonical_unit_id,
        normalized_statement="beta statement changed",
        canonical_hash=_det_hex(32),
        deduplication_key=_det_hex(32),
        immutable_version_id="v2-" + _det_hex(4),
    )
    diff = sup_svc.compute_structured_diff(old_ku, new_ku)
    assert diff["change_kind"] == enums.MemoryChangeKind.CONTENT_CHANGE.value
    assert "normalized_statement" in diff["changed_fields"]
    assert diff["field_diffs"]["normalized_statement"]["old"] == "alpha statement"
    assert diff["field_diffs"]["normalized_statement"]["new"] == "beta statement changed"
    assert sup_svc.detect_change_kind(old_ku, new_ku) is enums.MemoryChangeKind.CONTENT_CHANGE


def test_W2P01_T6_04_no_change_idempotent(db) -> None:
    _require_postgres(db)
    models, enums, _, sup_svc = _load_w2p01()
    ku, mem = _ensure_memory(db)
    payload = sup_svc.apply_no_change_result(
        memory_item_id=mem.memory_item_id, canonical_hash=ku.canonical_hash
    )
    assert payload["transition_kind"] == enums.MemoryTransitionKind.NO_CHANGE.value
    tr = _build_transition(
        mem.id,
        mem.memory_item_id,
        transition_kind=payload["transition_kind"],
        change_kind=payload["change_kind"],
        idempotency_key=payload["idempotency_key"],
        to_knowledge_unit_id=ku.id,
    )
    db.add(tr)
    db.flush()
    count_before = db.execute(
        text("SELECT count(*) FROM knowledge_memory_items WHERE memory_item_id = :m"),
        {"m": mem.memory_item_id},
    ).scalar()
    assert count_before == 1
    # Second identical idempotency_key insert must fail UQ
    _expect_named_integrity(
        db,
        constraint="uq_kmt_idempotency_key",
        mutate=lambda: db.add(
            _build_transition(
                mem.id,
                mem.memory_item_id,
                transition_kind=payload["transition_kind"],
                change_kind=payload["change_kind"],
                idempotency_key=payload["idempotency_key"],
                to_knowledge_unit_id=ku.id,
            )
        ),
    )
    count_after = db.execute(
        text("SELECT count(*) FROM knowledge_memory_items WHERE memory_item_id = :m"),
        {"m": mem.memory_item_id},
    ).scalar()
    assert count_after == 1
    _ = models


# ===========================================================================
# T7 — negative CHECKs (runtime, parametrized)
# ===========================================================================


def _mutate_memory(db, **overrides) -> None:
    ku = _ensure_ku(db)
    db.add(
        _build_memory(
            ku.id,
            canonical_unit_id=ku.canonical_unit_id,
            knowledge_version=ku.immutable_version_id,
            **overrides,
        )
    )


def _mutate_transition(db, **overrides) -> None:
    ku, mem = _ensure_memory(db)
    db.add(_build_transition(mem.id, mem.memory_item_id, **overrides))


def _t7_cases() -> list[tuple[str, str, Callable]]:
    """Return (param_id, constraint_name, factory)."""
    cases: list[tuple[str, str, Callable]] = []

    def add(param_id: str, constraint: str, factory: Callable) -> None:
        cases.append((param_id, constraint, factory))

    add(
        "ck_kmi_evidence_strength_vocab",
        "ck_kmi_evidence_strength_vocab",
        lambda db: _mutate_memory(db, evidence_strength="SUPER"),
    )
    add(
        "ck_kmi_freshness_state_vocab",
        "ck_kmi_freshness_state_vocab",
        lambda db: _mutate_memory(db, freshness_state="ROTTEN"),
    )
    add(
        "ck_kmi_conflict_state_vocab",
        "ck_kmi_conflict_state_vocab",
        lambda db: _mutate_memory(db, conflict_state="WAR"),
    )
    add(
        "ck_kmi_medical_safety_state_vocab",
        "ck_kmi_medical_safety_state_vocab",
        lambda db: _mutate_memory(db, medical_safety_state="UNSAFE"),
    )
    add(
        "ck_kmi_runtime_eligibility_vocab",
        "ck_kmi_runtime_eligibility_vocab",
        lambda db: _mutate_memory(db, runtime_eligibility="YES_PLEASE"),
    )
    add(
        "ck_kmi_supersession_state_vocab",
        "ck_kmi_supersession_state_vocab",
        lambda db: _mutate_memory(db, supersession_state="ZOMBIE"),
    )
    add(
        "ck_kmi_eligible_requires_current",
        "ck_kmi_eligible_requires_current",
        lambda db: _mutate_memory(
            db, runtime_eligibility="ELIGIBLE", supersession_state="SUPERSEDED"
        ),
    )
    add(
        "ck_kmi_eligible_requires_current_update",
        "ck_kmi_eligible_requires_current",
        lambda db: _eligible_requires_current_via_update(db),
    )
    add(
        "ck_kmt_transition_kind_vocab",
        "ck_kmt_transition_kind_vocab",
        lambda db: _mutate_transition(db, transition_kind="EXPLODED"),
    )
    add(
        "ck_kmt_change_kind_vocab",
        "ck_kmt_change_kind_vocab",
        lambda db: _mutate_transition(db, change_kind="MAGIC"),
    )
    add(
        "ck_kmt_idempotency_key_format",
        "ck_kmt_idempotency_key_format",
        lambda db: _mutate_transition(db, idempotency_key="not-hex"),
    )
    add(
        "ck_kmt_diff_json_object",
        "ck_kmt_diff_json_object",
        lambda db: _mutate_transition(db, diff_json="[1]"),
    )
    return cases


def _eligible_requires_current_via_update(db) -> None:
    ku, mem = _ensure_memory(
        db, runtime_eligibility="NOT_ELIGIBLE", supersession_state="CURRENT"
    )
    mem.runtime_eligibility = "ELIGIBLE"
    mem.supersession_state = "RETRACTED"
    db.flush()


_T7_CASES = _t7_cases()


@pytest.mark.parametrize(
    "constraint,factory",
    [(c, f) for _, c, f in _T7_CASES],
    ids=[f"W2P01-T7-{pid}" for pid, _, _ in _T7_CASES],
)
def test_W2P01_T7_negative_check_constraints(db, constraint: str, factory) -> None:
    _require_postgres(db)
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: factory(db))


# ===========================================================================
# T8 — UQ / FK negatives (runtime)
# ===========================================================================


def _t8_cases() -> list[tuple[str, Callable]]:
    cases: list[tuple[str, Callable]] = []

    def uq_memory_item_id(db) -> None:
        ku1 = _ensure_ku(db)
        mid = "a" * 64
        db.add(
            _build_memory(
                ku1.id,
                memory_item_id=mid,
                canonical_unit_id=ku1.canonical_unit_id,
                knowledge_version=ku1.immutable_version_id,
            )
        )
        db.flush()
        ku2 = _ensure_ku(db)
        db.add(
            _build_memory(
                ku2.id,
                memory_item_id=mid,
                canonical_unit_id=ku2.canonical_unit_id,
                knowledge_version=ku2.immutable_version_id,
            )
        )

    def uq_knowledge_unit_id(db) -> None:
        ku, mem = _ensure_memory(db)
        db.add(
            _build_memory(
                ku.id,
                memory_item_id=_det_hex(32),
                canonical_unit_id=ku.canonical_unit_id + "-b",
                knowledge_version=ku.immutable_version_id + "-b",
            )
        )
        _ = mem

    def fk_kmi_ku(db) -> None:
        db.add(
            _build_memory(
                999999101,
                memory_item_id=_det_hex(32),
                canonical_unit_id="missing",
                knowledge_version="v1",
            )
        )

    def uq_idempotency(db) -> None:
        ku, mem = _ensure_memory(db)
        key = _det_hex(32)
        db.add(_build_transition(mem.id, mem.memory_item_id, idempotency_key=key))
        db.flush()
        db.add(_build_transition(mem.id, mem.memory_item_id, idempotency_key=key))

    def fk_memory_row(db) -> None:
        db.add(
            _build_transition(
                999999102,
                "c" * 64,
                idempotency_key=_det_hex(32),
            )
        )

    def fk_from_ku(db) -> None:
        ku, mem = _ensure_memory(db)
        db.add(
            _build_transition(
                mem.id,
                mem.memory_item_id,
                from_knowledge_unit_id=999999103,
                idempotency_key=_det_hex(32),
            )
        )

    def fk_to_ku(db) -> None:
        ku, mem = _ensure_memory(db)
        db.add(
            _build_transition(
                mem.id,
                mem.memory_item_id,
                to_knowledge_unit_id=999999104,
                idempotency_key=_det_hex(32),
            )
        )

    def fk_kmi_ku_dup_path(db) -> None:
        # Distinct FK miss on knowledge_unit_id (second negative FK node).
        db.add(
            _build_memory(
                999999105,
                memory_item_id=_det_hex(32),
                domain="cardiology",
                topic="afib",
                knowledge_version="vx",
            )
        )

    cases.append(("uq_kmi_memory_item_id", uq_memory_item_id))
    cases.append(("uq_kmi_knowledge_unit_id", uq_knowledge_unit_id))
    cases.append(("fk_kmi_knowledge_unit_id", fk_kmi_ku))
    cases.append(("uq_kmt_idempotency_key", uq_idempotency))
    cases.append(("fk_kmt_memory_item_row_id", fk_memory_row))
    cases.append(("fk_kmt_from_knowledge_unit_id", fk_from_ku))
    cases.append(("fk_kmt_to_knowledge_unit_id", fk_to_ku))
    cases.append(("fk_kmi_knowledge_unit_id_alt", fk_kmi_ku_dup_path))
    return cases


_T8_CASES = _t8_cases()


@pytest.mark.parametrize(
    "constraint,factory",
    [
        (c if not c.endswith("_alt") else "fk_kmi_knowledge_unit_id", f)
        for c, f in _T8_CASES
    ],
    ids=[f"W2P01-T8-{c}" for c, _ in _T8_CASES],
)
def test_W2P01_T8_uq_fk_runtime_negative(db, constraint: str, factory) -> None:
    _require_postgres(db)
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: factory(db))


# ===========================================================================
# T9 — retraction / chain / resolve (runtime)
# ===========================================================================


def test_W2P01_T9_01_retraction_not_eligible(db) -> None:
    _require_postgres(db)
    _, enums, mem_svc, _ = _load_w2p01()
    ku = _ensure_ku(db, retraction_reason="withdrawn for safety review")
    _, mem = _ensure_memory(db, ku=ku)
    mem.supersession_state = enums.SupersessionState.RETRACTED.value
    mem.runtime_eligibility = "NOT_ELIGIBLE"
    ku.retraction_reason = "withdrawn for safety review"
    ku.publication_state = "WITHDRAWN"
    ku.runtime_eligibility = "NOT_ELIGIBLE"
    db.flush()
    elig = mem_svc.evaluate_memory_eligibility(mem)
    assert elig is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    assert mem.supersession_state == "RETRACTED"
    assert mem.runtime_eligibility == "NOT_ELIGIBLE"


@pytest.mark.parametrize(
    "case_id",
    [
        "self_parent",
        "cross_canonical",
        "resolve_superseded_by",
        "one_current_memory",
        "eligibility_fail_closed",
        "refuse_user_memory",
        "refuse_local_rag",
        "refuse_conversation",
        "project_and_idempotency",
    ],
    ids=[
        "W2P01-T9-self_parent",
        "W2P01-T9-cross_canonical",
        "W2P01-T9-resolve_superseded_by",
        "W2P01-T9-one_current_memory",
        "W2P01-T9-eligibility_fail_closed",
        "W2P01-T9-refuse_user_memory",
        "W2P01-T9-refuse_local_rag",
        "W2P01-T9-refuse_conversation",
        "W2P01-T9-project_and_idempotency",
    ],
)
def test_W2P01_T9_02_chain_resolve_and_guards(db, case_id: str) -> None:
    _require_postgres(db)
    models, enums, mem_svc, sup_svc = _load_w2p01()

    if case_id == "self_parent":
        ku = _ensure_ku(db)
        with pytest.raises(sup_svc.SupersessionServiceError):
            sup_svc.validate_supersession_link(ku, ku)
        return

    if case_id == "cross_canonical":
        old_ku = _ensure_ku(db, canonical_unit_id="canon-a-" + _det_hex(4))
        new_ku = _ensure_ku(db, canonical_unit_id="canon-b-" + _det_hex(4))
        with pytest.raises(sup_svc.SupersessionServiceError):
            sup_svc.validate_supersession_link(new_ku, old_ku)
        return

    if case_id == "resolve_superseded_by":
        old_ku = _ensure_ku(db)
        new_ku = _build_ku(
            canonical_unit_id=old_ku.canonical_unit_id,
            supersedes_unit_id=old_ku.id,
            immutable_version_id="v2-" + _det_hex(4),
            deduplication_key=_det_hex(32),
            canonical_hash=_det_hex(32),
        )
        db.add(new_ku)
        db.flush()
        by_supersedes: dict[int, list[int]] = {}
        for row in db.execute(
            text(
                "SELECT id, supersedes_unit_id FROM knowledge_units "
                "WHERE supersedes_unit_id IS NOT NULL"
            )
        ).fetchall():
            by_supersedes.setdefault(int(row[1]), []).append(int(row[0]))
        resolved = sup_svc.resolve_superseded_by(by_supersedes, old_ku.id)
        assert new_ku.id in resolved
        return

    if case_id == "one_current_memory":
        ku, mem = _ensure_memory(db)
        count = db.execute(
            text(
                "SELECT count(*) FROM knowledge_memory_items "
                "WHERE memory_item_id = :m AND supersession_state = 'CURRENT'"
            ),
            {"m": mem.memory_item_id},
        ).scalar()
        assert count == 1
        # Second row with same memory_item_id refused by UQ
        ku2 = _ensure_ku(db)
        _expect_named_integrity(
            db,
            constraint="uq_kmi_memory_item_id",
            mutate=lambda: db.add(
                _build_memory(
                    ku2.id,
                    memory_item_id=mem.memory_item_id,
                    knowledge_version="other",
                )
            ),
        )
        return

    if case_id == "eligibility_fail_closed":
        assert (
            mem_svc.evaluate_memory_eligibility(
                {"supersession_state": "CURRENT", "runtime_eligibility": "ELIGIBLE"}
            )
            is enums.KnowledgeUnitRuntimeEligibility.ELIGIBLE
        )
        assert (
            mem_svc.evaluate_memory_eligibility(
                {"supersession_state": "STALE", "runtime_eligibility": "ELIGIBLE"}
            )
            is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
        )
        return

    if case_id == "refuse_user_memory":
        with pytest.raises(mem_svc.KnowledgeMemoryServiceError):
            mem_svc.assert_not_user_memory_path("vault/user_memory/x")
        return

    if case_id == "refuse_local_rag":
        with pytest.raises(mem_svc.KnowledgeMemoryServiceError):
            mem_svc.assert_not_user_memory_path("C:\\tmp\\local_rag\\idx")
        return

    if case_id == "refuse_conversation":
        with pytest.raises(mem_svc.KnowledgeMemoryServiceError):
            mem_svc.assert_not_user_memory_path("/var/conversation/log")
        return

    if case_id == "project_and_idempotency":
        ku = _ensure_ku(db, topic_taxonomy="stroke")
        projected = mem_svc.project_from_knowledge_unit(
            {
                "id": ku.id,
                "domain": ku.domain,
                "topic_taxonomy": ku.topic_taxonomy,
                "canonical_unit_id": ku.canonical_unit_id,
                "immutable_version_id": ku.immutable_version_id,
                "runtime_eligibility": "NOT_ELIGIBLE",
                "supersession_state": "CURRENT",
            }
        )
        assert projected["memory_item_id"] == mem_svc.build_memory_item_id(
            ku.domain, ku.topic_taxonomy or "", ku.canonical_unit_id
        )
        key = sup_svc.build_idempotency_key(
            projected["memory_item_id"],
            ku.canonical_hash,
            enums.MemoryChangeKind.NO_MATERIAL_CHANGE,
        )
        assert len(key) == 64
        mem = models.KnowledgeMemoryItem(**projected)
        db.add(mem)
        db.flush()
        assert mem.id is not None
        return

    raise AssertionError(f"unknown case_id: {case_id}")
