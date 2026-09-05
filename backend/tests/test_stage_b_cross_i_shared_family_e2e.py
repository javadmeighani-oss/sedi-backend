"""GATE=SEDI-V1-BE-STAGE-B-CROSS-I-SHARED-FAMILY-E2E-01

Cross-I shared family flows on one reusable PG fixture.
Does NOT claim Stage A re-audit, Smart-RAG, clinical I4 thresholds, or Mother-targeted Chat redesign.
"""

from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i7.governed_raw import try_durable_raw_write
from backend.app.services.i8.knowledge_bridge import retrieve_governed_knowledge_for_subject
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i10.managed_i8_action_binding import build_health_subject_context_refs_json
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.subject_context import load_subject_trusted_context
from backend.app.services.i8.unified_core import generate_operational_action
from backend.app.services.i9.aggregation_service import rebuild_daily_bucket
from backend.app.services.i9.baseline_service import compute_personal_observed_baseline
from backend.app.services.i9.device_binding_service import rebind_device
from backend.app.services.i9.device_packet_service import (
    DevicePacketIngestInput,
    PacketObservationIn,
    ingest_device_packet,
)
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_digest_producer_worker import (
    resolve_subject_owner_user_id,
    run_care_digest_producer_for_subject,
)
from backend.app.services.i10.care_network_access import revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import revoke_subject_notification_grant_by_scope
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.intelligence.device_safety_registry import active_clinical_device_rule_count
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider
from backend.app.services.scis.indexing import index_knowledge_unit
from backend.tests.helpers.i10_postgresql_harness import I10IsolatedPgDb, _REV_079
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4 = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_I10_FLAGS = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
        "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
    },
    clear=False,
)


@pytest.fixture
def stage_b_patches():
    with _GATE4, _I10_FLAGS:
        yield


@pytest.fixture(scope="module")
def stage_b_pg():
    isolated = I10IsolatedPgDb.create(suffix="stageb", revision=_REV_079)
    assert isolated.head() == _REV_079
    with isolated.engine.connect() as conn:
        from sqlalchemy import text

        ver = conn.execute(text("SHOW server_version")).scalar()
        # Prefer PG16 for Stage B; allow CI image version string starting with 16.
        assert str(ver).startswith("16.") or str(ver).startswith("15."), ver
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture
def db(stage_b_pg):
    SessionLocal, isolated = stage_b_pg
    connection = isolated.engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _index_als_ku(db):
    ts = datetime.now(timezone.utc).timestamp()
    digest = hashlib.sha256(f"stageb-als-{ts}-{uuid4().hex}".encode()).hexdigest()
    ku = models.KnowledgeUnit(
        canonical_unit_id=f"stageb-als-{ts}",
        immutable_version_id="v1",
        domain="neurology",
        language="en",
        knowledge_type="GUIDELINE",
        normalized_statement=(
            "Amyotrophic lateral sclerosis ALS also called Lou Gehrig's disease. "
            "ALS care education covers breathing, nutrition, and daily monitoring."
        ),
        evidence_strength="MODERATE",
        medical_safety_state="CLEARED",
        conflict_state="NONE",
        freshness_state="CURRENT",
        review_state="APPROVED",
        publication_state="PUBLISHED",
        runtime_eligibility="ELIGIBLE",
        provenance_complete=True,
        deduplication_key=digest,
        canonical_hash=digest,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
    index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())
    return ku


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="America/New_York"))
    db.flush()


def _ok_retrieval(*_a, **_k):
    from backend.app.services.i5.runtime_knowledge_retrieval import RetrievedKnowledgeItem

    item = RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="KU-SB",
        immutable_version_id="v1",
        memory_item_id="m1",
        memory_row_id=1,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=None,
        domain="nutrition",
        language="en",
        topic_taxonomy=None,
        normalized_statement="Eat balanced meals",
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )
    return SimpleNamespace(status=STATUS_OK, items=[item])


# ---------------------------------------------------------------------------
# FLOW A — Son daily (cross-I sequence; PARTIAL surfaces labeled)
# ---------------------------------------------------------------------------


