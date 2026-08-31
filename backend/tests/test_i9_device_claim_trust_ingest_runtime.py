"""I9 device claim, trust, gateway, and ingest runtime tests (PD-I9-V1-02)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.core.device_auth import generate_device_token, hash_device_token
from backend.app.services import auth_otp_service as svc
from backend.app.services.i9.device_binding_service import bind_device_to_subject, get_active_binding
from backend.app.services.i9.device_claim_service import (
    DeviceClaimError,
    claim_device_to_health_subject,
    provision_unclaimed_device_platform,
)
from backend.app.services.i9.device_credential_verifier import (
    PerDeviceSymmetricCredentialVerifier,
    get_device_credential_verifier,
    is_pin_or_setup_code_proof,
)
from backend.app.services.i9.device_gateway_service import (
    authorize_mobile_gateway,
    disconnect_mobile_gateway,
    list_active_gateways,
)
from backend.app.services.i9.device_lifecycle_service import release_device, revoke_device_lifecycle, transfer_device
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


@pytest.fixture
def account_user(db):
    user = models.User(name="Javad", secret_key="k-javad", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_user(db):
    user = models.User(name="Other", secret_key="k-other", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_t1_unclaimed_device_claimed_to_self_subject(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev001")
    subject = ensure_self_subject_for_account(db, account_user.id)
    binding = claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    assert binding.health_subject_id == subject.id
    assert device.claim_lifecycle_status == "claimed"
    assert device.owner_account_user_id == account_user.id


def test_t2_claim_to_managed_subject_without_account(db, account_user):
    father = create_managed_subject_without_account(
        db, account_user_id=account_user.id, display_name="Father"
    )
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev002")
    binding = claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=father.id,
        possession_proof=token,
    )
    assert binding.health_subject_id == father.id
    assert father.linked_user_id is None


def test_t3_unauthorized_account_cannot_claim_to_foreign_subject(db, account_user, other_user):
    foreign_subject = ensure_self_subject_for_account(db, other_user.id)
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev003")
    with pytest.raises(DeviceClaimError) as exc:
        claim_device_to_health_subject(
            db,
            device=device,
            account_user_id=account_user.id,
            health_subject_id=foreign_subject.id,
            possession_proof=token,
        )
    assert exc.value.code == "HEALTH_SUBJECT_ACCESS_DENIED"


def test_t4_claimed_device_cannot_be_silently_reclaimed(db, account_user, other_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev004")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    with pytest.raises(DeviceClaimError) as exc:
        claim_device_to_health_subject(
            db,
            device=device,
            account_user_id=other_user.id,
            health_subject_id=ensure_self_subject_for_account(db, other_user.id).id,
            possession_proof=token,
        )
    assert exc.value.code == "CLAIMED_DEVICE_RECLAIM_FORBIDDEN"


def test_t5_gateway_repair_changes_gateway_only(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev005")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
        gateway_install_id="gw-install-a",
    )
    before_subject = device.health_subject_id
    authorize_mobile_gateway(
        db,
        device=device,
        gateway_install_id="gw-install-b",
        account_user_id=account_user.id,
    )
    assert device.health_subject_id == before_subject
    gateways = list_active_gateways(db, device.id)
    assert len(gateways) == 2


def test_t6_disconnect_gateway_does_not_release_device(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev006")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
        gateway_install_id="gw-signout-test",
    )
    disconnect_mobile_gateway(
        db,
        device=device,
        gateway_install_id="gw-signout-test",
        account_user_id=account_user.id,
    )
    assert device.claim_lifecycle_status == "claimed"
    assert get_active_binding(db, device.id) is not None


def test_t7_release_closes_binding_preserves_history(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev007")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    measured = datetime(2026, 4, 1, 8, 0, 0, tzinfo=timezone.utc)
    ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="rel-pkt-1",
            measured_at=measured,
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 70})],
        ),
    )
    prior_binding = release_device(db, device=device, account_user_id=account_user.id)
    assert prior_binding.unbound_at is not None
    assert get_active_binding(db, device.id) is None
    pm = db.query(models.PhysiologicalMeasurement).filter(
        models.PhysiologicalMeasurement.health_subject_id == subject.id
    ).one()
    assert pm.health_subject_id == subject.id


def test_t8_transfer_creates_new_binding_old_data_stays(db, account_user):
    father = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Father")
    mother = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Mother")
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev008")
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=father.id,
        possession_proof=token,
    )
    r1 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="xfer-father",
            measured_at=datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 68})],
        ),
    )
    transfer_device(
        db,
        device=device,
        account_user_id=account_user.id,
        new_health_subject_id=mother.id,
        possession_proof=token,
    )
    r2 = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="xfer-mother",
            measured_at=datetime(2026, 4, 2, 9, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 72})],
        ),
    )
    pm_father = db.query(models.PhysiologicalMeasurement).get(r1.physiological_measurement_ids[0])
    pm_mother = db.query(models.PhysiologicalMeasurement).get(r2.physiological_measurement_ids[0])
    assert pm_father.health_subject_id == father.id
    assert pm_mother.health_subject_id == mother.id


def test_t9_revoked_device_cannot_ingest(client, db, account_user, monkeypatch):
    os.environ["DEVICE_AUTH_MODE"] = "db_only"
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev009")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    revoke_device_lifecycle(db, device=device, account_user_id=account_user.id)
    pkt = client.post(
        "/device/packet",
        headers={"X-DEVICE-TOKEN": token},
        json={
            "client_packet_id": "revoked-pkt",
            "measured_at": "2026-04-01T10:00:00Z",
            "observations": [{"observation_type": "heart_rate", "payload": {"bpm": 70}}],
        },
    )
    assert pkt.status_code == 200
    body = pkt.json()
    assert body["ok"] is False
    assert body["data"]["ack_status"] == "REJECTED_REVOKED"


def test_t10_credential_rotation_preserves_subject_history(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev010")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="rot-pkt-1",
            measured_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 65})],
        ),
    )
    old_subject = device.health_subject_id
    new_token = generate_device_token()
    device.token_hash = hash_device_token(new_token)
    db.commit()
    ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="rot-pkt-2",
            measured_at=datetime(2026, 4, 1, 11, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 66})],
        ),
    )
    assert device.health_subject_id == old_subject


def test_t11_pin_not_runtime_auth(db, account_user):
    device, _token = provision_unclaimed_device_platform(db, device_id="ClaimDev011")
    verifier = PerDeviceSymmetricCredentialVerifier()
    result = verifier.verify(device, "123456")
    assert result.verified is False
    assert result.reject_reason == "PIN_NOT_RUNTIME_AUTH"
    assert is_pin_or_setup_code_proof("pin:1234") is True


def test_t12_no_shared_fleet_secret_in_packet_path(monkeypatch):
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    monkeypatch.setenv("DEVICE_AUTH_MODE", "db_only")
    verifier = get_device_credential_verifier()
    assert verifier.__class__.__name__ == "PerDeviceSymmetricCredentialVerifier"


def test_t13_multi_subject_one_gateway_attribution(db, account_user):
    self_subj = ensure_self_subject_for_account(db, account_user.id)
    father = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Father")
    mother = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Mother")

    devices = []
    for label, subject in (("A", self_subj), ("B", father), ("C", mother)):
        dev, tok = provision_unclaimed_device_platform(db, device_id=f"MultiGw{label}")
        claim_device_to_health_subject(
            db,
            device=dev,
            account_user_id=account_user.id,
            health_subject_id=subject.id,
            possession_proof=tok,
            gateway_install_id="shared-mobile-gw",
        )
        devices.append((dev, subject))

    for dev, subject in devices:
        result = ingest_device_packet(
            db,
            device=dev,
            packet_in=DevicePacketIngestInput(
                client_packet_id=f"pkt-{dev.device_id}",
                measured_at=datetime(2026, 4, 3, 10, 0, 0, tzinfo=timezone.utc),
                transport="bluetooth_relay",
                observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 70})],
            ),
        )
        assert result.health_subject_id == subject.id


def test_t14_packet_retry_idempotent(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev014")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    packet_in = DevicePacketIngestInput(
        client_packet_id="idem-pkt-1",
        measured_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
        observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 71})],
    )
    r1 = ingest_device_packet(db, device=device, packet_in=packet_in)
    r2 = ingest_device_packet(db, device=device, packet_in=packet_in)
    assert r1.dedupe_hit is False
    assert r2.dedupe_hit is True


def test_t15_distinct_packets_within_five_minutes(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev015")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    base = datetime(2026, 4, 1, 10, 1, 0, tzinfo=timezone.utc)
    for i, pkt_id in enumerate(("p-a", "p-b")):
        ingest_device_packet(
            db,
            device=device,
            packet_in=DevicePacketIngestInput(
                client_packet_id=pkt_id,
                measured_at=base + timedelta(minutes=i),
                observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 60 + i})],
            ),
        )
    assert db.query(models.DevicePacket).filter(models.DevicePacket.device_row_id == device.id).count() == 2


def test_t16_delayed_packet_preserves_measured_at(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev016")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    measured = datetime(2026, 3, 28, 6, 15, 0, tzinfo=timezone.utc)
    result = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="delay-1",
            measured_at=measured,
            gateway_received_at=datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 66})],
        ),
    )
    packet = db.query(models.DevicePacket).get(result.packet.id)
    assert packet.measured_at.replace(tzinfo=timezone.utc) == measured


def test_t17_ack_duplicate_no_duplicate_children(client, db, account_user, monkeypatch):
    os.environ["DEVICE_AUTH_MODE"] = "db_only"
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev017")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    payload = {
        "client_packet_id": "ack-dup-1",
        "measured_at": "2026-04-01T10:00:00Z",
        "observations": [{"observation_type": "heart_rate", "payload": {"bpm": 70}}],
    }
    r1 = client.post("/device/packet", headers={"X-DEVICE-TOKEN": token}, json=payload)
    r2 = client.post("/device/packet", headers={"X-DEVICE-TOKEN": token}, json=payload)
    assert r1.json()["data"]["ack_status"] == "ACCEPTED"
    assert r2.json()["data"]["ack_status"] == "DUPLICATE"
    assert db.query(models.PhysiologicalMeasurement).filter(
        models.PhysiologicalMeasurement.health_subject_id == subject.id,
        models.PhysiologicalMeasurement.numeric_value == 70.0,
    ).count() == 1


def test_t18_device_reported_cardiac_provenance(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev018")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    detected = datetime(2026, 4, 1, 11, 0, 0, tzinfo=timezone.utc)
    result = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="cardiac-1",
            measured_at=detected,
            firmware_version="fw-2.0",
            algorithm_version="algo-3.0",
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
    assert "DEVICE" in (event.provenance_json or "")


def test_t19_device_operational_auth_compatible(client, db, monkeypatch):
    os.environ["DEVICE_AUTH_MODE"] = "db_only"
    phone = "+989190020019"
    auth = _token(client, db, monkeypatch, phone)
    reg = client.post(
        "/devices/register",
        json={"device_id": "LegacyAuth019"},
        headers={"Authorization": f"Bearer {auth}"},
    )
    assert reg.status_code == 200
    dev_token = reg.json()["data"]["token"]
    hb = client.post(
        "/device/heartbeat",
        headers={"X-DEVICE-TOKEN": dev_token},
        json={"device_id": "LegacyAuth019", "battery_level": 90},
    )
    assert hb.status_code == 200


def test_t20_i5_rag_boundary_unchanged(db, account_user):
    device, token = provision_unclaimed_device_platform(db, device_id="ClaimDev020")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=token,
    )
    ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="rag-1",
            measured_at=datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc),
            observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 68})],
        ),
    )
    for ev in db.query(models.DeviceEvent).all():
        assert ev.embedding_id is None


def test_t21_single_alembic_head():
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory("backend/alembic").get_heads()
    assert heads == ["075_i10_care_network_identity_grants"]
