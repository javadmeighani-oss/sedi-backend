"""I9→I10 DeviceReportedVitalStatus — gadget STABLE|UNSTABLE SoT (GATE I9-I10-01).

PG16 required. No MAD/RAG/LLM/clinical status authority.
"""

from __future__ import annotations

import ast
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text

from backend.app import models
from backend.app.services.i10.care_network_grants import revoke_subject_notification_grant_by_scope
from backend.app.services.i10.care_subject_status_facts import assemble_care_subject_status_facts
from backend.app.services.i10.caregiver_data_gap import is_care_data_gap_candidate
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.device_reported_vital_status_producer import (
    render_device_reported_vital_status_body,
    should_notify_device_reported_transition,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.device_binding_service import rebind_device
from backend.app.services.i9.device_packet_service import (
    DevicePacketIngestInput,
    PacketObservationIn,
    ingest_device_packet,
)
from backend.app.services.i9.device_reported_vital_status import (
    OBSERVATION_TYPE,
    SOURCE_CLASS,
    get_effective_device_reported_vital_status,
)
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account
from backend.app.services.intelligence.device_safety_registry import active_clinical_device_rule_count
from backend.app.services.vitals.vital_registry import VitalValidationError
from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_079,
    _REV_080,
    pg_table_exists,
)
from backend.tests.helpers.stage_b_family_fixture import seed_stage_b_family

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4 = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAGS = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
        "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
    },
    clear=False,
)

FORBIDDEN = ("safe", "healthy", "danger", "emergency", "diagnosis", "critical", "medically")


@pytest.fixture
def patches():
    with _GATE4, _FLAGS:
        yield


@pytest.fixture(scope="module")
def drvs_pg():
    isolated = I10IsolatedPgDb.create(suffix="drvs", revision=_REV_080)
    assert isolated.head() == _REV_080
    with isolated.engine.connect() as conn:
        ver = conn.execute(text("SHOW server_version")).scalar()
        assert str(ver).startswith("16."), ver
        assert pg_table_exists(conn, "device_reported_vital_statuses")
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture
def db(drvs_pg):
    SessionLocal, isolated = drvs_pg
    connection = isolated.engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _ingest_status(db, device, *, status: str, when, client_packet_id: str | None = None, commit=False):
    return ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=client_packet_id or f"pkt-{uuid4().hex[:10]}",
            measured_at=when,
            observations=[
                PacketObservationIn(
                    observation_type=OBSERVATION_TYPE,
                    payload={"status": status},
                    detected_at=when,
                )
            ],
        ),
        commit=commit,
    )


def _device_intents(db, health_subject_id: int, recipient_user_id: int | None = None):
    q = db.query(models.CaregiverNotificationIntent).filter(
        models.CaregiverNotificationIntent.health_subject_id == health_subject_id,
        models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.DEVICE_STATUS.value,
        models.CaregiverNotificationIntent.source_entity_type == "I10_DEVICE_REPORTED_VITAL_STATUS",
    )
    if recipient_user_id is not None:
        q = q.filter(models.CaregiverNotificationIntent.recipient_user_id == recipient_user_id)
    return q.order_by(models.CaregiverNotificationIntent.id.asc()).all()


def _assert_safe_body(body: str) -> None:
    lower = body.lower()
    for word in FORBIDDEN:
        assert word not in lower, word


# --- 01–08 ingest / identity ---


def test_01_stable_to_mother_hs(db, patches):
    family = seed_stage_b_family(db, commit=False)
    when = family.when
    r = _ingest_status(db, family.device, status="STABLE", when=when)
    assert r.dedupe_hit is False
    assert len(r.vital_status_ids) == 1
    row = db.query(models.DeviceReportedVitalStatus).get(r.vital_status_ids[0])
    assert row.health_subject_id == family.mother_hs.id
    assert row.status == "STABLE"
    assert row.source_class == SOURCE_CLASS


def test_02_unstable_to_mother_hs(db, patches):
    family = seed_stage_b_family(db, commit=False)
    r = _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    row = db.query(models.DeviceReportedVitalStatus).get(r.vital_status_ids[0])
    assert row.health_subject_id == family.mother_hs.id
    assert row.status == "UNSTABLE"


def test_03_no_fake_mother_account(db, patches):
    family = seed_stage_b_family(db, commit=False)
    assert family.mother_hs.linked_user_id is None
    assert family.mother_hs.subject_kind == "managed"
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0
    _ingest_status(db, family.device, status="STABLE", when=family.when)
    assert family.mother_hs.linked_user_id is None


