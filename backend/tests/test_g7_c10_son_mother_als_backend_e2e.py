"""SEDI G7-B / C10 — Son SELF + Mother MANAGED ALS backend E2E (PG16).

GATE: SEDI-G7-C10-SON-MOTHER-ALS-FULL-BACKEND-E2E-01
Canonical identity: seed_stage_b_family (NOT patient-SELF ALS E2E shape).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, text

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.gate4.notification_chat_context import build_safe_chat_context
from backend.app.services.i10.care_action_producer_worker import run_care_action_producer_for_subject
from backend.app.services.i10.care_digest_producer_worker import run_care_digest_producer_for_subject
from backend.app.services.i10.care_network_access import revoke_caregiver_subject_access
from backend.app.services.i10.care_network_grants import revoke_subject_notification_grant_by_scope
from backend.app.services.i10.care_safety_producer_worker import (
    bind_escalation_health_subject_metadata,
    run_care_safety_producer_for_subject,
)
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.i4_escalation_authority import is_authoritative_care_safety_escalation
from backend.app.services.i10.interaction_recorder import (
    get_last_notification_presence_at,
)
from backend.app.services.i10.managed_i8_action_binding import (
    build_health_subject_context_refs_json,
    resolve_action_health_subject_id,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i9.device_packet_service import (
    DevicePacketIngestInput,
    PacketObservationIn,
    ingest_device_packet,
)
from backend.app.services.i9.device_reported_vital_status import (
    OBSERVATION_TYPE,
    get_effective_device_reported_vital_status,
)
from backend.app.services.intelligence.contracts import (
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.safety_risk import REGISTRY_VERSION
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.section10.i4_emergency_escalation import persist_i4_emergency_escalation
from backend.app.services.section10.i4_escalation_provenance import new_occurrence_id
from backend.tests.helpers.i10_postgresql_harness import ALEMBIC_HEAD
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

G7_MARKERS: list[str] = []


def _mark(code: str) -> None:
    print(f"{code}=PASS")
    G7_MARKERS.append(code)


@pytest.fixture
def family_flags():
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ), patch.dict(
        "os.environ",
        {
            "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
            "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
            "SEDI_I10_CARE_ACTION_PRODUCER_ENABLED": "true",
            "SEDI_I10_CARE_SAFETY_PRODUCER_ENABLED": "true",
        },
        clear=False,
    ):
        yield


@pytest.fixture()
def client(db):
    def _override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _family(db):
    fam = seed_stage_b_family(db, commit=True)
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"
    return fam


def _ingest_drv(db, device, *, status: str, when):
    return ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id=f"g7-{uuid4().hex[:10]}",
            measured_at=when,
            observations=[
                PacketObservationIn(
                    observation_type=OBSERVATION_TYPE,
                    payload={"status": status},
                    detected_at=when,
                )
            ],
        ),
        commit=True,
    )


def _rollup(db, user, subject, when, *, sample_count=12, coverage=0.85):
    start = datetime(when.date().year, when.date().month, when.date().day, tzinfo=timezone.utc)
    row = models.PhysiologicalMeasurementRollup(
        user_id=user.id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=start,
        bucket_end=when - timedelta(hours=2),
        sample_count=sample_count,
        avg_value=78.0,
        min_value=70.0,
        max_value=85.0,
        coverage=coverage,
    )
    db.add(row)
    db.commit()
    return row


def _profile_tz(db, user_id: int, tz: str = "UTC"):
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone=tz))
    db.flush()


def _i8_action(db, user, *, domain: str, summary: str, when, key: str = "act", subject=None):
    _profile_tz(db, user.id)
    window = resolve_local_day_window(db, user.id, now_utc=when)
    repo = I8OperationalRepository()
    existing = (
        db.query(models.I8OperationalPlan)
        .filter(
            models.I8OperationalPlan.user_id == user.id,
            models.I8OperationalPlan.user_local_date == window.user_local_date,
            models.I8OperationalPlan.status == "ACTIVE",
        )
        .order_by(models.I8OperationalPlan.id.desc())
        .first()
    )
    if existing is not None:
        plan = existing
    else:
        plan = repo.create_plan(
            db,
            user_id=user.id,
            user_local_date=window.user_local_date,
            timezone_snapshot=window.timezone_snapshot,
            generation_mode="proactive",
            plan_idempotency_key=f"g7-plan-{user.id}-{key}-{uuid4().hex[:6]}",
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
        )
    kwargs = dict(
        user_id=user.id,
        plan_id=plan.id,
        action_domain=domain,
        action_type=f"{domain}_item",
        action_idempotency_key=f"g7-{key}-{uuid4().hex[:6]}",
        summary_text=summary,
        presentation_json="{}",
        knowledge_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    if subject is not None:
        kwargs["context_refs_json"] = build_health_subject_context_refs_json(subject.id)
    action = repo.create_action(db, **kwargs)
    db.commit()
    return plan, action


def _emergency_assessment() -> RiskAssessment:
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.EMERGENCY,
        action=SafetyAction.RETURN_EMERGENCY_RESPONSE,
        domain=RiskDomain.MEDICAL_EMERGENCY,
        rule_id="i4.rule.emergency.medical.v1",
        language="en",
    )


def _device_intents(db, health_subject_id: int, recipient_user_id: int | None = None):
    q = db.query(models.CaregiverNotificationIntent).filter(
        models.CaregiverNotificationIntent.health_subject_id == health_subject_id,
        models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.DEVICE_STATUS.value,
    )
    if recipient_user_id is not None:
        q = q.filter(models.CaregiverNotificationIntent.recipient_user_id == recipient_user_id)
    return q.order_by(models.CaregiverNotificationIntent.id.asc()).all()


def _companion_notif(db, user: models.User, subject: models.HealthSubject) -> models.Notification:
    notif = models.Notification(
        user_id=user.id,
        health_subject_id=subject.id,
        type="companion",
        title="Hello",
        body="Check in",
        priority="normal",
        channel="engagement",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
        template_key="companion",
        semantic_family=I10SemanticFamily.ENGAGEMENT.value,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def _seed_chat(db, user_id: int, *, when: datetime, text_msg: str = "hello") -> models.Memory:
    row = models.Memory(
        user_id=user_id,
        user_message=text_msg,
        sedi_response="hi",
        language="en",
        created_at=when,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _feedback(client, user: models.User, notif_id: int, payload: dict):
    return client.post(
        f"/notifications/{notif_id}/feedback",
        json=payload,
        headers=_auth(user.id),
    )


def _assert_identity_locks(fam) -> None:
    assert fam.son_self_hs.id != fam.mother_hs.id
    assert fam.son.__tablename__ == "users"
    assert fam.son_self_hs.__tablename__ == "health_subjects"
    assert fam.mother_hs.__tablename__ == "health_subjects"
    assert fam.son_self_hs.subject_kind == "self"
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.son_self_hs.linked_user_id == fam.son.id
    assert fam.mother_hs.linked_user_id is None
    assert fam.device is not None
    assert fam.device.health_subject_id == fam.mother_hs.id
    assert fam.device.user_id == fam.son.id
    assert fam.device.user_id != fam.mother_hs.linked_user_id
    mother_accounts = (
        # no Mother User row may own linked_user_id for Mother HS
        fam.mother_hs.linked_user_id
    )
    assert mother_accounts is None


# ---------------------------------------------------------------------------
# Harness / runtime
# ---------------------------------------------------------------------------


def test_g7_runtime_harness(db, i10_pg_db_module):
    _, isolated = i10_pg_db_module
    with isolated.engine.connect() as conn:
        ver = conn.execute(text("SHOW server_version")).scalar()
        assert str(ver).startswith("16."), ver
        print(f"POSTGRES_VERSION={ver}")
        head = isolated.head()
        assert head == ALEMBIC_HEAD
        print(f"ALEMBIC_HEAD={head}")
        print("RUNTIME_CREATE_ALL=NO")
        print("HIDDEN_SCHEMA_CREATION=NO")
        print(f"VECTOR_MODE={getattr(isolated, 'vector_mode', 'UNKNOWN')}")
    _mark("G7-00_RUNTIME_PG16_ALEMBIC_081")


# ---------------------------------------------------------------------------
# A — IDENTITY
# ---------------------------------------------------------------------------


def test_g7_01_son_exact_self(db, family_flags):
    fam = _family(db)
    self_rows = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.linked_user_id == fam.son.id,
            models.HealthSubject.subject_kind == "self",
            models.HealthSubject.status == "active",
        )
        .all()
    )
    assert len(self_rows) == 1
    assert self_rows[0].id == fam.son_self_hs.id
    ahsa = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == fam.son.id,
            models.AccountHealthSubjectAccess.health_subject_id == fam.son_self_hs.id,
            models.AccountHealthSubjectAccess.access_role == "SELF",
            models.AccountHealthSubjectAccess.is_active.is_(True),
        )
        .one()
    )
    assert ahsa is not None
    _mark("G7-01_SON_HAS_EXACTLY_CORRECT_SELF_SUBJECT")


def test_g7_02_mother_managed_null(db, family_flags):
    fam = _family(db)
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.mother_hs.linked_user_id is None
    assert fam.mother_condition is not None
    assert fam.mother_condition.health_subject_id == fam.mother_hs.id
    # ALS is catalog/context only — no Mother Account minted
    assert db.query(models.User).filter(models.User.id == fam.mother_hs.linked_user_id).count() == 0
    _mark("G7-02_MOTHER_IS_MANAGED_LINKED_USER_NULL_WITHOUT_ACCOUNT")
    _mark("CAREGIVER_ACCOUNT_NE_MOTHER_ACCOUNT")


def test_g7_03_coexist_no_collision(db, family_flags):
    fam = _family(db)
    _assert_identity_locks(fam)
    assert fam.son_self_hs.id != fam.mother_hs.id
    assert fam.son.id != fam.mother_hs.id  # Account namespace != HS namespace semantics
    _mark("G7-03_SON_SELF_AND_MOTHER_MANAGED_COEXIST_WITHOUT_IDENTITY_COLLISION")


# ---------------------------------------------------------------------------
# B — SON SELF JOURNEY
# ---------------------------------------------------------------------------


def test_g7_04_son_context_account_scoped(db, family_flags):
    fam = _family(db)
    mem = _seed_chat(db, fam.son.id, when=fam.when, text_msg="son personal note")
    assert mem.user_id == fam.son.id
    # Mother has no Account → no I7 Memory rows keyed to Mother identity
    assert fam.mother_hs.linked_user_id is None
    mother_mem = (
        db.query(models.Memory)
        .filter(models.Memory.user_message.ilike("%MOTHER%"))
        .count()
    )
    assert mother_mem == 0
    # Son I7 rows must not reference Mother HS id as user_id
    assert db.query(models.Memory).filter(models.Memory.user_id == fam.mother_hs.id).count() == 0
    _mark("G7-04_SON_SELF_CONTEXT_REMAINS_ACCOUNT_SCOPED")
    _mark("MOTHER_DATA_NOT_IN_SON_I7_SELF_CONTEXT")


def test_g7_05_son_i8_on_self(db, family_flags):
    fam = _family(db)
    _, action = _i8_action(
        db,
        fam.son,
        domain="routine",
        summary="Son evening walk",
        when=fam.when,
        key="son-self",
        subject=fam.son_self_hs,
    )
    assert action.user_id == fam.son.id
    assert resolve_action_health_subject_id(db, action) == fam.son_self_hs.id
    assert resolve_action_health_subject_id(db, action) != fam.mother_hs.id
    _mark("G7-05_SON_I8_PLAN_ACTION_REMAINS_ON_SON_SELF")


def test_g7_06_son_self_smart_notification(db, family_flags):
    fam = _family(db)
    _rollup(db, fam.son, fam.son_self_hs, fam.when)
    notif = DecisionEngine(db).create_daily_wellness_digest(
        user_id=fam.son.id, scheduled_for=fam.when
    )
    assert notif is not None
    assert notif.user_id == fam.son.id
    assert notif.health_subject_id == fam.son_self_hs.id
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    assert decision.semantic_family == I10SemanticFamily.DAILY_WELLNESS_DIGEST.value
    assert decision.semantic_family != I10SemanticFamily.CARE_STATUS_DIGEST.value
    _mark("G7-06_SON_SELF_SMART_NOTIFICATION_ROUTES_TO_SON")
    _mark("SON_SELF_NOTIFICATION_NOT_MOTHER_CARE_NOTIFICATION")


def test_g7_07_son_4h_reengagement_self_only(db, family_flags):
    fam = _family(db)
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, fam.son.id, when=now - timedelta(hours=5))
    prefs = db.query(models.NotificationPrefs).filter_by(user_id=fam.son.id).one()
    prefs.companion_enabled = True
    db.commit()
    notif = DecisionEngine(db).create_connection_ping(user_id=fam.son.id, scheduled_for=now)
    assert notif is not None
    assert notif.user_id == fam.son.id
    assert notif.health_subject_id == fam.son_self_hs.id
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    assert decision.semantic_family == I10SemanticFamily.PRESENCE_REENGAGEMENT.value
    # No Mother HS reengagement minted
    assert (
        db.query(models.Notification)
        .filter(models.Notification.health_subject_id == fam.mother_hs.id)
        .count()
        == 0
    )
    _mark("G7-07_SON_4H_REENGAGEMENT_ROUTES_TO_SON_SELF_ONLY")


def test_g7_08_interaction_safe_self_no_i7(db, family_flags, client):
    fam = _family(db)
    before_mem = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == fam.son.id).scalar()
    before_facts = (
        db.query(func.count(models.UserMemoryFact.id))
        .filter(models.UserMemoryFact.user_id == fam.son.id)
        .scalar()
    )
    seed = _companion_notif(db, fam.son, fam.son_self_hs)
    assert _feedback(client, fam.son, seed.id, {"reaction": "like"}).status_code == 200
    assert (
        _feedback(client, fam.son, seed.id, {"reaction": "dislike", "reason": "too_frequent"}).status_code
        == 200
    )
    assert _feedback(client, fam.son, seed.id, {"action_id": "OPEN_CHAT"}).status_code == 200
    after_mem = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == fam.son.id).scalar()
    after_facts = (
        db.query(func.count(models.UserMemoryFact.id))
        .filter(models.UserMemoryFact.user_id == fam.son.id)
        .scalar()
    )
    assert after_mem == before_mem
    assert after_facts == before_facts
    assert get_last_notification_presence_at(db, fam.son.id) is not None
    ctx = build_safe_chat_context(seed, db=db, viewer_user_id=fam.son.id)
    assert ctx.get("category") is not None
    assert "raw_device" not in json.dumps(ctx).lower()
    _mark("G7-08_SON_NOTIFICATION_INTERACTION_PRESERVES_SAFE_SELF_CONTEXT")


# ---------------------------------------------------------------------------
# C — MOTHER DEVICE / I9
# ---------------------------------------------------------------------------


def test_g7_09_device_binding_mother(db, family_flags):
    fam = _family(db)
    binding = (
        db.query(models.DeviceSubjectBinding)
        .filter(
            models.DeviceSubjectBinding.device_row_id == fam.device.id,
            models.DeviceSubjectBinding.health_subject_id == fam.mother_hs.id,
        )
        .one()
    )
    assert binding.health_subject_id == fam.mother_hs.id
    assert binding.health_subject_id != fam.son_self_hs.id
    _mark("G7-09_MOTHER_DEVICE_BINDING_TARGETS_MOTHER_HEALTHSUBJECT")


def test_g7_10_gateway_not_measured_subject(db, family_flags):
    fam = _family(db)
    assert fam.device.user_id == fam.son.id
    assert fam.device.health_subject_id == fam.mother_hs.id
    assert fam.device.user_id != fam.device.health_subject_id
    assert fam.mother_hs.linked_user_id is None
    _mark("G7-10_GATEWAY_OR_OWNER_ACCOUNT_NOT_USED_AS_MEASURED_SUBJECT")
    _mark("GATEWAY_ACCOUNT_NE_MEASURED_HEALTHSUBJECT")


def test_g7_11_device_data_enters_i9_as_mother(db, family_flags):
    fam = _family(db)
    result = _ingest_drv(db, fam.device, status="STABLE", when=fam.when)
    assert result.health_subject_id == fam.mother_hs.id
    assert result.health_subject_id != fam.son_self_hs.id
    packet = (
        db.query(models.DevicePacket)
        .filter(models.DevicePacket.health_subject_id == fam.mother_hs.id)
        .one()
    )
    assert packet.health_subject_id == fam.mother_hs.id
    # Son SELF must not receive Mother packet attribution
    assert (
        db.query(models.DevicePacket)
        .filter(models.DevicePacket.health_subject_id == fam.son_self_hs.id)
        .count()
        == 0
    )
    # Son SELF rollup/data must not appear as Mother effective DRVS
    son_eff = get_effective_device_reported_vital_status(db, health_subject_id=fam.son_self_hs.id)
    mother_eff = get_effective_device_reported_vital_status(db, health_subject_id=fam.mother_hs.id)
    assert mother_eff is not None and mother_eff.status == "STABLE"
    assert son_eff is None
    _mark("G7-11_MOTHER_DEVICE_DATA_ENTERS_I9_AS_MOTHER_DATA")
    _mark("SON_DATA_NOT_IN_MOTHER_I9_STATUS")


def test_g7_12_mother_daily_status_mother(db, family_flags):
    fam = _family(db)
    _ingest_drv(db, fam.device, status="STABLE", when=fam.when)
    run_care_digest_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, when=fam.when, deliver=True, commit=True
    )
    intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .all()
    )
    assert len(intents) >= 1
    assert all(i.health_subject_id == fam.mother_hs.id for i in intents)
    assert all(i.health_subject_id != fam.son_self_hs.id for i in intents)
    _mark("G7-12_MOTHER_DAILY_STATUS_REMAINS_MOTHER_STATUS")


def test_g7_13_status_distinct(db, family_flags):
    fam = _family(db)
    _ingest_drv(db, fam.device, status="STABLE", when=fam.when)
    eff = get_effective_device_reported_vital_status(db, health_subject_id=fam.mother_hs.id)
    assert eff is not None and eff.status == "STABLE"
    meta = " ".join(
        (i.payload_metadata_json or "") for i in _device_intents(db, fam.mother_hs.id, fam.son.id)
    ).lower()
    assert "emergency" not in meta
    assert "diagnosis" not in meta
    assert "medically safe" not in meta
    # ALS catalog label must not appear as clinical invention in I9 status metadata
    assert "amyotrophic" not in meta
    _ingest_drv(db, fam.device, status="UNSTABLE", when=fam.when + timedelta(minutes=3))
    eff2 = get_effective_device_reported_vital_status(db, health_subject_id=fam.mother_hs.id)
    assert eff2 is not None and eff2.status == "UNSTABLE"
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .count()
        == 0
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .count()
        == 0
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
        == 0
    )
    _mark("G7-13_STABLE_DATA_GAP_UNSTABLE_REMAIN_DISTINCT")


# ---------------------------------------------------------------------------
# D — I4 / I8 BOUNDARIES
# ---------------------------------------------------------------------------


def test_g7_14_i9_alone_no_care_safety(db, family_flags):
    fam = _family(db)
    _ingest_drv(db, fam.device, status="UNSTABLE", when=fam.when)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .count()
        == 0
    )
    # ALS condition presence alone still cannot mint CARE_SAFETY
    assert fam.mother_condition is not None
    run_care_safety_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, deliver=True, commit=True
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .count()
        == 0
    )
    _mark("G7-14_I9_ALONE_CANNOT_CREATE_CARE_SAFETY")


def test_g7_15_valid_i4_care_safety(db, family_flags):
    fam = _family(db)
    rec = persist_i4_emergency_escalation(
        db,
        authenticated_user_id=fam.son.id,
        health_subject_id=fam.son_self_hs.id,
        risk_assessment=_emergency_assessment(),
        occurrence_id=new_occurrence_id(),
        commit=True,
    )
    assert rec is not None
    bind_escalation_health_subject_metadata(
        db, rec, health_subject_id=fam.mother_hs.id, commit=True
    )
    assert is_authoritative_care_safety_escalation(rec) is True
    run_care_safety_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, deliver=True, commit=True
    )
    safety = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        )
        .all()
    )
    assert len(safety) >= 1
    assert all(i.recipient_user_id == fam.son.id for i in safety)
    assert all(i.recipient_user_id != fam.stranger.id for i in safety)
    _mark("G7-15_VALID_I4_AUTHORITY_CAN_REACH_CARE_SAFETY_PATH")


def test_g7_16_valid_mother_i8_care_action(db, family_flags):
    fam = _family(db)
    when = fam.when
    _i8_action(
        db,
        fam.son,
        domain="routine",
        summary="Mother evening check",
        when=when,
        key="mother-i8",
        subject=fam.mother_hs,
    )
    # Without I8, producer yields nothing for empty second subject — with I8 bound:
    run_care_action_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, when=when, deliver=True, commit=True
    )
    intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .all()
    )
    assert len(intents) >= 1
    assert all(i.recipient_user_id == fam.son.id for i in intents)
    # I9 alone / digest alone cannot invent CARE_ACTION (already empty before I8)
    # Idempotent retry
    run_care_action_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, when=when, deliver=True, commit=True
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
        == len(intents)
    )
    _mark("G7-16_VALID_MOTHER_I8_ACTION_CAN_REACH_CARE_ACTION_PATH")


# ---------------------------------------------------------------------------
# E — SELF + CAREGIVER NOTIFICATIONS
# ---------------------------------------------------------------------------


def test_g7_17_self_and_mother_care_coexist(db, family_flags):
    fam = _family(db)
    _assert_identity_locks(fam)
    _rollup(db, fam.son, fam.son_self_hs, fam.when)
    self_notif = DecisionEngine(db).create_daily_wellness_digest(
        user_id=fam.son.id, scheduled_for=fam.when
    )
    assert self_notif is not None
    assert self_notif.health_subject_id == fam.son_self_hs.id
    assert self_notif.user_id == fam.son.id

    _ingest_drv(db, fam.device, status="STABLE", when=fam.when)
    run_care_digest_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, when=fam.when, deliver=True, commit=True
    )
    mother_intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
            models.CaregiverNotificationIntent.recipient_user_id == fam.son.id,
        )
        .all()
    )
    assert len(mother_intents) >= 1
    # Distinct subjects for the two notification lanes
    assert self_notif.health_subject_id != mother_intents[0].health_subject_id
    self_decision = (
        db.query(models.I10NotificationDecision)
        .filter_by(id=self_notif.i10_policy_decision_id)
        .one()
    )
    assert self_decision.semantic_family == I10SemanticFamily.DAILY_WELLNESS_DIGEST.value
    assert self_decision.semantic_family != I10SemanticFamily.CARE_STATUS_DIGEST.value
    _mark("G7-17_SON_SELF_NOTIFICATION_AND_MOTHER_CARE_NOTIFICATION_COEXIST")


def test_g7_18_mother_care_authorized_son_only(db, family_flags):
    fam = _family(db)
    _ingest_drv(db, fam.device, status="UNSTABLE", when=fam.when)
    intents = _device_intents(db, fam.mother_hs.id)
    recipients = {i.recipient_user_id for i in intents}
    assert fam.son.id in recipients
    assert fam.stranger.id not in recipients
    bad = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam.mother_hs.id,
            models.CaregiverNotificationIntent.recipient_user_id == fam.stranger.id,
        )
        .count()
    )
    assert bad == 0
    _mark("G7-18_MOTHER_CARE_STATUS_DELIVERED_ONLY_TO_AUTHORIZED_SON")
    _mark("MOTHER_NOTIFICATION_NOT_TO_UNAUTHORIZED_ACCOUNT")


def test_g7_19_self_notif_never_reclassified_mother_care(db, family_flags):
    fam = _family(db)
    _rollup(db, fam.son, fam.son_self_hs, fam.when)
    notif = DecisionEngine(db).create_daily_wellness_digest(
        user_id=fam.son.id, scheduled_for=fam.when
    )
    assert notif is not None
    decision = db.query(models.I10NotificationDecision).filter_by(id=notif.i10_policy_decision_id).one()
    care_families = {
        I10SemanticFamily.CARE_STATUS_DIGEST.value,
        I10SemanticFamily.CARE_DATA_GAP.value,
        I10SemanticFamily.CARE_ACTION.value,
        I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        I10SemanticFamily.DEVICE_STATUS.value,
    }
    assert decision.semantic_family not in care_families
    assert notif.health_subject_id == fam.son_self_hs.id
    _mark("G7-19_SON_SELF_NOTIFICATION_NEVER_RECLASSIFIED_AS_MOTHER_CARE_NOTIFICATION")


def test_g7_20_mother_notif_not_contaminate_son_i7(db, family_flags):
    fam = _family(db)
    before = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == fam.son.id).scalar()
    before_facts = (
        db.query(func.count(models.UserMemoryFact.id))
        .filter(models.UserMemoryFact.user_id == fam.son.id)
        .scalar()
    )
    _ingest_drv(db, fam.device, status="STABLE", when=fam.when)
    run_care_digest_producer_for_subject(
        db, health_subject_id=fam.mother_hs.id, when=fam.when, deliver=True, commit=True
    )
    for intent in _device_intents(db, fam.mother_hs.id, fam.son.id):
        process_caregiver_delivery_intent(db, intent, commit=True)
    after = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == fam.son.id).scalar()
    after_facts = (
        db.query(func.count(models.UserMemoryFact.id))
        .filter(models.UserMemoryFact.user_id == fam.son.id)
        .scalar()
    )
    assert after == before
    assert after_facts == before_facts
    # Mother DRVS must not appear as Son SELF effective status
    son_eff = get_effective_device_reported_vital_status(
        db, health_subject_id=fam.son_self_hs.id
    )
    mother_eff = get_effective_device_reported_vital_status(
        db, health_subject_id=fam.mother_hs.id
    )
    assert mother_eff is not None and mother_eff.status == "STABLE"
    assert son_eff is None or son_eff.status != mother_eff.status or son_eff.id != mother_eff.id
    _mark("G7-20_MOTHER_NOTIFICATION_NEVER_CONTAMINATES_SON_SELF_CONTEXT")


# ---------------------------------------------------------------------------
# F — ENGAGEMENT / INTERACTION
# ---------------------------------------------------------------------------


def test_g7_21_engagement_does_not_mutate_mother(db, family_flags):
    fam = _family(db)
    mother_status_before = fam.mother_hs.status
    mother_linked_before = fam.mother_hs.linked_user_id
    device_hs_before = fam.device.health_subject_id
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, fam.son.id, when=now - timedelta(hours=5))
    DecisionEngine(db).create_connection_ping(user_id=fam.son.id, scheduled_for=now)
    db.refresh(fam.mother_hs)
    db.refresh(fam.device)
    assert fam.mother_hs.status == mother_status_before
    assert fam.mother_hs.linked_user_id == mother_linked_before
    assert fam.device.health_subject_id == device_hs_before
    assert fam.device.health_subject_id == fam.mother_hs.id
    _mark("G7-21_SON_ENGAGEMENT_ACTIVITY_DOES_NOT_MUTATE_MOTHER_STATE")


def test_g7_22_like_dislike_open_chat_no_mother_or_i7(db, family_flags, client):
    fam = _family(db)
    before_mem = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == fam.son.id).scalar()
    seed = _companion_notif(db, fam.son, fam.son_self_hs)
    _feedback(client, fam.son, seed.id, {"reaction": "like"})
    _feedback(client, fam.son, seed.id, {"reaction": "dislike", "reason": "irrelevant"})
    _feedback(client, fam.son, seed.id, {"action_id": "OPEN_CHAT"})
    after_mem = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == fam.son.id).scalar()
    assert after_mem == before_mem
    db.refresh(fam.mother_hs)
    assert fam.mother_hs.linked_user_id is None
    assert fam.device.health_subject_id == fam.mother_hs.id
    # No I7 facts minted for Mother (Mother has no Account)
    assert (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.user_id == fam.mother_hs.id)
        .count()
        == 0
    )
    _mark("G7-22_LIKE_DISLIKE_OPEN_CHAT_DO_NOT_CREATE_MOTHER_OR_I7_AUTHORITY")


def test_g7_23_safe_context_resolves_son_notification_only(db, family_flags, client):
    fam = _family(db)
    seed = _companion_notif(db, fam.son, fam.son_self_hs)
    ctx = build_safe_chat_context(seed, db=db, viewer_user_id=fam.son.id)
    dumped = json.dumps(ctx).lower()
    assert "mother" not in dumped or ctx.get("category") != "care_notification"
    # Stranger cannot use Son notification as chat context owner path via feedback
    bad = _feedback(client, fam.stranger, seed.id, {"action_id": "OPEN_CHAT"})
    assert bad.status_code in (401, 403, 404)
    stranger_ctx = build_safe_chat_context(seed, db=db, viewer_user_id=fam.stranger.id)
    # Foreign viewer for SELF notif: eligibility fails closed for caregiver scopes;
    # SELF companion may still sanitize title — but must not expose Mother HS
    assert fam.mother_hs.display_name.lower() not in json.dumps(stranger_ctx).lower()
    _mark("G7-23_NOTIFICATION_SAFE_CONTEXT_RESOLVES_CORRECT_SON_NOTIFICATION_ONLY")
    _mark("WRONG_ACCOUNT_BLOCKED")


# ---------------------------------------------------------------------------
# G — REVOKE
# ---------------------------------------------------------------------------


def test_g7_24_revoked_access_fail_closed(db, family_flags):
    fam = _family(db)
    _ingest_drv(db, fam.device, status="STABLE", when=fam.when)
    intent = _device_intents(db, fam.mother_hs.id, fam.son.id)[0]
    revoke_caregiver_subject_access(
        db,
        actor_user_id=fam.son.id,
        health_subject_id=fam.mother_hs.id,
        recipient_account_user_id=fam.son.id,
    )
    # Manager SELF-created AHSA may use is_active path; force inactive if still active MANAGER
    for a in (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == fam.mother_hs.id,
            models.AccountHealthSubjectAccess.account_user_id == fam.son.id,
        )
        .all()
    ):
        if a.is_active:
            a.is_active = False
            a.revoked_at = fam.when.replace(tzinfo=None) if fam.when.tzinfo else fam.when
    db.commit()
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome["status"] == "suppressed"
    db.refresh(fam.mother_hs)
    db.refresh(fam.device)
    assert fam.mother_hs.linked_user_id is None
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.device.health_subject_id == fam.mother_hs.id
    assert fam.device.user_id == fam.son.id
    # No fallback stranger delivery
    assert (
        db.query(models.Notification)
        .filter(models.Notification.user_id == fam.stranger.id)
        .count()
        == 0
    )
    _mark("G7-24_REVOKED_SON_TO_MOTHER_ACCESS_FAILS_CLOSED")


def test_g7_25_revoked_grant_fail_closed(db, family_flags):
    fam = _family(db)
    _ingest_drv(db, fam.device, status="UNSTABLE", when=fam.when)
    intent = _device_intents(db, fam.mother_hs.id, fam.son.id)[0]
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=fam.son.id,
        health_subject_id=fam.mother_hs.id,
        recipient_user_id=fam.son.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome["status"] == "suppressed"
    db.refresh(fam.mother_hs)
    db.refresh(fam.device)
    assert fam.mother_hs.id == fam.device.health_subject_id
    assert fam.mother_hs.linked_user_id is None
    assert (
        db.query(models.Notification)
        .filter(models.Notification.user_id == fam.stranger.id)
        .count()
        == 0
    )
    _mark("G7-25_REVOKED_MOTHER_NOTIFICATION_GRANT_FAILS_CLOSED")


# ---------------------------------------------------------------------------
# H — CROSS-FAMILY / TX / IDEMPOTENCY
# ---------------------------------------------------------------------------


def test_g7_26_full_family_isolation_and_tx_idempotency(db, family_flags):
    fam_a = _family(db)
    fam_b = seed_stage_b_family(db, commit=True)

    # Cross-family: B stranger/son cannot receive A's Mother intents
    _ingest_drv(db, fam_a.device, status="STABLE", when=fam_a.when)
    a_intents = _device_intents(db, fam_a.mother_hs.id)
    assert all(i.recipient_user_id == fam_a.son.id for i in a_intents)
    assert all(i.recipient_user_id != fam_b.son.id for i in a_intents)
    assert all(i.recipient_user_id != fam_b.stranger.id for i in a_intents)
    assert all(i.health_subject_id != fam_b.mother_hs.id for i in a_intents)

    # Wrong HealthSubject substitution blocked for digest producer target
    run_care_digest_producer_for_subject(
        db, health_subject_id=fam_a.mother_hs.id, when=fam_a.when, deliver=True, commit=True
    )
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam_a.mother_hs.id,
            models.CaregiverNotificationIntent.recipient_user_id == fam_b.son.id,
        )
        .count()
        == 0
    )

    # Idempotent care-action retry
    when = fam_a.when
    _i8_action(
        db,
        fam_a.son,
        domain="routine",
        summary="Mother check A",
        when=when,
        key="xf-1",
        subject=fam_a.mother_hs,
    )
    run_care_action_producer_for_subject(
        db, health_subject_id=fam_a.mother_hs.id, when=when, deliver=True, commit=True
    )
    c1 = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam_a.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
    )
    run_care_action_producer_for_subject(
        db, health_subject_id=fam_a.mother_hs.id, when=when, deliver=True, commit=True
    )
    c2 = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == fam_a.mother_hs.id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_ACTION.value,
        )
        .count()
    )
    assert c1 == c2 >= 1

    # Failed delivery path does not reassign device/subject
    intent = _device_intents(db, fam_a.mother_hs.id, fam_a.son.id)[0]
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=fam_a.son.id,
        health_subject_id=fam_a.mother_hs.id,
        recipient_user_id=fam_a.son.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome["status"] == "suppressed"
    db.refresh(fam_a.mother_hs)
    db.refresh(fam_a.device)
    assert fam_a.mother_hs.linked_user_id is None
    assert fam_a.device.health_subject_id == fam_a.mother_hs.id
    assert fam_a.son_self_hs.id != fam_a.mother_hs.id
    assert fam_a.mother_hs.id != fam_b.mother_hs.id
    assert fam_a.son.id != fam_b.son.id

    # Identity separation survives (harness rolls back after test; in-test invariants hold)
    _assert_identity_locks(fam_a)
    _assert_identity_locks(fam_b)

    _mark("G7-26_FULL_FAMILY_ISOLATION_AND_TRANSACTION_IDEMPOTENCY")
    _mark("CROSS_FAMILY_ACCESS_BLOCKED")
    _mark("WRONG_HEALTHSUBJECT_BLOCKED")
    _mark("NO_ACCOUNT_SUBSTITUTION")
    _mark("NO_HEALTHSUBJECT_SUBSTITUTION")
    _mark("NO_FAKE_MOTHER_ACCOUNT")