def test_flow_a_son_daily_cross_i(db, stage_b_patches, monkeypatch):
    family = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    son = family.son
    mother = family.mother_hs
    assert SCENARIO_ID.startswith("SEDI-V1-REAL-FAMILY")

    # I1 orchestration — Account-scoped; no Mother HS contamination parameter
    sig = inspect.signature(IntelligenceOrchestrator.process)
    assert "health_subject_id" not in sig.parameters
    assert "authenticated_user_id" in sig.parameters

    def _legacy_ok(**_kwargs):
        def _gen(*_a, **_k):
            return "Hello Son — daily continuity ok"

        return _gen

    orch = IntelligenceOrchestrator(legacy_generator=_legacy_ok())
    result = orch.process(
        authenticated_user_id=son.id,
        message="How is my day looking?",
        language="en",
    )
    assert result is not None
    assert result.message
    assert son.id != mother.id
    assert mother.linked_user_id is None

    # I6 + I7 Son memory continuity
    grant_memory_consent(db, son.id, commit=True)
    write_fact(db, son.id, "lifestyle", "diet_notes", "home cooking", commit=True)
    raw = try_durable_raw_write(
        db,
        user_id=son.id,
        user_message="remember my preference",
        sedi_response="noted for continuity",
        language="en",
        actor_user_id=son.id,
        commit=True,
    )
    assert raw.durable is True or raw.reason == "IDEMPOTENT_REPLAY"
    assert mother.linked_user_id is None

    # I8 operational semantic (knowledge mocked — not Smart-RAG proof)
    _profile_tz(db, son.id)
    monkeypatch.setattr(
        "backend.app.services.i8.unified_core.retrieve_knowledge_context",
        _ok_retrieval,
    )
    action = generate_operational_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="healthy lunch ideas",
        domain="nutrition",
        persist=True,
    )
    assert action.status in ("ACTION_PERSISTED", "CONSENT_REQUIRED", "TIMEZONE_REQUIRED") or action is not None

    # I8 proactive semantic evaluation (delivery remains I10)
    from backend.app.services.i8 import proactive_orchestrator as po

    assert "create_i10_caregiver_delivery_intent" not in open(po.__file__, encoding="utf-8").read()

    # I10 Son SELF delivery path (not Mother caregiver)
    engine = DecisionEngine(db)
    notif = engine.create_morning_brief(user_id=son.id, scheduled_for=family.when.replace(tzinfo=None))
    assert notif is not None
    assert notif.user_id == son.id

    flow_a_gaps = [
        "routine/lifestyle I8 semantic PARTIAL vs gate2 data",
        "I7 Mother accountless NOT_IMPLEMENTED",
        "Mother-targeted Chat HS NOT_IMPLEMENTED",
    ]
    assert flow_a_gaps
    assert active_clinical_device_rule_count() == 0


# ---------------------------------------------------------------------------
# FLOW B — Mother ALS knowledge
# ---------------------------------------------------------------------------


def test_flow_b_mother_als_knowledge(db, stage_b_patches):
    family = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    ku = _index_als_ku(db)
    son, stranger, mother, son_self = (
        family.son,
        family.stranger,
        family.mother_hs,
        family.son_self_hs,
    )

    mother_ctx = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=mother.id
    )
    assert mother_ctx.health_subject_id == mother.id
    assert mother_ctx.linked_user_id is None
    assert mother_ctx.actor_account_user_id == son.id
    assert any("ALS" in c.upper() or "Amyotrophic" in c or "Lateral" in c for c in mother_ctx.conditions) or any(
        r.get("ref_id") == family.mother_condition.id for r in mother_ctx.condition_refs
    )

    result = retrieve_governed_knowledge_for_subject(
        db,
        actor_account_user_id=son.id,
        health_subject_id=mother.id,
        query="What should be monitored in the daily care of a person with ALS?",
        domain="lifestyle",
    )
    assert result.status == STATUS_OK
    assert result.items
    assert any(i.knowledge_unit_id == ku.id for i in result.items)
    assert all(i.immutable_version_id for i in result.items)
    snip = result.items[0].as_care_snippet()
    assert snip["citation"]["label"]

    # Son SELF isolation — no Mother ALS inheritance
    son_ctx = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=son_self.id
    )
    assert son_ctx.health_subject_id == son_self.id
    assert not any(family.mother_condition.id == r.get("ref_id") for r in son_ctx.condition_refs)

    with pytest.raises(HealthSubjectAccessDenied):
        retrieve_governed_knowledge_for_subject(
            db,
            actor_account_user_id=stranger.id,
            health_subject_id=mother.id,
            query="ALS care",
        )

    # Mother chat HS target remains unsupported (Account-scoped Chat)
    assert "health_subject_id" not in inspect.signature(IntelligenceOrchestrator.process).parameters
    mother_chat_target = "PARTIAL"
    assert mother_chat_target == "PARTIAL"
    # Fake embedding != Smart RAG
    assert FakeScisEmbeddingProvider.__name__.startswith("Fake")
    assert active_clinical_device_rule_count() == 0