def test_04_son_gateway_not_mother_data_owner(db, patches):
    family = seed_stage_b_family(db, commit=False)
    assert family.device.user_id == family.son.id
    assert family.device.health_subject_id == family.mother_hs.id
    assert family.mother_hs.linked_user_id is None
    r = _ingest_status(db, family.device, status="STABLE", when=family.when)
    row = db.query(models.DeviceReportedVitalStatus).get(r.vital_status_ids[0])
    assert row.health_subject_id == family.mother_hs.id
    assert row.health_subject_id != family.son_self_hs.id


def test_05_duplicate_packet_idempotent(db, patches):
    family = seed_stage_b_family(db, commit=False)
    pkt = f"dup-{uuid4().hex[:8]}"
    r1 = _ingest_status(db, family.device, status="STABLE", when=family.when, client_packet_id=pkt)
    r2 = _ingest_status(db, family.device, status="STABLE", when=family.when, client_packet_id=pkt)
    assert r1.dedupe_hit is False
    assert r2.dedupe_hit is True
    assert (
        db.query(models.DeviceReportedVitalStatus)
        .filter(models.DeviceReportedVitalStatus.health_subject_id == family.mother_hs.id)
        .count()
        == 1
    )
    assert len(_device_intents(db, family.mother_hs.id, family.son.id)) == 1


def test_06_invalid_verdict_fail_closed(db, patches):
    family = seed_stage_b_family(db, commit=False)
    with pytest.raises(VitalValidationError):
        ingest_device_packet(
            db,
            device=family.device,
            packet_in=DevicePacketIngestInput(
                client_packet_id=f"bad-{uuid4().hex[:8]}",
                measured_at=family.when,
                observations=[
                    PacketObservationIn(
                        observation_type=OBSERVATION_TYPE,
                        payload={"status": "DANGER"},
                    )
                ],
            ),
            commit=False,
        )
    assert (
        db.query(models.DeviceReportedVitalStatus)
        .filter(models.DeviceReportedVitalStatus.health_subject_id == family.mother_hs.id)
        .count()
        == 0
    )


def test_06b_missing_status_fail_closed(db, patches):
    family = seed_stage_b_family(db, commit=False)
    with pytest.raises(VitalValidationError):
        ingest_device_packet(
            db,
            device=family.device,
            packet_in=DevicePacketIngestInput(
                client_packet_id=f"miss-{uuid4().hex[:8]}",
                measured_at=family.when,
                observations=[PacketObservationIn(observation_type=OBSERVATION_TYPE, payload={})],
            ),
            commit=False,
        )
    assert (
        db.query(models.DeviceReportedVitalStatus)
        .filter(models.DeviceReportedVitalStatus.health_subject_id == family.mother_hs.id)
        .count()
        == 0
    )


def test_07_unbound_device_rejected(db, patches):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    from backend.app.core.device_auth import hash_device_token

    unbound = models.Device(
        user_id=family.son.id,
        device_id=f"unbound-{uuid4().hex[:6]}",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-unbound"),
    )
    db.add(unbound)
    db.flush()
    with pytest.raises(ValueError, match="NO_ACTIVE_DEVICE_SUBJECT_BINDING"):
        _ingest_status(db, unbound, status="STABLE", when=family.when)


def test_08_historical_binding_immutable(db, patches):
    family = seed_stage_b_family(db, commit=False)
    when = family.when
    r1 = _ingest_status(db, family.device, status="STABLE", when=when - timedelta(hours=2))
    row1 = db.query(models.DeviceReportedVitalStatus).get(r1.vital_status_ids[0])
    other = create_managed_subject_without_account(
        db, account_user_id=family.son.id, display_name="OTHER", access_role="MANAGER", commit=False
    )
    rebind_device(
        db,
        device=family.device,
        new_health_subject_id=other.id,
        bound_by_account_user_id=family.son.id,
        bound_at=when - timedelta(hours=1),
        commit=False,
    )
    db.refresh(row1)
    assert row1.health_subject_id == family.mother_hs.id
    r2 = _ingest_status(db, family.device, status="UNSTABLE", when=when)
    row2 = db.query(models.DeviceReportedVitalStatus).get(r2.vital_status_ids[0])
    assert row2.health_subject_id == other.id


# --- 09–14 transitions / dedupe ---


