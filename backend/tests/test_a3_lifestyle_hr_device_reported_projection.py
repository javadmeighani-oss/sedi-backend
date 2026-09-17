"""Lifestyle health-hr DEVICE_REPORTED status projection — no MAD relabeling."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app.core.security import create_access_token
from backend.app.models import (
    Device,
    DevicePacket,
    DeviceReportedVitalStatus,
    PhysiologicalMeasurement,
    User,
    UserProfileCore,
)
from backend.app.services.i10.self_producer_adapter import (
    resolve_or_ensure_self_health_subject_id,
)
from backend.app.services.lifestyle.a3_health_hr_projection import (
    build_lifestyle_hr_projection,
)


def _auth(uid: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _user(db, phone: str) -> User:
    u = User(name="HrDrvs", secret_key="t", preferred_language="en", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(UserProfileCore(user_id=u.id, timezone="UTC"))
    db.commit()
    return u


def _device(db, user: User, key: str) -> Device:
    device = Device(
        user_id=user.id,
        device_id=f"drvs-{key}",
        device_type="heart_rate",
        status="active",
        token_hash=f"th-drvs-{key}",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _add_bpm(db, user: User, device: Device, value: float, key: str) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        PhysiologicalMeasurement(
            user_id=user.id,
            device_id=device.id,
            measurement_type="heart_rate",
            numeric_value=value,
            unit="bpm",
            measured_at=now,
            received_at=now,
            idempotency_key=f"bpm-{key}",
            ingestion_status="accepted",
        )
    )
    db.commit()


def _add_drvs(
    db,
    *,
    user: User,
    device: Device,
    status: str,
    when: datetime,
    packet_key: str,
    health_subject_id: int | None = None,
) -> DeviceReportedVitalStatus:
    hs_id = health_subject_id or resolve_or_ensure_self_health_subject_id(db, user.id)
    packet = DevicePacket(
        device_row_id=device.id,
        device_logical_id=device.device_id,
        health_subject_id=int(hs_id),
        client_packet_id=f"pkt-{packet_key}",
        measured_at=when,
        server_received_at=when,
        ingestion_status="accepted",
        provenance_json="{}",
    )
    db.add(packet)
    db.flush()
    row = DeviceReportedVitalStatus(
        device_packet_id=packet.id,
        health_subject_id=int(hs_id),
        status=status,
        source_class="DEVICE_REPORTED",
        detected_at=when,
        server_received_at=when,
        provenance_json='{"class":"DEVICE_REPORTED"}',
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_device_reported_stable_projection(client, db):
    u = _user(db, "+19990001001")
    device = _device(db, u, "s1")
    _add_bpm(db, u, device, 74.0, "s1")
    when = datetime.now(timezone.utc)
    _add_drvs(db, user=u, device=device, status="STABLE", when=when, packet_key="s1")

    r = client.get("/lifestyle/health-hr?range_key=7d", headers=_auth(u.id))
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["latest_value"] == 74.0
    assert data["hr_status"] == "STABLE"
    assert data["hr_status_source"] == "DEVICE_REPORTED"
    assert data["hr_status_observed_at"] is not None
    assert data["hr_stability_compact"] in (
        "STABLE",
        "UNSTABLE_OR_CHANGED",
        "INSUFFICIENT_DATA",
    )


def test_device_reported_unstable_projection(client, db):
    u = _user(db, "+19990001002")
    device = _device(db, u, "u1")
    when = datetime.now(timezone.utc)
    _add_drvs(db, user=u, device=device, status="UNSTABLE", when=when, packet_key="u1")
    data = build_lifestyle_hr_projection(db, u.id, range_key="7d")
    assert data["hr_status"] == "UNSTABLE"
    assert data["hr_status_source"] == "DEVICE_REPORTED"


def test_unknown_fail_closed_no_device_status(client, db):
    u = _user(db, "+19990001003")
    device = _device(db, u, "n1")
    _add_bpm(db, u, device, 80.0, "n1")
    data = build_lifestyle_hr_projection(db, u.id)
    assert data["latest_value"] == 80.0
    assert data["hr_status"] is None
    assert data["hr_status_source"] is None
    assert data["hr_status_observed_at"] is None
    assert data["hr_stability_compact"] != "DEVICE_REPORTED"


def test_mad_compact_never_becomes_device_reported(client, db):
    u = _user(db, "+19990001004")
    device = _device(db, u, "m1")
    _add_bpm(db, u, device, 90.0, "m1")
    # Ensure SELF subject exists so MAD compact may evaluate; still no DRVS.
    resolve_or_ensure_self_health_subject_id(db, u.id)
    data = build_lifestyle_hr_projection(db, u.id)
    assert data["hr_status_source"] is None
    assert data["hr_status"] is None
    assert data["hr_stability_compact"] in (
        "STABLE",
        "UNSTABLE_OR_CHANGED",
        "INSUFFICIENT_DATA",
    )


def test_newer_status_wins_latest_selection(client, db):
    u = _user(db, "+19990001005")
    device = _device(db, u, "ord")
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    t1 = datetime.now(timezone.utc)
    _add_drvs(db, user=u, device=device, status="STABLE", when=t0, packet_key="old")
    _add_drvs(db, user=u, device=device, status="UNSTABLE", when=t1, packet_key="new")
    data = build_lifestyle_hr_projection(db, u.id)
    assert data["hr_status"] == "UNSTABLE"
    assert data["hr_status_source"] == "DEVICE_REPORTED"


def test_out_of_order_older_packet_does_not_override(client, db):
    u = _user(db, "+19990001006")
    device = _device(db, u, "ooo")
    t_new = datetime.now(timezone.utc)
    t_old = t_new - timedelta(hours=3)
    _add_drvs(db, user=u, device=device, status="UNSTABLE", when=t_new, packet_key="new2")
    _add_drvs(db, user=u, device=device, status="STABLE", when=t_old, packet_key="old2")
    data = build_lifestyle_hr_projection(db, u.id)
    assert data["hr_status"] == "UNSTABLE"


def test_cross_account_status_isolation(client, db):
    a = _user(db, "+19990001007")
    b = _user(db, "+19990001008")
    da = _device(db, a, "iso-a")
    db_dev = _device(db, b, "iso-b")
    when = datetime.now(timezone.utc)
    _add_drvs(db, user=a, device=da, status="UNSTABLE", when=when, packet_key="iso-a")
    _add_bpm(db, a, da, 99.0, "iso-a")
    ra = client.get("/lifestyle/health-hr", headers=_auth(a.id)).json()["data"]
    rb = client.get("/lifestyle/health-hr", headers=_auth(b.id)).json()["data"]
    assert ra["hr_status"] == "UNSTABLE"
    assert ra["latest_value"] == 99.0
    assert rb["hr_status"] is None
    assert rb["latest_value"] is None
    assert rb["hr_status_source"] is None
    # unused device for b keeps fixture honest
    assert db_dev.id is not None


def test_history_and_bpm_unchanged_with_status(client, db):
    u = _user(db, "+19990001009")
    device = _device(db, u, "hist")
    _add_bpm(db, u, device, 66.0, "hist")
    _add_drvs(
        db,
        user=u,
        device=device,
        status="STABLE",
        when=datetime.now(timezone.utc),
        packet_key="hist",
    )
    data = build_lifestyle_hr_projection(db, u.id, range_key="30d")
    assert data["latest_value"] == 66.0
    assert data["range_key"] == "30d"
    assert isinstance(data["history"], list)
    assert "history_bucket_kind" in data
