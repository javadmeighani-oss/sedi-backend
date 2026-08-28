"""Trusted fleet provisioning + claim hardening tests (PD-I9-V1-03)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services import auth_otp_service as svc
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
from backend.app.services.i9.device_gateway_service import authorize_mobile_gateway, disconnect_mobile_gateway
from backend.app.services.i9.device_lifecycle_service import release_device, transfer_device
from backend.app.services.i9.device_packet_service import DevicePacketIngestInput, PacketObservationIn, ingest_device_packet
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)

_TEST_ADMIN_TOKEN = "test-fleet-provision-admin"


def _user_token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _admin_headers(monkeypatch, token: str = _TEST_ADMIN_TOKEN) -> dict[str, str]:
    monkeypatch.setenv("ADMIN_TOKEN", token)
    return {"X-Admin-Token": token}


@pytest.fixture
def account_user(db):
    user = models.User(name="FleetUser", secret_key="k-fleet", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_user(db):
    user = models.User(name="FleetOther", secret_key="k-other", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_f1_ordinary_user_cannot_provision_when_admin_disabled(client, db, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    token = _user_token(client, db, monkeypatch, "+989190030001")
    response = client.post(
        "/devices/provision",
        json={"device_id": "SquatDev001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json().get("detail") == "admin_disabled"
    assert db.query(models.Device).filter(models.Device.device_id == "SquatDev001").count() == 0


def test_f2_ordinary_user_cannot_create_device_id_via_provision(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    token = _user_token(client, db, monkeypatch, "+989190030002")
    response = client.post(
        "/devices/provision",
        json={"device_id": "SquatDev002"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert db.query(models.Device).filter(models.Device.device_id == "SquatDev002").count() == 0


def test_f3_ordinary_user_cannot_obtain_factory_credential(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", _TEST_ADMIN_TOKEN)
    token = _user_token(client, db, monkeypatch, "+989190030003")
    response = client.post(
        "/devices/provision",
        json={"device_id": "SquatDev003"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    payload = response.json()
    assert "token" not in str(payload.get("data") or "")


def test_f3b_trusted_admin_can_provision_and_receive_credential(client, db, monkeypatch):
    response = client.post(
        "/devices/provision",
        json={"device_id": "FleetDev001"},
        headers=_admin_headers(monkeypatch),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["token"]
    assert body["data"]["claim_lifecycle_status"] == "unclaimed"


def test_f4_unknown_device_cannot_be_claimed(client, db, monkeypatch, account_user):
    token = _user_token(client, db, monkeypatch, "+989190030004")
    subject = ensure_self_subject_for_account(db, account_user.id)
    response = client.post(
        "/devices/claim",
        json={
            "device_id": "NeverProvisioned001",
            "health_subject_id": subject.id,
            "possession_proof": "any-proof",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "DEVICE_NOT_REGISTERED"


def test_f5_claim_never_auto_provisions_unknown_device(client, db, monkeypatch, account_user):
    token = _user_token(client, db, monkeypatch, "+989190030005")
    subject = ensure_self_subject_for_account(db, account_user.id)
    client.post(
        "/devices/claim",
        json={
            "device_id": "AutoProvForbidden001",
            "health_subject_id": subject.id,
            "possession_proof": "factory-token",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert db.query(models.Device).filter(models.Device.device_id == "AutoProvForbidden001").count() == 0


def test_f6_preprovisioned_unclaimed_device_can_be_claimed(client, db, monkeypatch, account_user):
    admin = client.post(
        "/devices/provision",
        json={"device_id": "FleetClaim001"},
        headers=_admin_headers(monkeypatch),
    )
    factory_token = admin.json()["data"]["token"]
    user_token = _user_token(client, db, monkeypatch, "+989190030006")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim = client.post(
        "/devices/claim",
        json={
            "device_id": "FleetClaim001",
            "health_subject_id": subject.id,
            "possession_proof": factory_token,
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert claim.status_code == 200
    assert claim.json()["ok"] is True
    assert claim.json()["data"]["claim_lifecycle_status"] == "claimed"


def test_f7_managed_subject_without_account_claim(client, db, monkeypatch, account_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetManaged001")
    father = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Father")
    binding = claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=father.id,
        possession_proof=factory_token,
    )
    assert binding.health_subject_id == father.id
    assert father.linked_user_id is None


def test_f8_unauthorized_health_subject_claim_fails(db, account_user, other_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetAuth001")
    foreign_subject = ensure_self_subject_for_account(db, other_user.id)
    with pytest.raises(DeviceClaimError) as exc:
        claim_device_to_health_subject(
            db,
            device=device,
            account_user_id=account_user.id,
            health_subject_id=foreign_subject.id,
            possession_proof=factory_token,
        )
    assert exc.value.code == "HEALTH_SUBJECT_ACCESS_DENIED"


def test_f9_already_claimed_device_cannot_be_reclaimed(db, account_user, other_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetReclaim001")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=factory_token,
    )
    with pytest.raises(DeviceClaimError) as exc:
        claim_device_to_health_subject(
            db,
            device=device,
            account_user_id=other_user.id,
            health_subject_id=ensure_self_subject_for_account(db, other_user.id).id,
            possession_proof=factory_token,
        )
    assert exc.value.code == "CLAIMED_DEVICE_RECLAIM_FORBIDDEN"


def test_f10_gateway_pair_does_not_change_subject_binding(db, account_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetGw001")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=factory_token,
        gateway_install_id="gw-a",
    )
    before = device.health_subject_id
    authorize_mobile_gateway(
        db,
        device=device,
        gateway_install_id="gw-b",
        account_user_id=account_user.id,
    )
    assert device.health_subject_id == before


def test_f11_release_transfer_still_work(db, account_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetLife001")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=factory_token,
    )
    release_device(db, device=device, account_user_id=account_user.id)
    assert device.claim_lifecycle_status == "released"
    mother = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Mother")
    transfer_device(
        db,
        device=device,
        account_user_id=account_user.id,
        new_health_subject_id=mother.id,
        possession_proof=factory_token,
    )
    assert device.health_subject_id == mother.id


def test_f12_pin_still_rejected_as_runtime_credential(db):
    device, _ = provision_unclaimed_device_platform(db, device_id="FleetPin001")
    result = PerDeviceSymmetricCredentialVerifier().verify(device, "123456")
    assert result.verified is False
    assert result.reject_reason == "PIN_NOT_RUNTIME_AUTH"
    assert is_pin_or_setup_code_proof("setup:9999") is True


def test_f13_per_device_credential_no_fleet_secret(monkeypatch):
    monkeypatch.delenv("DEVICE_INGEST_TOKEN", raising=False)
    assert get_device_credential_verifier().__class__.__name__ == "PerDeviceSymmetricCredentialVerifier"


def test_f14_packet_idempotency_regression(db, account_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetPkt001")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=factory_token,
    )
    packet_in = DevicePacketIngestInput(
        client_packet_id="fleet-idem-1",
        measured_at=datetime(2026, 4, 5, 10, 0, 0, tzinfo=timezone.utc),
        observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 70})],
    )
    r1 = ingest_device_packet(db, device=device, packet_in=packet_in)
    r2 = ingest_device_packet(db, device=device, packet_in=packet_in)
    assert r1.dedupe_hit is False
    assert r2.dedupe_hit is True


def test_f15_cardiac_provenance_regression(db, account_user):
    device, factory_token = provision_unclaimed_device_platform(db, device_id="FleetCardiac001")
    subject = ensure_self_subject_for_account(db, account_user.id)
    claim_device_to_health_subject(
        db,
        device=device,
        account_user_id=account_user.id,
        health_subject_id=subject.id,
        possession_proof=factory_token,
    )
    detected = datetime(2026, 4, 5, 11, 0, 0, tzinfo=timezone.utc)
    result = ingest_device_packet(
        db,
        device=device,
        packet_in=DevicePacketIngestInput(
            client_packet_id="fleet-cardiac-1",
            measured_at=detected,
            firmware_version="fw-2.0",
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


def test_f16_multi_subject_one_gateway_attribution(db, account_user):
    self_subj = ensure_self_subject_for_account(db, account_user.id)
    father = create_managed_subject_without_account(db, account_user_id=account_user.id, display_name="Father")
    for label, subject in (("A", self_subj), ("B", father)):
        dev, tok = provision_unclaimed_device_platform(db, device_id=f"FleetMulti{label}")
        claim_device_to_health_subject(
            db,
            device=dev,
            account_user_id=account_user.id,
            health_subject_id=subject.id,
            possession_proof=tok,
            gateway_install_id="shared-gw",
        )
        result = ingest_device_packet(
            db,
            device=dev,
            packet_in=DevicePacketIngestInput(
                client_packet_id=f"pkt-{label}",
                measured_at=datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc),
                observations=[PacketObservationIn(observation_type="heart_rate", payload={"bpm": 70})],
            ),
        )
        assert result.health_subject_id == subject.id
    disconnect_mobile_gateway(
        db,
        device=db.query(models.Device).filter(models.Device.device_id == "FleetMultiA").one(),
        gateway_install_id="shared-gw",
        account_user_id=account_user.id,
    )


def test_f17_single_alembic_head():
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory("backend/alembic").get_heads()
    assert heads == ["072_i9_device_claim_gateway_lifecycle_foundation"]
