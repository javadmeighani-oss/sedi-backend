"""Section 30 / W2-P02 — Evidence Strength / Freshness / Conflict / Medical-Safety.

Static T1–T4 are NOT in the PostgreSQL runtime selector manifest.
Runtime T5+ are selected by w2p02-postgresql-knowledge-safety-runtime.yml.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from typing import Any, Callable

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers


def _load_w2p02():
    models = importlib.import_module("backend.app.models")
    enums = importlib.import_module("backend.app.services.i5.enums")
    fresh = importlib.import_module("backend.app.services.i5.freshness_service")
    evidence = importlib.import_module("backend.app.services.i5.evidence_strength_service")
    conflict = importlib.import_module("backend.app.services.i5.conflict_service")
    safety = importlib.import_module("backend.app.services.i5.medical_safety_gate")
    elig = importlib.import_module("backend.app.services.i5.runtime_eligibility_gate")
    return models, enums, fresh, evidence, conflict, safety, elig


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


def _expect_named_integrity(
    db, *, constraint: str, mutate, accept_any_of: frozenset[str] | None = None
) -> None:
    _require_postgres(db)
    with pytest.raises(IntegrityError) as ei:
        with db.begin_nested():
            mutate()
            db.flush()
    blob = _constraint_blob(ei.value)
    allowed = accept_any_of if accept_any_of is not None else frozenset({constraint})
    assert constraint in allowed
    assert any(name in blob for name in allowed), (sorted(allowed), blob)


_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


EXPECTED_CHECK_NAMES: frozenset[str] = frozenset(
    {
        "ck_kc_conflict_state_vocab",
        "ck_kc_idempotency_key_format",
        "ck_kc_units_ordered",
        "uq_kc_idempotency_key",
        "uq_kc_conflict_key",
        "uq_kc_unit_pair",
        "fk_kc_ku_a",
        "fk_kc_ku_b",
        "ck_ksr_queue_status_vocab",
        "ck_ksr_medical_safety_state_vocab",
        "ck_ksr_idempotency_key_format",
        "uq_ksr_queue_item_id",
        "uq_ksr_idempotency_key",
        "fk_ksr_knowledge_unit_id",
        "fk_ksr_decision_id",
    }
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_gsp(**overrides):
    models, *_ = _load_w2p02()
    base = dict(
        canonical_key="w2p02-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


def _build_ku(**overrides):
    models, *_ = _load_w2p02()
    stmt = overrides.pop("normalized_statement", "W2-P02 demo normalized statement")
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


def _ensure_ku(db, **overrides):
    ku = _build_ku(**overrides)
    db.add(ku)
    db.flush()
    return ku


def _eligible_ku_kwargs(**overrides) -> dict[str, Any]:
    base = dict(
        provenance_complete=True,
        evidence_strength="HIGH",
        freshness_state="CURRENT",
        conflict_state="NONE",
        medical_safety_state="CLEARED",
        publication_state="PUBLISHED",
        retraction_reason=None,
        topic_taxonomy="migraine",
        domain="neurology",
    )
    base.update(overrides)
    return base


def _build_conflict(db, ku_a=None, ku_b=None, **overrides):
    models, _, _, _, conflict_svc, _, _ = _load_w2p02()
    if ku_a is None:
        ku_a = _ensure_ku(db, topic_taxonomy="migraine", domain="neurology")
    if ku_b is None:
        ku_b = _ensure_ku(
            db,
            topic_taxonomy="migraine",
            domain="neurology",
            normalized_statement="alternate conflicting statement " + _det_hex(2),
        )
    a_id, b_id = conflict_svc.order_unit_ids(ku_a.id, ku_b.id)
    summary_hash = overrides.pop("summary_hash", None) or _det_hex(32)
    idem = overrides.pop("idempotency_key", None) or conflict_svc.build_conflict_idempotency_key(
        a_id, b_id, summary_hash
    )
    ckey = overrides.pop("conflict_key", None) or conflict_svc.build_conflict_key(a_id, b_id)
    base = dict(
        conflict_key=ckey,
        knowledge_unit_id_a=a_id,
        knowledge_unit_id_b=b_id,
        conflict_state="SUSPECTED",
        conflict_summary="structured conflict",
        idempotency_key=idem,
    )
    base.update(overrides)
    row = models.KnowledgeConflict(**base)
    db.add(row)
    db.flush()
    return row, ku_a, ku_b


def _build_safety_item(db, ku=None, **overrides):
    models, *_ = _load_w2p02()
    if ku is None:
        ku = _ensure_ku(db, medical_safety_state="PENDING_REVIEW")
    base = dict(
        queue_item_id="ksr-" + _det_hex(8),
        knowledge_unit_id=ku.id,
        queue_status="OPEN",
        medical_safety_state=overrides.pop("medical_safety_state", ku.medical_safety_state),
        high_risk_domain=overrides.pop("high_risk_domain", False),
        reason=overrides.pop("reason", "human review required"),
        idempotency_key=overrides.pop("idempotency_key", None) or _det_hex(32),
    )
    base.update(overrides)
    row = models.SafetyReviewQueueItem(**base)
    db.add(row)
    db.flush()
    return row, ku


def _ku_mapping(**overrides) -> dict[str, Any]:
    base = _eligible_ku_kwargs()
    base.update(overrides)
    return base


# ===========================================================================
# T1 — enums (static)
# ===========================================================================


def test_W2P02_T1_enum_imports_and_literals() -> None:
    from enum import Enum

    _, enums, *_ = _load_w2p02()
    assert issubclass(enums.SafetyReviewQueueStatus, Enum)
    for member in enums.SafetyReviewQueueStatus:
        assert member.value == member.name
    assert enums.EvidenceStrength.CONFLICTED.value == "CONFLICTED"
    assert enums.FreshnessState.STALE.value == "STALE"
    assert enums.ConflictState.RESOLVED.value == "RESOLVED"
    assert enums.MedicalSafetyState.CLEARED.value == "CLEARED"


# ===========================================================================
# T2 — configure_mappers / zero relationships (static)
# ===========================================================================


def test_W2P02_T2_models_configure_and_zero_relationships() -> None:
    models, *_ = _load_w2p02()
    configure_mappers()
    for name in ("KnowledgeConflict", "SafetyReviewQueueItem", "KnowledgeUnit"):
        assert hasattr(models, name), name
        mapper = sa_inspect(getattr(models, name))
        assert len(list(mapper.relationships)) == 0, name


# ===========================================================================
# T3 — metadata ledgers (static)
# ===========================================================================


def test_W2P02_T3_metadata_constraint_ledgers() -> None:
    models, *_ = _load_w2p02()
    names: set[str] = set()
    for table in (
        models.KnowledgeConflict.__table__,
        models.SafetyReviewQueueItem.__table__,
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


def test_W2P02_T4_service_pure_functions() -> None:
    _, enums, fresh, evidence, conflict, safety, elig = _load_w2p02()
    now = datetime(2026, 8, 6, 12, 0, 0)
    assert (
        fresh.calculate_freshness_state(now=now)
        is enums.FreshnessState.UNKNOWN
    )
    assert (
        fresh.calculate_freshness_state(
            now=now, reviewed_at=now - timedelta(days=1)
        )
        is enums.FreshnessState.CURRENT
    )
    assert evidence.classify_evidence_strength(
        source_authority_tier="AUTHORITATIVE",
        has_guideline=True,
        has_conflict=False,
        assessed=True,
    ) is enums.EvidenceStrength.HIGH
    assert conflict.order_unit_ids(9, 3) == (3, 9)
    left = {
        "domain": "neurology",
        "topic_taxonomy": "migraine",
        "normalized_statement": "a",
        "applicability": None,
        "exclusions": None,
        "medical_safety_state": "CLEARED",
        "evidence_strength": "HIGH",
        "provenance_complete": True,
    }
    right = dict(left, normalized_statement="b")
    assert conflict.detect_structured_conflict(left, right) is enums.ConflictState.CONFIRMED
    with pytest.raises(conflict.ConflictServiceError):
        conflict.assert_allowed_conflict_transition("RESOLVED", "SUSPECTED")
    with pytest.raises(safety.MedicalSafetyGateError):
        safety.assert_allowed_medical_safety_transition("BLOCKED", "CLEARED")
    assert safety.requires_human_review("neurology", "UNKNOWN", "NONE", False) is True
    assert (
        elig.evaluate_knowledge_unit_eligibility(_ku_mapping())
        is enums.KnowledgeUnitRuntimeEligibility.ELIGIBLE
    )


# ===========================================================================
# T5 — metadata / catalog (runtime)
# ===========================================================================


def test_W2P02_T5_01_metadata_contains_safety_tables(db) -> None:
    _require_postgres(db)
    models, *_ = _load_w2p02()
    tables = set(models.Base.metadata.tables.keys())
    for name in ("knowledge_conflicts", "knowledge_safety_reviews", "knowledge_units"):
        assert name in tables
    inspector = sa_inspect(db.get_bind())
    present = set(inspector.get_table_names())
    for name in ("knowledge_conflicts", "knowledge_safety_reviews", "knowledge_units"):
        assert name in present


def test_W2P02_T5_02_named_checks_present_in_pg_catalog(db) -> None:
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
                'knowledge_conflicts', 'knowledge_safety_reviews', 'knowledge_units'
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


def test_W2P02_T6_01_create_conflict(db) -> None:
    _require_postgres(db)
    _, enums, _, _, conflict_svc, _, _ = _load_w2p02()
    row, ku_a, ku_b = _build_conflict(db)
    assert row.id is not None
    assert row.knowledge_unit_id_a < row.knowledge_unit_id_b
    assert row.conflict_state == enums.ConflictState.SUSPECTED.value
    detected = conflict_svc.detect_structured_conflict(
        {
            "domain": ku_a.domain,
            "topic_taxonomy": ku_a.topic_taxonomy,
            "normalized_statement": ku_a.normalized_statement,
            "applicability": ku_a.applicability,
            "exclusions": ku_a.exclusions,
            "medical_safety_state": ku_a.medical_safety_state,
            "evidence_strength": ku_a.evidence_strength,
            "provenance_complete": True,
        },
        {
            "domain": ku_b.domain,
            "topic_taxonomy": ku_b.topic_taxonomy,
            "normalized_statement": ku_b.normalized_statement,
            "applicability": ku_b.applicability,
            "exclusions": ku_b.exclusions,
            "medical_safety_state": ku_b.medical_safety_state,
            "evidence_strength": ku_b.evidence_strength,
            "provenance_complete": True,
        },
    )
    assert detected in (
        enums.ConflictState.SUSPECTED,
        enums.ConflictState.CONFIRMED,
    )


def test_W2P02_T6_02_resolve_conflict(db) -> None:
    _require_postgres(db)
    _, enums, _, _, conflict_svc, _, _ = _load_w2p02()
    row, _, _ = _build_conflict(db, conflict_state="SUSPECTED")
    conflict_svc.assert_allowed_conflict_transition(row.conflict_state, "CONFIRMED")
    row.conflict_state = enums.ConflictState.CONFIRMED.value
    db.flush()
    conflict_svc.assert_allowed_conflict_transition(row.conflict_state, "RESOLVED")
    row.conflict_state = enums.ConflictState.RESOLVED.value
    row.resolution_note = "reviewed and reconciled"
    db.flush()
    assert row.conflict_state == "RESOLVED"


def test_W2P02_T6_03_enqueue_safety_review(db) -> None:
    _require_postgres(db)
    _, enums, _, _, _, safety, _ = _load_w2p02()
    ku = _ensure_ku(
        db,
        domain="pregnancy_care",
        medical_safety_state="PENDING_REVIEW",
        conflict_state="NONE",
    )
    assert safety.should_enqueue_safety_review(
        ku.domain, ku.medical_safety_state, ku.conflict_state, True
    )
    row, _ = _build_safety_item(
        db,
        ku=ku,
        high_risk_domain=True,
        medical_safety_state="PENDING_REVIEW",
    )
    assert row.queue_status == enums.SafetyReviewQueueStatus.OPEN.value
    assert row.high_risk_domain is True


def test_W2P02_T6_04_freshness_current(db) -> None:
    _require_postgres(db)
    _, enums, fresh, *_ = _load_w2p02()
    now = datetime(2026, 8, 6, 12, 0, 0)
    state = fresh.calculate_freshness_state(
        now=now,
        updated_at=now - timedelta(days=2),
        policy_days=30,
    )
    assert state is enums.FreshnessState.CURRENT
    ku = _ensure_ku(db, freshness_state=state.value)
    assert ku.freshness_state == "CURRENT"


def test_W2P02_T6_05_eligibility_eligible_path(db) -> None:
    _require_postgres(db)
    _, enums, _, _, _, _, elig = _load_w2p02()
    ku = _ensure_ku(db, **_eligible_ku_kwargs())
    result = elig.evaluate_knowledge_unit_eligibility(ku)
    assert result is enums.KnowledgeUnitRuntimeEligibility.ELIGIBLE


# ===========================================================================
# T7 — negative CHECKs (runtime, parametrized)
# ===========================================================================


def _conflict_vocab_bad(db) -> None:
    models, *_ = _load_w2p02()
    ku_a = _ensure_ku(db)
    ku_b = _ensure_ku(db)
    a_id, b_id = (ku_a.id, ku_b.id) if ku_a.id < ku_b.id else (ku_b.id, ku_a.id)
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=a_id,
            knowledge_unit_id_b=b_id,
            conflict_state="WAR",
            idempotency_key=_det_hex(32),
        )
    )


def _conflict_idem_bad(db) -> None:
    models, *_ = _load_w2p02()
    ku_a = _ensure_ku(db)
    ku_b = _ensure_ku(db)
    a_id, b_id = (ku_a.id, ku_b.id) if ku_a.id < ku_b.id else (ku_b.id, ku_a.id)
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=a_id,
            knowledge_unit_id_b=b_id,
            conflict_state="SUSPECTED",
            idempotency_key="not-a-hex-digest",
        )
    )


def _conflict_units_reversed(db) -> None:
    models, *_ = _load_w2p02()
    ku_a = _ensure_ku(db)
    ku_b = _ensure_ku(db)
    lo, hi = (ku_a.id, ku_b.id) if ku_a.id < ku_b.id else (ku_b.id, ku_a.id)
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=hi,
            knowledge_unit_id_b=lo,
            conflict_state="SUSPECTED",
            idempotency_key=_det_hex(32),
        )
    )


def _conflict_units_equal(db) -> None:
    models, *_ = _load_w2p02()
    ku = _ensure_ku(db)
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=ku.id,
            knowledge_unit_id_b=ku.id,
            conflict_state="SUSPECTED",
            idempotency_key=_det_hex(32),
        )
    )


def _safety_queue_vocab_bad(db) -> None:
    models, *_ = _load_w2p02()
    ku = _ensure_ku(db)
    db.add(
        models.SafetyReviewQueueItem(
            queue_item_id="ksr-" + _det_hex(4),
            knowledge_unit_id=ku.id,
            queue_status="DONE",
            medical_safety_state="PENDING_REVIEW",
            idempotency_key=_det_hex(32),
        )
    )


def _safety_medical_vocab_bad(db) -> None:
    models, *_ = _load_w2p02()
    ku = _ensure_ku(db)
    db.add(
        models.SafetyReviewQueueItem(
            queue_item_id="ksr-" + _det_hex(4),
            knowledge_unit_id=ku.id,
            queue_status="OPEN",
            medical_safety_state="UNSAFE",
            idempotency_key=_det_hex(32),
        )
    )


def _safety_idem_bad(db) -> None:
    models, *_ = _load_w2p02()
    ku = _ensure_ku(db)
    db.add(
        models.SafetyReviewQueueItem(
            queue_item_id="ksr-" + _det_hex(4),
            knowledge_unit_id=ku.id,
            queue_status="OPEN",
            medical_safety_state="PENDING_REVIEW",
            idempotency_key="ZZ",
        )
    )


def _conflict_vocab_update(db) -> None:
    row, _, _ = _build_conflict(db)
    row.conflict_state = "WAR"


def _safety_queue_update(db) -> None:
    row, _ = _build_safety_item(db)
    row.queue_status = "DONE"


def _safety_medical_update(db) -> None:
    row, _ = _build_safety_item(db)
    row.medical_safety_state = "UNSAFE"


def _conflict_idem_update(db) -> None:
    row, _, _ = _build_conflict(db)
    row.idempotency_key = "bad"


def _safety_idem_update(db) -> None:
    row, _ = _build_safety_item(db)
    row.idempotency_key = "bad"


def _t7_cases() -> list[tuple[str, str, Callable]]:
    return [
        ("ck_kc_conflict_state_vocab", "ck_kc_conflict_state_vocab", _conflict_vocab_bad),
        ("ck_kc_idempotency_key_format", "ck_kc_idempotency_key_format", _conflict_idem_bad),
        ("ck_kc_units_ordered", "ck_kc_units_ordered", _conflict_units_reversed),
        ("ck_kc_units_ordered_equal", "ck_kc_units_ordered", _conflict_units_equal),
        ("ck_ksr_queue_status_vocab", "ck_ksr_queue_status_vocab", _safety_queue_vocab_bad),
        (
            "ck_ksr_medical_safety_state_vocab",
            "ck_ksr_medical_safety_state_vocab",
            _safety_medical_vocab_bad,
        ),
        ("ck_ksr_idempotency_key_format", "ck_ksr_idempotency_key_format", _safety_idem_bad),
        (
            "ck_kc_conflict_state_vocab_update",
            "ck_kc_conflict_state_vocab",
            _conflict_vocab_update,
        ),
        (
            "ck_ksr_queue_status_vocab_update",
            "ck_ksr_queue_status_vocab",
            _safety_queue_update,
        ),
        (
            "ck_ksr_medical_safety_state_vocab_update",
            "ck_ksr_medical_safety_state_vocab",
            _safety_medical_update,
        ),
        (
            "ck_kc_idempotency_key_format_update",
            "ck_kc_idempotency_key_format",
            _conflict_idem_update,
        ),
        (
            "ck_ksr_idempotency_key_format_update",
            "ck_ksr_idempotency_key_format",
            _safety_idem_update,
        ),
    ]


@pytest.mark.parametrize(
    "constraint, factory",
    [(c, f) for _, c, f in _t7_cases()],
    ids=[f"W2P02-T7-{p}" for p, _, _ in _t7_cases()],
)
def test_W2P02_T7_negative_check_constraints(db, constraint: str, factory) -> None:
    _expect_named_integrity(db, constraint=constraint, mutate=lambda: factory(db))


# ===========================================================================
# T8 — UQ / FK negatives (runtime, parametrized)
# ===========================================================================


def _t8_uq_kc_idem(db) -> None:
    row, _, _ = _build_conflict(db)
    models, *_ = _load_w2p02()
    ku_c = _ensure_ku(db)
    ku_d = _ensure_ku(db)
    a_id, b_id = (ku_c.id, ku_d.id) if ku_c.id < ku_d.id else (ku_d.id, ku_c.id)
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=a_id,
            knowledge_unit_id_b=b_id,
            conflict_state="SUSPECTED",
            idempotency_key=row.idempotency_key,
        )
    )


def _t8_uq_kc_pair(db) -> None:
    row, ku_a, ku_b = _build_conflict(db)
    models, *_ = _load_w2p02()
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=row.knowledge_unit_id_a,
            knowledge_unit_id_b=row.knowledge_unit_id_b,
            conflict_state="SUSPECTED",
            idempotency_key=_det_hex(32),
        )
    )
    _ = (ku_a, ku_b)


def _t8_uq_kc_key(db) -> None:
    row, _, _ = _build_conflict(db)
    models, *_ = _load_w2p02()
    ku_c = _ensure_ku(db)
    ku_d = _ensure_ku(db)
    a_id, b_id = (ku_c.id, ku_d.id) if ku_c.id < ku_d.id else (ku_d.id, ku_c.id)
    db.add(
        models.KnowledgeConflict(
            conflict_key=row.conflict_key,
            knowledge_unit_id_a=a_id,
            knowledge_unit_id_b=b_id,
            conflict_state="SUSPECTED",
            idempotency_key=_det_hex(32),
        )
    )


def _t8_fk_kc_a(db) -> None:
    models, *_ = _load_w2p02()
    # Ordered orphan pair (a < b); first missing parent is ku_a.
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=8_888_801,
            knowledge_unit_id_b=8_888_802,
            conflict_state="SUSPECTED",
            idempotency_key=_det_hex(32),
        )
    )


def _t8_fk_kc_b(db) -> None:
    models, *_ = _load_w2p02()
    ku = _ensure_ku(db)
    orphan_b = ku.id + 50_000
    db.add(
        models.KnowledgeConflict(
            conflict_key=_det_hex(32),
            knowledge_unit_id_a=ku.id,
            knowledge_unit_id_b=orphan_b,
            conflict_state="SUSPECTED",
            idempotency_key=_det_hex(32),
        )
    )


def _t8_uq_ksr_qid(db) -> None:
    row, _ = _build_safety_item(db)
    models, *_ = _load_w2p02()
    ku2 = _ensure_ku(db)
    db.add(
        models.SafetyReviewQueueItem(
            queue_item_id=row.queue_item_id,
            knowledge_unit_id=ku2.id,
            queue_status="OPEN",
            medical_safety_state="PENDING_REVIEW",
            idempotency_key=_det_hex(32),
        )
    )


def _t8_uq_ksr_idem(db) -> None:
    row, _ = _build_safety_item(db)
    models, *_ = _load_w2p02()
    ku2 = _ensure_ku(db)
    db.add(
        models.SafetyReviewQueueItem(
            queue_item_id="ksr-" + _det_hex(4),
            knowledge_unit_id=ku2.id,
            queue_status="OPEN",
            medical_safety_state="PENDING_REVIEW",
            idempotency_key=row.idempotency_key,
        )
    )


def _t8_fk_ksr_ku(db) -> None:
    models, *_ = _load_w2p02()
    db.add(
        models.SafetyReviewQueueItem(
            queue_item_id="ksr-" + _det_hex(4),
            knowledge_unit_id=9_999_999,
            queue_status="OPEN",
            medical_safety_state="PENDING_REVIEW",
            idempotency_key=_det_hex(32),
        )
    )


def _t8_cases() -> list[tuple[str, str, Callable]]:
    return [
        ("uq_kc_idempotency_key", "uq_kc_idempotency_key", _t8_uq_kc_idem),
        ("uq_kc_unit_pair", "uq_kc_unit_pair", _t8_uq_kc_pair),
        ("uq_kc_conflict_key", "uq_kc_conflict_key", _t8_uq_kc_key),
        ("fk_kc_ku_a", "fk_kc_ku_a", _t8_fk_kc_a),
        ("fk_kc_ku_b", "fk_kc_ku_b", _t8_fk_kc_b),
        ("uq_ksr_queue_item_id", "uq_ksr_queue_item_id", _t8_uq_ksr_qid),
        ("uq_ksr_idempotency_key", "uq_ksr_idempotency_key", _t8_uq_ksr_idem),
        ("fk_ksr_knowledge_unit_id", "fk_ksr_knowledge_unit_id", _t8_fk_ksr_ku),
    ]


@pytest.mark.parametrize(
    "constraint, factory",
    [(c, f) for _, c, f in _t8_cases()],
    ids=[f"W2P02-T8-{p}" for p, _, _ in _t8_cases()],
)
def test_W2P02_T8_uq_fk_runtime_negative(db, constraint: str, factory) -> None:
    accept = None
    if constraint == "fk_kc_ku_a":
        # Both parents missing: engine may surface either FK name first.
        accept = frozenset({"fk_kc_ku_a", "fk_kc_ku_b"})
    _expect_named_integrity(
        db, constraint=constraint, mutate=lambda: factory(db), accept_any_of=accept
    )


# ===========================================================================
# T9 — fail-closed matrix / guards (runtime, parametrized)
# ===========================================================================


def _t9_freshness_unknown(db) -> None:
    _, enums, fresh, *_ = _load_w2p02()
    now = datetime(2026, 8, 6, 12, 0, 0)
    assert fresh.calculate_freshness_state(now=now) is enums.FreshnessState.UNKNOWN
    assert (
        fresh.calculate_freshness_state(now=now, published_at=now - timedelta(days=1))
        is enums.FreshnessState.UNKNOWN
    )


def _t9_freshness_stale(db) -> None:
    _, enums, fresh, *_ = _load_w2p02()
    now = datetime(2026, 8, 6, 12, 0, 0)
    assert (
        fresh.calculate_freshness_state(
            now=now, updated_at=now - timedelta(days=40), policy_days=30
        )
        is enums.FreshnessState.STALE
    )


def _t9_freshness_expired_valid_until(db) -> None:
    _, enums, fresh, *_ = _load_w2p02()
    now = datetime(2026, 8, 6, 12, 0, 0)
    assert (
        fresh.calculate_freshness_state(
            now=now,
            updated_at=now - timedelta(days=1),
            valid_until=now - timedelta(hours=1),
        )
        is enums.FreshnessState.EXPIRED
    )


def _t9_freshness_expired_policy(db) -> None:
    _, enums, fresh, *_ = _load_w2p02()
    now = datetime(2026, 8, 6, 12, 0, 0)
    assert (
        fresh.calculate_freshness_state(
            now=now, updated_at=now - timedelta(days=70), policy_days=30
        )
        is enums.FreshnessState.EXPIRED
    )


def _t9_conflict_blocks(db) -> None:
    _, enums, _, _, _, _, elig = _load_w2p02()
    result = elig.evaluate_knowledge_unit_eligibility(
        _ku_mapping(conflict_state="SUSPECTED")
    )
    assert result is enums.KnowledgeUnitRuntimeEligibility.REVIEW_REQUIRED


def _t9_blocked_safety(db) -> None:
    _, enums, _, _, _, _, elig = _load_w2p02()
    result = elig.evaluate_knowledge_unit_eligibility(
        _ku_mapping(medical_safety_state="BLOCKED")
    )
    assert result is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE


def _t9_retraction(db) -> None:
    _, enums, _, _, _, _, elig = _load_w2p02()
    result = elig.evaluate_knowledge_unit_eligibility(
        _ku_mapping(retraction_reason="source retracted")
    )
    assert result is enums.KnowledgeUnitRuntimeEligibility.REVOKED


def _t9_illegal_conflict(db) -> None:
    _, _, _, _, conflict, _, _ = _load_w2p02()
    with pytest.raises(conflict.ConflictServiceError):
        conflict.assert_allowed_conflict_transition("RESOLVED", "SUSPECTED")


def _t9_illegal_medical(db) -> None:
    _, _, _, _, _, safety, _ = _load_w2p02()
    with pytest.raises(safety.MedicalSafetyGateError):
        safety.assert_allowed_medical_safety_transition("BLOCKED", "CLEARED")


def _t9_high_risk(db) -> None:
    _, _, _, _, _, safety, _ = _load_w2p02()
    assert safety.requires_human_review("diabetes_type2", "UNKNOWN", "NONE", False)
    assert safety.should_enqueue_safety_review("diabetes_type2", "UNKNOWN", "NONE", False)
    assert not safety.should_enqueue_safety_review(
        "diabetes_type2", "CLEARED", "NONE", True
    )


def _t9_idempotent_conflict(db) -> None:
    row, _, _ = _build_conflict(db)
    models, *_ = _load_w2p02()
    ku_c = _ensure_ku(db)
    ku_d = _ensure_ku(db)
    a_id, b_id = (ku_c.id, ku_d.id) if ku_c.id < ku_d.id else (ku_d.id, ku_c.id)
    _expect_named_integrity(
        db,
        constraint="uq_kc_idempotency_key",
        mutate=lambda: db.add(
            models.KnowledgeConflict(
                conflict_key=_det_hex(32),
                knowledge_unit_id_a=a_id,
                knowledge_unit_id_b=b_id,
                conflict_state="SUSPECTED",
                idempotency_key=row.idempotency_key,
            )
        ),
    )


def _t9_matrix_eligible(db) -> None:
    _, enums, _, evidence, _, _, elig = _load_w2p02()
    assert evidence.validate_evidence_strength("MODERATE") is enums.EvidenceStrength.MODERATE
    assert (
        elig.evaluate_knowledge_unit_eligibility(_ku_mapping(evidence_strength="MODERATE"))
        is enums.KnowledgeUnitRuntimeEligibility.ELIGIBLE
    )


def _t9_matrix_withdrawn(db) -> None:
    _, enums, _, _, _, _, elig = _load_w2p02()
    result = elig.evaluate_knowledge_unit_eligibility(
        _ku_mapping(publication_state="WITHDRAWN")
    )
    assert result is enums.KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE


def _t9_cases() -> list[tuple[str, Callable]]:
    return [
        ("freshness_unknown", _t9_freshness_unknown),
        ("freshness_stale", _t9_freshness_stale),
        ("freshness_expired_valid_until", _t9_freshness_expired_valid_until),
        ("freshness_expired_policy", _t9_freshness_expired_policy),
        ("conflict_blocks_eligibility", _t9_conflict_blocks),
        ("blocked_safety", _t9_blocked_safety),
        ("retraction_revoked", _t9_retraction),
        ("illegal_conflict_transition", _t9_illegal_conflict),
        ("illegal_medical_safety_transition", _t9_illegal_medical),
        ("high_risk_human", _t9_high_risk),
        ("idempotent_conflict", _t9_idempotent_conflict),
        ("matrix_eligible", _t9_matrix_eligible),
        ("matrix_withdrawn", _t9_matrix_withdrawn),
    ]


@pytest.mark.parametrize(
    "case_id",
    [p for p, _ in _t9_cases()],
    ids=[f"W2P02-T9-{p}" for p, _ in _t9_cases()],
)
def test_W2P02_T9_fail_closed_matrix_and_guards(db, case_id: str) -> None:
    _require_postgres(db)
    mapping = {p: fn for p, fn in _t9_cases()}
    mapping[case_id](db)