def test_09_first_stable_one_son_notification(db, patches):
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="STABLE", when=family.when)
    intents = _device_intents(db, family.mother_hs.id, family.son.id)
    assert len(intents) == 1
    assert intents[0].owner_user_id is None
    meta = intents[0].payload_metadata_json or ""
    assert "stable" in meta.lower()
    _assert_safe_body(meta)


def test_10_first_unstable_one_son_notification(db, patches):
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    intents = _device_intents(db, family.mother_hs.id, family.son.id)
    assert len(intents) == 1
    assert "unstable" in (intents[0].payload_metadata_json or "").lower()
    _assert_safe_body(intents[0].payload_metadata_json or "")


def test_11_stable_to_unstable_notifies(db, patches):
    family = seed_stage_b_family(db, commit=False)
    t0 = family.when
    _ingest_status(db, family.device, status="STABLE", when=t0)
    _ingest_status(db, family.device, status="UNSTABLE", when=t0 + timedelta(minutes=5))
    intents = _device_intents(db, family.mother_hs.id, family.son.id)
    assert len(intents) == 2
    assert "unstable" in (intents[-1].payload_metadata_json or "").lower()


def test_12_unstable_to_stable_recovery_notification(db, patches):
    family = seed_stage_b_family(db, commit=False)
    t0 = family.when
    _ingest_status(db, family.device, status="UNSTABLE", when=t0)
    _ingest_status(db, family.device, status="STABLE", when=t0 + timedelta(minutes=5))
    intents = _device_intents(db, family.mother_hs.id, family.son.id)
    assert len(intents) == 2
    body = render_device_reported_vital_status_body(previous_status="UNSTABLE", new_status="STABLE")
    assert "returned to stable" in body.lower()
    assert body in (intents[-1].payload_metadata_json or "")
    _assert_safe_body(body)


def test_13_stable_repeat_dedupe(db, patches):
    family = seed_stage_b_family(db, commit=False)
    t0 = family.when
    _ingest_status(db, family.device, status="STABLE", when=t0)
    _ingest_status(db, family.device, status="STABLE", when=t0 + timedelta(minutes=5))
    assert len(_device_intents(db, family.mother_hs.id, family.son.id)) == 1


def test_14_unstable_repeat_dedupe(db, patches):
    family = seed_stage_b_family(db, commit=False)
    t0 = family.when
    _ingest_status(db, family.device, status="UNSTABLE", when=t0)
    _ingest_status(db, family.device, status="UNSTABLE", when=t0 + timedelta(minutes=5))
    assert len(_device_intents(db, family.mother_hs.id, family.son.id)) == 1


# --- 15–19 access / prefs / wrong HS ---


def test_15_stranger_blocked(db, patches):
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    assert len(_device_intents(db, family.mother_hs.id, family.stranger.id)) == 0
    assert len(_device_intents(db, family.mother_hs.id, family.son.id)) == 1


def test_16_access_revoke_fail_closed(db, patches):
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="STABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    access_rows = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == family.mother_hs.id,
            models.AccountHealthSubjectAccess.account_user_id == family.son.id,
        )
        .all()
    )
    for a in access_rows:
        a.is_active = False
        a.revoked_at = family.when.replace(tzinfo=None)
    db.flush()
    outcome = process_caregiver_delivery_intent(db, intent, commit=False)
    assert outcome["status"] == "suppressed"


def test_17_grant_revoke_fail_closed(db, patches):
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=family.son.id,
        health_subject_id=family.mother_hs.id,
        recipient_user_id=family.son.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        commit=False,
    )
    outcome = process_caregiver_delivery_intent(db, intent, commit=False)
    assert outcome["status"] == "suppressed"