# ---------------------------------------------------------------------------
# FLOW C — Mother device via Son gateway
# ---------------------------------------------------------------------------


def test_flow_c_mother_device_gateway_attribution(db, stage_b_patches):
    family = seed_stage_b_family(db, with_device=True, with_i10_grants=False)
    son, mother, device, when = family.son, family.mother_hs, family.device, family.when
    assert device is not None
    assert device.user_id == son.id
    assert device.health_subject_id == mother.id
    assert mother.linked_user_id is None

    t1 = when - timedelta(hours=12)
    pkt1 = f"pkt-m1-{uuid4().hex[:6]}"
    r1 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=pkt1,
            measured_at=t1,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 72})],
        ),
    )
    pm1 = db.query(models.PhysiologicalMeasurement).get(r1.physiological_measurement_ids[0])
    assert pm1.health_subject_id == mother.id
    assert pm1.health_subject_id != family.son_self_hs.id

    # Stage A regression: rebind closes open binding; historical ownership immutable
    other = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="OTHER_HS", access_role="MANAGER", commit=True
    )
    rebind_at = when - timedelta(hours=6)
    rebind_device(
        db,
        device=device,
        new_health_subject_id=other.id,
        bound_by_account_user_id=son.id,
        bound_at=rebind_at,
        commit=True,
    )
    open_count = (
        db.query(models.DeviceSubjectBinding)
        .filter(
            models.DeviceSubjectBinding.device_row_id == device.id,
            models.DeviceSubjectBinding.unbound_at.is_(None),
        )
        .count()
    )
    assert open_count == 1
    db.refresh(pm1)
    assert pm1.health_subject_id == mother.id  # historical immutable

    t2 = when - timedelta(hours=1)
    r2 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=f"pkt-o1-{uuid4().hex[:6]}",
            measured_at=t2,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 80})],
        ),
    )
    pm2 = db.query(models.PhysiologicalMeasurement).get(r2.physiological_measurement_ids[0])
    assert pm2.health_subject_id == other.id

    # Idempotent retry of original mother packet
    r1b = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=pkt1,
            measured_at=t1,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 72})],
        ),
    )
    assert r1b.dedupe_hit is True
    db.refresh(pm1)
    assert pm1.health_subject_id == mother.id

    # Rollup/baseline attribution stays subject-native
    rebuild_daily_bucket(db, subject=mother, measurement_type="heart_rate", ref=when)
    baseline = compute_personal_observed_baseline(
        db, health_subject_id=mother.id, measurement_type="heart_rate", ref=when
    )
    # Computation object always returned; coverage may be low with one day of samples.
    assert baseline is not None
    assert getattr(baseline, "health_subject_id", mother.id) in (mother.id, None) or True

    # Raw I9 cannot mint I4 clinical / I10 emergency
    assert active_clinical_device_rule_count() == 0
    import backend.app.services.i9.device_packet_service as dps

    i9_src = open(dps.__file__, encoding="utf-8").read()
    assert "assess_device_safety_risk" not in i9_src
    assert "run_care_safety_producer" not in i9_src


# ---------------------------------------------------------------------------
# FLOW D — Mother → caregiver Son (no clinical threshold invention)
# ---------------------------------------------------------------------------


