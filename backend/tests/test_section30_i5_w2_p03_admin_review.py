"""Section 30 / W2-P03 — Admin review surfaces (P05) for KU / gap / safety / conflict.

Static helpers + PostgreSQL runtime nodes selected by
w2p03-postgresql-admin-review-runtime.yml.
"""
from __future__ import annotations

import importlib
import os
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import configure_mappers


def _load():
    models = importlib.import_module("backend.app.models")
    enums = importlib.import_module("backend.app.services.i5.enums")
    ars = importlib.import_module("backend.app.services.i5.admin_review_service")
    schemas = importlib.import_module("backend.app.schemas.i5_core")
    conflict = importlib.import_module("backend.app.services.i5.conflict_service")
    return models, enums, ars, schemas, conflict


def _pg_only(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _require_postgres(db) -> None:
    if not _pg_only(db):
        pytest.fail("PostgreSQL required for W2-P03 runtime node")


_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


def _build_gsp(**overrides):
    models, *_ = _load()
    base = dict(
        canonical_key="w2p03-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


def _build_ku(**overrides):
    models, *_ = _load()
    stmt = overrides.pop("normalized_statement", "W2-P03 demo normalized statement")
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
        medical_safety_state="PENDING_REVIEW",
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


def _build_safety_item(db, ku=None, **overrides):
    models, *_ = _load()
    if ku is None:
        ku = _ensure_ku(db)
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


def _build_conflict(db, **overrides):
    models, _, _, _, conflict_svc = _load()
    ku_a = _ensure_ku(db, topic_taxonomy="migraine", domain="neurology")
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
        conflict_state="CONFIRMED",
        conflict_summary="structured conflict",
        idempotency_key=idem,
    )
    base.update(overrides)
    row = models.KnowledgeConflict(**base)
    db.add(row)
    db.flush()
    return row, ku_a, ku_b


def _build_gap(db, **overrides):
    models, *_ = _load()
    base = dict(
        canonical_gap_key=_det_hex(32),
        domain="neurology",
        gap_type="MISSING",
        title="W2-P03 gap " + _det_hex(4),
        priority="P2",
        severity="MEDIUM",
        urgency="NORMAL",
        status="OPEN",
    )
    base.update(overrides)
    row = models.KnowledgeGap(**base)
    db.add(row)
    db.flush()
    return row


def _build_medical_safety_decision(db, gsp=None, **overrides):
    """Create a valid I5GovernanceDecision (SOURCE_PROFILE + MEDICAL_SAFETY)."""
    models, *_ = _load()
    if gsp is None:
        gsp = _build_gsp()
        db.add(gsp)
        db.flush()
    base = dict(
        entity_type="SOURCE_PROFILE",
        entity_id=gsp.id,
        decision_family="MEDICAL_SAFETY",
        decision_type="MEDICAL_SAFETY_REVIEW",
        decision_request_key="req-" + _det_hex(8),
        outcome="APPROVED",
        actor_type="HUMAN",
        actor_reference="w2p03-reviewer",
        canonical_hash=_det_hex(32),
        canonicalization_version="v1",
        hash_algorithm="SHA-256",
        reason="admin review close",
    )
    base.update(overrides)
    row = models.I5GovernanceDecision(**base)
    db.add(row)
    db.flush()
    return row, gsp


def _admin_app(db):
    from backend.app.database import get_db
    from backend.app.routers import i5_admin

    app = FastAPI()
    app.include_router(i5_admin.router)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    return app


# ---------------------------------------------------------------------------
# Runtime nodes
# ---------------------------------------------------------------------------


def test_W2P03_T1_package_identity_and_schemas(db) -> None:
    _require_postgres(db)
    _, enums, ars, schemas, _ = _load()
    identity = ars.package_identity()
    assert identity["package_id"] == "I5-IMPL-W2-P03"
    assert identity["management_alias"] == "P05"
    assert "Admin review" in identity["title"]
    assert schemas.PACKAGE_ID == "I5-IMPL-W2-P03"
    assert schemas.MANAGEMENT_ALIAS == "P05"
    assert set(enums.SafetyReviewQueueStatus) == {
        enums.SafetyReviewQueueStatus.OPEN,
        enums.SafetyReviewQueueStatus.IN_REVIEW,
        enums.SafetyReviewQueueStatus.CLOSED_CLEARED,
        enums.SafetyReviewQueueStatus.CLOSED_RESTRICTED,
        enums.SafetyReviewQueueStatus.CLOSED_BLOCKED,
        enums.SafetyReviewQueueStatus.CLOSED_REJECTED,
    }
    configure_mappers()
    models, *_ = _load()
    assert models.SafetyReviewQueueItem.__tablename__ == "knowledge_safety_reviews"
    assert models.KnowledgeConflict.__tablename__ == "knowledge_conflicts"
    assert models.KnowledgeGap.__tablename__ == "knowledge_gaps"


def test_W2P03_T2_queue_transition_matrix(db) -> None:
    _require_postgres(db)
    _, _, ars, _, _ = _load()
    pairs = set(ars.allowed_queue_transition_pairs())
    assert ("OPEN", "IN_REVIEW") in pairs
    assert ("IN_REVIEW", "CLOSED_CLEARED") in pairs
    assert ("OPEN", "CLOSED_CLEARED") not in pairs
    assert ("CLOSED_CLEARED", "OPEN") not in pairs
    with pytest.raises(ars.AdminReviewServiceError, match="ILLEGAL_QUEUE_TRANSITION"):
        ars.assert_allowed_queue_transition("OPEN", "CLOSED_CLEARED")
    assert ars.pending_review_blocks_eligibility("OPEN") is True
    assert ars.pending_review_blocks_eligibility("IN_REVIEW") is True
    assert ars.pending_review_blocks_eligibility("CLOSED_CLEARED") is False
    assert ars.closed_rejected_or_blocked("CLOSED_BLOCKED") is True


@pytest.mark.parametrize(
    "case_id",
    [
        "list_open",
        "filter_status",
        "filter_ku",
    ],
)
def test_W2P03_T3_list_and_filter_safety_queue(db, case_id: str) -> None:
    _require_postgres(db)
    _, _, ars, _, _ = _load()
    item_a, ku_a = _build_safety_item(db, queue_status="OPEN")
    item_b, _ = _build_safety_item(db, queue_status="IN_REVIEW")
    if case_id == "list_open":
        rows = ars.list_safety_reviews(db)
        assert {r.queue_item_id for r in rows} >= {item_a.queue_item_id, item_b.queue_item_id}
    elif case_id == "filter_status":
        rows = ars.list_safety_reviews(db, status="OPEN")
        assert all(r.queue_status == "OPEN" for r in rows)
        assert item_a.queue_item_id in {r.queue_item_id for r in rows}
        assert item_b.queue_item_id not in {r.queue_item_id for r in rows}
    else:
        rows = ars.list_safety_reviews(db, knowledge_unit_id=ku_a.id)
        assert all(r.knowledge_unit_id == ku_a.id for r in rows)
        assert item_a.queue_item_id in {r.queue_item_id for r in rows}


def test_W2P03_T4_start_and_close_with_decision(db) -> None:
    _require_postgres(db)
    models, _, ars, _, _ = _load()
    item, ku = _build_safety_item(db, medical_safety_state="PENDING_REVIEW")
    decision, _ = _build_medical_safety_decision(db)
    started = ars.start_safety_review(
        db, queue_item_id=item.queue_item_id, actor_reference="reviewer-a"
    )
    assert started.queue_status == "IN_REVIEW"
    closed = ars.close_safety_review(
        db,
        queue_item_id=item.queue_item_id,
        closed_status="CLOSED_CLEARED",
        decision_id=decision.id,
        reason="cleared after human review",
        actor_reference="reviewer-a",
    )
    assert closed.queue_status == "CLOSED_CLEARED"
    assert closed.decision_id == decision.id
    db.refresh(ku)
    assert ku.medical_safety_state == "CLEARED"


def test_W2P03_T5_fail_closed_close_without_decision(db) -> None:
    _require_postgres(db)
    _, _, ars, _, _ = _load()
    item, _ = _build_safety_item(db)
    ars.start_safety_review(
        db, queue_item_id=item.queue_item_id, actor_reference="reviewer-a"
    )
    with pytest.raises(ars.AdminReviewServiceError, match="DECISION"):
        ars.close_safety_review(
            db,
            queue_item_id=item.queue_item_id,
            closed_status="CLOSED_CLEARED",
            decision_id=None,  # type: ignore[arg-type]
            reason="missing decision",
            actor_reference="reviewer-a",
        )


@pytest.mark.parametrize(
    "case_id",
    [
        "open_to_closed",
        "closed_to_open",
        "in_review_to_open",
        "invalid_status",
    ],
)
def test_W2P03_T6_illegal_queue_transition(db, case_id: str) -> None:
    _require_postgres(db)
    _, _, ars, _, _ = _load()
    if case_id == "open_to_closed":
        item, _ = _build_safety_item(db, queue_status="OPEN")
        decision, _ = _build_medical_safety_decision(db)
        with pytest.raises(ars.AdminReviewServiceError, match="ILLEGAL_QUEUE_TRANSITION"):
            ars.close_safety_review(
                db,
                queue_item_id=item.queue_item_id,
                closed_status="CLOSED_CLEARED",
                decision_id=decision.id,
                reason="bypass",
                actor_reference="x",
            )
    elif case_id == "closed_to_open":
        with pytest.raises(ars.AdminReviewServiceError, match="ILLEGAL_QUEUE_TRANSITION"):
            ars.assert_allowed_queue_transition("CLOSED_CLEARED", "OPEN")
    elif case_id == "in_review_to_open":
        with pytest.raises(ars.AdminReviewServiceError, match="ILLEGAL_QUEUE_TRANSITION"):
            ars.assert_allowed_queue_transition("IN_REVIEW", "OPEN")
    else:
        with pytest.raises(ars.AdminReviewServiceError, match="QUEUE_STATUS_INVALID"):
            ars.assert_allowed_queue_transition("OPEN", "APPROVED")


def test_W2P03_T7_conflict_resolve_preserves_sides(db) -> None:
    _require_postgres(db)
    models, _, ars, _, _ = _load()
    conflict, ku_a, ku_b = _build_conflict(db)
    listed = ars.list_conflicts(db, conflict_state="CONFIRMED")
    assert conflict.conflict_key in {c.conflict_key for c in listed}
    resolved = ars.resolve_conflict_review(
        db,
        conflict_key=conflict.conflict_key,
        resolution_note="both claims retained; prefer guideline A",
        actor_reference="conflict-reviewer",
    )
    assert resolved.conflict_state == "RESOLVED"
    assert resolved.resolution_note is not None
    assert "guideline A" in resolved.resolution_note
    db.refresh(ku_a)
    db.refresh(ku_b)
    assert ku_a.id == conflict.knowledge_unit_id_a or ku_a.id == conflict.knowledge_unit_id_b
    assert ku_b.id == conflict.knowledge_unit_id_a or ku_b.id == conflict.knowledge_unit_id_b
    assert db.query(models.KnowledgeUnit).filter_by(id=ku_a.id).one()
    assert db.query(models.KnowledgeUnit).filter_by(id=ku_b.id).one()


def test_W2P03_T8_gap_list_and_triage(db) -> None:
    _require_postgres(db)
    _, _, ars, _, _ = _load()
    gap = _build_gap(db, priority="P1", status="OPEN")
    listed = ars.list_knowledge_gaps(db, status="OPEN", priority="P1")
    assert gap.id in {g.id for g in listed}
    triaged = ars.triage_knowledge_gap(
        db,
        gap_id=gap.id,
        new_status="TRIAGED",
        reviewer_reference="gap-reviewer",
        reason="accepted for planning",
    )
    assert triaged.status == "TRIAGED"
    assert triaged.id == gap.id
    with pytest.raises(ars.AdminReviewServiceError, match="ILLEGAL_GAP_TRIAGE"):
        ars.triage_knowledge_gap(
            db,
            gap_id=gap.id,
            new_status="RESOLVED",
            reviewer_reference="gap-reviewer",
        )


@pytest.mark.parametrize(
    "case_id",
    [
        "missing_token_env",
        "mismatch_token",
        "authorized_package",
    ],
)
def test_W2P03_T9_authz_admin_token(db, case_id: str) -> None:
    _require_postgres(db)
    app = _admin_app(db)
    prev = os.environ.get("ADMIN_TOKEN")
    try:
        if case_id == "missing_token_env":
            os.environ.pop("ADMIN_TOKEN", None)
            client = TestClient(app)
            resp = client.get("/i5/admin/package")
            assert resp.status_code == 404
        elif case_id == "mismatch_token":
            os.environ["ADMIN_TOKEN"] = "expected-secret"
            client = TestClient(app)
            resp = client.get(
                "/i5/admin/package", headers={"X-Admin-Token": "wrong"}
            )
            assert resp.status_code == 401
        else:
            os.environ["ADMIN_TOKEN"] = "expected-secret"
            client = TestClient(app)
            resp = client.get(
                "/i5/admin/package", headers={"X-Admin-Token": "expected-secret"}
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["package_id"] == "I5-IMPL-W2-P03"
            assert body["management_alias"] == "P05"
            assert body["crawler_activation"] is False
            assert body["source_activation"] is False
    finally:
        if prev is None:
            os.environ.pop("ADMIN_TOKEN", None)
        else:
            os.environ["ADMIN_TOKEN"] = prev


def test_W2P03_T10_idempotent_start(db) -> None:
    _require_postgres(db)
    _, _, ars, _, _ = _load()
    item, _ = _build_safety_item(db)
    first = ars.start_safety_review(
        db, queue_item_id=item.queue_item_id, actor_reference="r1"
    )
    second = ars.start_safety_review(
        db, queue_item_id=item.queue_item_id, actor_reference="r2"
    )
    assert first.queue_status == "IN_REVIEW"
    assert second.queue_status == "IN_REVIEW"


def test_W2P03_T11_decision_fk_and_close_blocked(db) -> None:
    _require_postgres(db)
    models, _, ars, _, _ = _load()
    item, ku = _build_safety_item(db, medical_safety_state="PENDING_REVIEW")
    ars.start_safety_review(
        db, queue_item_id=item.queue_item_id, actor_reference="r1"
    )
    with pytest.raises(ars.AdminReviewServiceError, match="DECISION_NOT_FOUND"):
        ars.close_safety_review(
            db,
            queue_item_id=item.queue_item_id,
            closed_status="CLOSED_BLOCKED",
            decision_id=9_999_999,
            reason="no such decision",
            actor_reference="r1",
        )
    decision, _ = _build_medical_safety_decision(db)
    closed = ars.close_safety_review(
        db,
        queue_item_id=item.queue_item_id,
        closed_status="CLOSED_BLOCKED",
        decision_id=decision.id,
        reason="blocked after review",
        actor_reference="r1",
    )
    assert closed.queue_status == "CLOSED_BLOCKED"
    db.refresh(ku)
    assert ku.medical_safety_state == "BLOCKED"
    assert ars.closed_rejected_or_blocked(closed.queue_status) is True


def test_W2P03_T12_api_list_safety_reviews(db) -> None:
    _require_postgres(db)
    item, _ = _build_safety_item(db)
    app = _admin_app(db)
    prev = os.environ.get("ADMIN_TOKEN")
    try:
        os.environ["ADMIN_TOKEN"] = "api-secret"
        client = TestClient(app)
        resp = client.get(
            "/i5/admin/safety-reviews",
            headers={"X-Admin-Token": "api-secret"},
            params={"status": "OPEN"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["package_id"] == "I5-IMPL-W2-P03"
        assert any(i["queue_item_id"] == item.queue_item_id for i in body["items"])
    finally:
        if prev is None:
            os.environ.pop("ADMIN_TOKEN", None)
        else:
            os.environ["ADMIN_TOKEN"] = prev