def test_18_prefs_respected(db, patches):
    family = seed_stage_b_family(db, commit=False)
    prefs = db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == family.son.id).one()
    prefs.health_alert_enabled = False
    db.flush()
    _ingest_status(db, family.device, status="STABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    outcome = process_caregiver_delivery_intent(db, intent, commit=False)
    assert outcome["status"] == "suppressed"


def test_19_wrong_health_subject_blocked(db, patches):
    family = seed_stage_b_family(db, commit=False)
    other = create_managed_subject_without_account(
        db, account_user_id=family.son.id, display_name="OTHER2", access_role="MANAGER", commit=False
    )
    _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    assert len(_device_intents(db, other.id, family.son.id)) == 0
    assert len(_device_intents(db, family.mother_hs.id, family.son.id)) == 1


# --- 20–25 ordering / safety / silence / tx ---


def test_20_out_of_order_cannot_corrupt_current(db, patches):
    family = seed_stage_b_family(db, commit=False)
    t_new = family.when
    t_old = family.when - timedelta(hours=2)
    _ingest_status(db, family.device, status="UNSTABLE", when=t_new)
    before = get_effective_device_reported_vital_status(db, health_subject_id=family.mother_hs.id)
    assert before is not None and before.status == "UNSTABLE"
    count_before = len(_device_intents(db, family.mother_hs.id, family.son.id))
    _ingest_status(db, family.device, status="STABLE", when=t_old)
    after = get_effective_device_reported_vital_status(db, health_subject_id=family.mother_hs.id)
    assert after is not None
    assert after.status == "UNSTABLE"
    assert after.row_id == before.row_id
    assert len(_device_intents(db, family.mother_hs.id, family.son.id)) == count_before
    assert (
        db.query(models.DeviceReportedVitalStatus)
        .filter(models.DeviceReportedVitalStatus.health_subject_id == family.mother_hs.id)
        .count()
        == 2
    )


def test_21_no_rag_llm_status_decision(db, patches):
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    paths = [
        root / "i9" / "device_packet_service.py",
        root / "i9" / "device_reported_vital_status.py",
        root / "i10" / "device_reported_vital_status_producer.py",
        root / "i10" / "care_subject_status_facts.py",
    ]
    banned = ("openai", "text-embedding", "chat.completions", "smart_rag", "smartrag")
    for path in paths:
        src = path.read_text(encoding="utf-8").lower()
        for token in banned:
            assert token not in src, f"{path.name}:{token}"
        ast.parse(path.read_text(encoding="utf-8"))


def test_22_clinical_rule_count_zero(db, patches):
    assert active_clinical_device_rule_count() == 0
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    assert active_clinical_device_rule_count() == 0
    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "i9" / "device_packet_service.py").read_text(
        encoding="utf-8"
    )
    assert "assess_device_safety_risk" not in src


def test_23_unstable_never_emergency_danger_diagnosis(db, patches):
    family = seed_stage_b_family(db, commit=False)
    _ingest_status(db, family.device, status="UNSTABLE", when=family.when)
    intent = _device_intents(db, family.mother_hs.id, family.son.id)[0]
    meta = intent.payload_metadata_json or ""
    _assert_safe_body(meta)
    assert intent.semantic_family == I10SemanticFamily.DEVICE_STATUS.value
    assert intent.notification_scope == I10NotificationScope.DEVICE_STATUS.value
    assert "SAFETY" not in (intent.semantic_family or "")
    facts = assemble_care_subject_status_facts(db, health_subject_id=family.mother_hs.id, when=family.when)
    # Canonical HR monitoring uses MAD evidence; without baseline → INSUFFICIENT_DATA (not gadget DRVS label).
    assert facts.monitoring_status == "INSUFFICIENT_DATA"
    assert facts.monitoring_status not in ("emergency", "danger", "diagnosis")
    assert get_effective_device_reported_vital_status(db, health_subject_id=family.mother_hs.id) is not None


def test_24_silence_never_becomes_stable_or_unstable(db, patches):
    family = seed_stage_b_family(db, commit=False)
    facts = assemble_care_subject_status_facts(db, health_subject_id=family.mother_hs.id, when=family.when)
    assert facts.monitoring_status == "INSUFFICIENT_DATA"
    assert facts.monitoring_status not in ("STABLE", "UNSTABLE", "UNSTABLE_OR_CHANGED")
    # CARE_DATA_GAP remains a separate path; silence must not invent gadget verdict.
    assert get_effective_device_reported_vital_status(db, health_subject_id=family.mother_hs.id) is None