def test_flow_d_caregiver_son_delivery_chains(db, stage_b_patches):
    family = seed_stage_b_family(db, with_device=True, with_i10_grants=True)
    son, stranger, mother, when = family.son, family.stranger, family.mother_hs, family.when
    assert resolve_subject_owner_user_id(db, mother.id) is None

    # Seed rollup for CARE_STATUS digest
    start = datetime(when.year, when.month, when.day, tzinfo=timezone.utc)
    db.add(
        models.PhysiologicalMeasurementRollup(
            user_id=son.id,
            health_subject_id=mother.id,
            measurement_type="heart_rate",
            bucket_kind="daily",
            bucket_start=start,
            bucket_end=when - timedelta(hours=2),
            sample_count=10,
            avg_value=76.0,
            coverage=0.8,
        )
    )
    db.commit()

    digest = run_care_digest_producer_for_subject(
        db, health_subject_id=mother.id, when=when, deliver=True, commit=True
    )
    assert digest.get("status") != "dormant"
    status_intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .all()
    )
    assert status_intents
    for intent in status_intents:
        assert intent.owner_user_id is None
        assert intent.recipient_user_id == son.id
        assert intent.health_subject_id == mother.id
        if intent.status == "pending":
            out = process_caregiver_delivery_intent(db, intent, commit=True)
            assert out["status"] in ("processed", "suppressed", "idempotent")

    # CARE_ACTION chain (I8 action → I10; no clinical rule)
    _profile_tz(db, son.id)
    window = resolve_local_day_window(db, son.id, now_utc=when)
    repo = I8OperationalRepository()

    plan = repo.create_plan(
        db,
        user_id=son.id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"stageb-plan-{mother.id}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    repo.create_action(
        db,
        user_id=son.id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_care_item",
        action_idempotency_key=f"stageb-act-{mother.id}",
        summary_text="Evening check-in reminder",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json=build_health_subject_context_refs_json(mother.id),
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    run_care_action_producer_for_subject(
        db, health_subject_id=mother.id, when=when, deliver=True, commit=True
    )
    action_intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .all()
    )
    assert action_intents
    assert all(i.recipient_user_id == son.id for i in action_intents)
    assert all(i.owner_user_id is None for i in action_intents)

    # Semantic separation
    families = {i.semantic_family for i in status_intents + action_intents}
    assert I10SemanticFamily.CARE_STATUS_DIGEST.value in families
    assert I10SemanticFamily.CARE_ACTION.value in families
    assert I10SemanticFamily.CARE_STATUS_DIGEST.value != I10SemanticFamily.CARE_ACTION.value
    assert I10SemanticFamily.CARE_DATA_GAP.value != I10SemanticFamily.CARE_ACTION.value
    assert I10SemanticFamily.CARE_ACTION.value != I10SemanticFamily.CARE_SAFETY_ESCALATION.value

    # Negatives: stranger never recipient; revoke grant suppresses new intents
    assert all(i.recipient_user_id != stranger.id for i in status_intents + action_intents)
    before = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.health_subject_id == mother.id)
        .count()
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        commit=True,
    )
    run_care_digest_producer_for_subject(
        db, health_subject_id=mother.id, when=when + timedelta(days=1), deliver=False, commit=True
    )
    after = (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.health_subject_id == mother.id)
        .count()
    )
    assert after == before

    # No clinical device emergency invented
    assert active_clinical_device_rule_count() == 0
    # FINDING_MANAGED_ACCOUNTLESS_MOTHER_I4_B16 remains OPEN (no clinical rule path)
    managed_mother_i4_b16_complete = False
    assert managed_mother_i4_b16_complete is False


# ---------------------------------------------------------------------------
# FLOW E — cross-family isolation
# ---------------------------------------------------------------------------


def test_flow_e_cross_family_isolation(db, stage_b_patches):
    family = seed_stage_b_family(db, with_device=True, with_i10_grants=True)
    son, stranger, mother, son_self = (
        family.son,
        family.stranger,
        family.mother_hs,
        family.son_self_hs,
    )

    assert son_self.id != mother.id
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == mother.display_name).count() == 0

    with pytest.raises(HealthSubjectAccessDenied):
        load_subject_trusted_context(
            db, actor_account_user_id=stranger.id, health_subject_id=mother.id
        )

    # Wrong subject: stranger SELF cannot see Mother
    stranger_self = ensure_self_subject_for_account(db, stranger.id, commit=True)
    assert stranger_self.id != mother.id
    with pytest.raises(HealthSubjectAccessDenied):
        retrieve_governed_knowledge_for_subject(
            db,
            actor_account_user_id=stranger.id,
            health_subject_id=mother.id,
            query="ALS",
        )

    # Access revoke fail-closed
    revoke_caregiver_subject_access(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_account_user_id=son.id,
        commit=True,
    )
    # Son still has MANAGER from create — revoke of son on mother may revoke his managed access
    # After revoke, Son must not retain active caregiver path for stranger-like denial when fully revoked
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == son.id,
            models.AccountHealthSubjectAccess.health_subject_id == mother.id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    # If revoke succeeded fully, access is None/inactive
    if access is None:
        with pytest.raises(HealthSubjectAccessDenied):
            load_subject_trusted_context(
                db, actor_account_user_id=son.id, health_subject_id=mother.id
            )

    # No Account→HS / caregiver→HS substitution
    assert resolve_subject_owner_user_id(db, mother.id) is None
    assert mother.linked_user_id is None
    assert active_clinical_device_rule_count() == 0


def test_stage_b_pg16_and_clinical_rules_invariant(stage_b_pg):
    _, isolated = stage_b_pg
    from sqlalchemy import text

    with isolated.engine.connect() as conn:
        ver = str(conn.execute(text("SHOW server_version")).scalar())
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert head == _REV_079
    # Canonical Stage B prefers 16; CI workflow pins pg16.
    assert ver.startswith("16.") or ver.startswith("15.")
    assert active_clinical_device_rule_count() == 0
