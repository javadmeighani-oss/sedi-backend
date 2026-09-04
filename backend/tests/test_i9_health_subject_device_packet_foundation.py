"""I9 Health Subject / Device Packet foundation tests (PD-I9-V1-01)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import inspect

from backend.app import models
from backend.app.core.device_auth import generate_device_token, hash_device_token
from backend.app.services import auth_otp_service as svc
from backend.app.services.i9.device_binding_service import bind_device_to_subject, rebind_device
from backend.app.services.i9.device_packet_service import DevicePacketIngestInput, PacketObservationIn, ingest_device_packet
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _register_device(client, headers, device_id: str, **extra):
    body = {"device_id": device_id, **extra}
    return client.post("/devices/register", json=body, headers=headers)


@pytest.fixture
def account_user(db):
    user = models.User(name="Account Holder", secret_key="k1", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_t1_account_owns_self_health_subject(db, account_user):
    subject = ensure_self_subject_for_account(db, account_user.id)
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user.id,
            models.AccountHealthSubjectAccess.health_subject_id == subject.id,
        )
        .one()
    )
    assert access.access_role == "SELF"
    assert subject.linked_user_id == account_user.id
    assert subject.subject_kind == "self"


def test_t2_managed_subject_without_account(db, account_user):
    subject = create_managed_subject_without_account(
        db,
        account_user_id=account_user.id,
        display_name="Father (no account)",
        access_role="CAREGIVER",
    )
    assert subject.linked_user_id is None
    assert subject.subject_kind == "managed"
    row = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(models.AccountHealthSubjectAccess.health_subject_id == subject.id)
        .one()
    )
    assert row.account_user_id == account_user.id
    assert row.access_role == "CAREGIVER"


def test_t3_device_binds_to_self_subject(db, account_user):
    subject = ensure_self_subject_for_account(db, account_user.id)
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevSelf001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-self"),
    )
    db.add(device)
    db.flush()
    binding = bind_device_to_subject(
        db,
        device=device,
        health_subject_id=subject.id,
        bound_by_account_user_id=account_user.id,
    )
    assert binding.health_subject_id == subject.id
    assert device.health_subject_id == subject.id


def test_t4_device_bound_to_other_subject_while_account_relays(db, account_user):
    father = create_managed_subject_without_account(
        db,
        account_user_id=account_user.id,
        display_name="Father",
    )
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevFather001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-father"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=father.id, bound_by_account_user_id=account_user.id)
    assert device.health_subject_id == father.id
    assert device.user_id == account_user.id


def test_t5_server_attribution_uses_binding_not_account(db, account_user):
    father = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Father")
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevAttr001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-attr"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=father.id, bound_by_account_user_id=account_user.id)

    measured = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="pkt-attr-001",
            measured_at=measured,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 72})],
        ),
    )
    assert result.dedupe_hit is False
    assert result.health_subject_id == father.id
    pm = db.query(models.PhysiologicalMeasurement).filter(models.PhysiologicalMeasurement.id.in_(result.physiological_measurement_ids)).one()
    assert pm.health_subject_id == father.id
    assert pm.user_id is None


def test_t6_rebind_does_not_move_old_observation_ownership(db, account_user):
    father = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Father")
    mother = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Mother")
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevRebind001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-rebind"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=father.id, bound_by_account_user_id=account_user.id)

    t1 = datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
    r1 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="pkt-father-1",
            measured_at=t1,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 70})],
        ),
    )

    rebind_device(
        db,
        device=device,
        new_health_subject_id=mother.id,
        bound_by_account_user_id=account_user.id,
        bound_at=datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc),
    )

    t2 = datetime(2026, 3, 2, 8, 0, 0, tzinfo=timezone.utc)
    r2 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="pkt-mother-1",
            measured_at=t2,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 75})],
        ),
    )

    pm_father = db.query(models.PhysiologicalMeasurement).get(r1.physiological_measurement_ids[0])
    pm_mother = db.query(models.PhysiologicalMeasurement).get(r2.physiological_measurement_ids[0])
    assert pm_father.health_subject_id == father.id
    assert pm_mother.health_subject_id == mother.id


def test_t7_packet_retry_idempotent(db, account_user):
    subject = ensure_self_subject_for_account(db, account_user.id)
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevRetry001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-retry"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=subject.id, bound_by_account_user_id=account_user.id)

    packet_in = DevicePacketIngestInput(
        client_packet_id="pkt-retry-001",
        measured_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 80})],
    )
    r1 = ingest_device_packet(db, device=device, packet_in=packet_in)
    r2 = ingest_device_packet(db, device=device, packet_in=packet_in)
    assert r1.dedupe_hit is False
    assert r2.dedupe_hit is True
    count = db.query(models.DevicePacket).filter(models.DevicePacket.client_packet_id == "pkt-retry-001").count()
    assert count == 1
    pm_count = db.query(models.PhysiologicalMeasurement).filter(
        models.PhysiologicalMeasurement.health_subject_id == subject.id,
        models.PhysiologicalMeasurement.numeric_value == 80.0,
    ).count()
    assert pm_count == 1


def test_t8_distinct_packets_within_five_minutes(db, account_user):
    subject = ensure_self_subject_for_account(db, account_user.id)
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevDistinct001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-distinct"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=subject.id, bound_by_account_user_id=account_user.id)

    base = datetime(2026, 3, 1, 10, 1, 0, tzinfo=timezone.utc)
    for i, pkt_id in enumerate(("pkt-a", "pkt-b", "pkt-c")):
        ingest_device_packet(
            db,
            device=device,
            packet_in=DevicePacketIngestInput(
                client_packet_id=pkt_id,
                measured_at=base + timedelta(minutes=i),
                observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 60 + i})],
            ),
        )
    assert db.query(models.DevicePacket).filter(models.DevicePacket.device_row_id == device.id).count() == 3


def test_t9_measured_at_preserved_on_delayed_ingest(db, account_user):
    subject = ensure_self_subject_for_account(db, account_user.id)
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevDelay001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-delay"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=subject.id, bound_by_account_user_id=account_user.id)

    measured = datetime(2026, 2, 28, 6, 15, 0, tzinfo=timezone.utc)
    result = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="pkt-delay-1",
            measured_at=measured,
            gateway_received_at=datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 66})],
        ),
    )
    packet = db.query(models.DevicePacket).get(result.packet.id)
    pm = db.query(models.PhysiologicalMeasurement).get(result.physiological_measurement_ids[0])
    assert packet.measured_at.replace(tzinfo=timezone.utc) == measured
    assert pm.measured_at.replace(tzinfo=timezone.utc) == measured


def test_t10_device_reported_cardiac_event_provenance(db, account_user):
    subject = ensure_self_subject_for_account(db, account_user.id)
    device = models.Device(
        user_id=account_user.id,
        device_id="I9DevCardiac001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-cardiac"),
        firmware_version="fw-1.2.3",
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=subject.id, bound_by_account_user_id=account_user.id)

    detected = datetime(2026, 3, 1, 11, 0, 0, tzinfo=timezone.utc)
    result = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="pkt-cardiac-1",
            measured_at=detected,
            firmware_version="fw-1.2.3",
            algorithm_version="algo-2.0",
            observations=[
                PacketObservationIn(
                    observation_type="device_reported_cardiac_event",
                    payload={"event_code": "arrhythmia_indicator", "value": 1},
                    detected_at=detected,
                )
            ],
        ),
    )
    event = db.query(models.DeviceReportedCardiacEvent).get(result.cardiac_event_ids[0])
    assert event.source_class == "DEVICE_REPORTED"
    assert event.event_code == "arrhythmia_indicator"
    assert event.algorithm_version == "algo-2.0"
    assert event.firmware_version == "fw-1.2.3"
    assert "DEVICE" in (event.provenance_json or "")


def test_t11_multi_vital_schema_foundation(db):
    """ORM + CHECK vocabulary includes future vitals beyond heart_rate."""
    pm_table = models.PhysiologicalMeasurement.__table__
    check = [c for c in pm_table.constraints if getattr(c, "name", None) == "ck_pm_measurement_type_vocab"][0]
    sql = str(check.sqltext)
    for vital in ("heart_rate", "blood_pressure", "glucose", "temperature", "spo2"):
        assert vital in sql

    rollup_table = models.PhysiologicalMeasurementRollup.__table__
    bucket_check = [c for c in rollup_table.constraints if getattr(c, "name", None) == "ck_pmr_bucket_kind_vocab"][0]
    bucket_sql = str(bucket_check.sqltext)
    for kind in ("daily", "weekly", "calendar_month", "yearly"):
        assert kind in bucket_sql


def test_t12_device_token_auth_still_works(client, db, monkeypatch):
    os.environ["DEVICE_AUTH_MODE"] = "db_only"
    phone = "+989190010012"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    reg = _register_device(client, headers, "I9AuthDev001")
    assert reg.status_code == 200
    assert reg.json()["ok"] is True
    dev_token = reg.json()["data"]["token"]
    pkt = client.post(
        "/device/packet",
        headers={"X-DEVICE-TOKEN": dev_token},
        json={
            "client_packet_id": "auth-pkt-1",
            "measured_at": "2026-03-01T10:00:00Z",
            "observations": [{"observation_type": "heart_rate", "payload": {"bpm": 71}}],
        },
    )
    assert pkt.status_code == 200
    assert pkt.json()["ok"] is True


def test_t13_i5_rag_boundary_unchanged(db, account_user):
    """Device events remain RAG-ready but inactive; no embedding write path."""
    subject = ensure_self_subject_for_account(db, account_user.id)
    device = models.Device(
        user_id=account_user.id,
        device_id="I9RagBound001",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token("tok-rag"),
    )
    db.add(device)
    db.flush()
    bind_device_to_subject(db, device=device, health_subject_id=subject.id, bound_by_account_user_id=account_user.id)
    ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="pkt-rag-1",
            measured_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 68})],
        ),
    )
    events = db.query(models.DeviceEvent).all()
    for ev in events:
        assert ev.embedding_id is None


def test_t14_single_alembic_head():
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory("backend/alembic").get_heads()
    assert heads == ["078_health_subject_condition_foundation"]


def test_managed_subject_api(client, db, monkeypatch):
    phone = "+989190010013"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/health-subjects/managed", json={"display_name": "Mother"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["data"]["subject_kind"] == "managed"
    assert r.json()["data"]["linked_user_id"] is None