def test_25_transaction_failure_rollback(patches):
    isolated = I10IsolatedPgDb.create(suffix="drvs_tx", revision=_REV_080)
    SessionLocal = isolated.session_factory()
    db = SessionLocal()
    try:
        family = seed_stage_b_family(db, commit=True)
        mother_id = family.mother_hs.id
        device = db.query(models.Device).get(family.device.id)
        pkt = f"tx-{uuid4().hex[:8]}"

        def _boom(*_a, **_k):
            raise RuntimeError("SIMULATED_TX_FAILURE")

        with patch(
            "backend.app.services.i10.device_reported_vital_status_producer.emit_device_reported_vital_status_notifications",
            side_effect=_boom,
        ):
            with pytest.raises(RuntimeError, match="SIMULATED_TX_FAILURE"):
                _ingest_status(db, device, status="STABLE", when=family.when, client_packet_id=pkt, commit=True)
        db.rollback()
        assert db.query(models.DevicePacket).filter(models.DevicePacket.client_packet_id == pkt).count() == 0
        assert (
            db.query(models.DeviceReportedVitalStatus)
            .filter(models.DeviceReportedVitalStatus.health_subject_id == mother_id)
            .count()
            == 0
        )
        assert (
            db.query(models.CaregiverNotificationIntent)
            .filter(
                models.CaregiverNotificationIntent.health_subject_id == mother_id,
                models.CaregiverNotificationIntent.source_entity_type == "I10_DEVICE_REPORTED_VITAL_STATUS",
            )
            .count()
            == 0
        )
    finally:
        db.close()
        isolated.close()


# --- 26–28 regression / migration ---


def test_26_family_stage_b_identity_regression(db, patches):
    family = seed_stage_b_family(db, commit=False)
    assert family.mother_hs.linked_user_id is None
    assert family.device.user_id == family.son.id
    assert family.device.health_subject_id == family.mother_hs.id
    _ingest_status(db, family.device, status="STABLE", when=family.when)
    assert family.son_self_hs.id != family.mother_hs.id


def test_27_care_data_gap_isolation_and_mad_not_authority(db, patches):
    family = seed_stage_b_family(db, commit=False)
    facts = assemble_care_subject_status_facts(db, health_subject_id=family.mother_hs.id, when=family.when)
    # Without sufficient MAD evidence → INSUFFICIENT_DATA (never invent STABLE/UNSTABLE gadget labels).
    assert facts.monitoring_status not in ("STABLE", "UNSTABLE", "NONCLINICAL_STABLE", "NONCLINICAL_CHANGED")
    assert facts.monitoring_status == "INSUFFICIENT_DATA"
    import backend.app.services.i9.nonclinical_vital_stability as mad

    assert callable(mad.evaluate_nonclinical_heart_rate_stability)
    facts2 = assemble_care_subject_status_facts(db, health_subject_id=family.mother_hs.id, when=family.when)
    assert facts2.monitoring_status == "INSUFFICIENT_DATA"
    # data-gap helper remains importable / separate
    assert callable(is_care_data_gap_candidate)
    # stranger still blocked after later status
    _ingest_status(db, family.device, status="STABLE", when=family.when)
    assert len(_device_intents(db, family.mother_hs.id, family.stranger.id)) == 0


def test_28_migration_upgrade_downgrade_upgrade():
    isolated = I10IsolatedPgDb.create(suffix="drvs_mig", revision=_REV_079)
    try:
        assert isolated.head() == _REV_079
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "device_reported_vital_statuses")
        command.upgrade(isolated.cfg, _REV_080)
        assert isolated.head() == _REV_080
        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "device_reported_vital_statuses")
            ck = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM information_schema.check_constraints
                    WHERE constraint_name IN ('ck_drvs_status', 'ck_drvs_source_class')
                    """
                )
            ).scalar_one()
            assert ck >= 2
        command.downgrade(isolated.cfg, _REV_079)
        assert isolated.head() == _REV_079
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "device_reported_vital_statuses")
        command.upgrade(isolated.cfg, _REV_080)
        assert isolated.head() == _REV_080
        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "device_reported_vital_statuses")
    finally:
        isolated.close()


def test_should_notify_helper_dedupe_and_ooo():
    from backend.app.services.i9.device_reported_vital_status import EffectiveVitalStatus
    from datetime import datetime, timezone

    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    prev = EffectiveVitalStatus("STABLE", 1, when, 9, 100)
    newer = EffectiveVitalStatus("UNSTABLE", 2, when + timedelta(minutes=1), 9, 101)
    older = EffectiveVitalStatus("STABLE", 3, when - timedelta(minutes=1), 9, 102)
    assert should_notify_device_reported_transition(previous=prev, new_effective=newer, ingested_row_id=2) is True
    assert should_notify_device_reported_transition(previous=prev, new_effective=older, ingested_row_id=3) is False
    assert should_notify_device_reported_transition(previous=prev, new_effective=prev, ingested_row_id=1) is False


def test_alembic_single_head_is_080():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("backend/alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [_REV_080]
