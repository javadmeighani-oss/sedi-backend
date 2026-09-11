"""SEDI-V1-I9-HR-STABILITY-TO-I10-MINIMAL-CLOSURE-01 — targeted PG16 tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.core.device_auth import hash_device_token
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.device_reported_vital_status_producer import (
    emit_device_reported_vital_status_notifications,
)
from backend.app.services.i10.hr_stability_producer import emit_hr_stability_i10_for_subject
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.device_reported_vital_status import (
    get_effective_device_reported_vital_status,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.hr_stability import (
    CanonicalHrStabilityStatus,
    evaluate_canonical_hr_stability,
)
from backend.app.services.i9.time_buckets import bucket_bounds

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_FLAG_PATCH = patch.dict(
    "os.environ",
    {"SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true"},
    clear=False,
)
_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)


@pytest.fixture
def patches():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _device(db, owner: models.User, device_id: str) -> models.Device:
    dev = models.Device(
        user_id=owner.id,
        device_id=device_id,
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token(f"tok-{device_id}"),
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _push_prefs(db, user_id: int) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=f"fcm-{user_id}", is_active=True))
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=True,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _when(day: str = "2026-08-31", hour: int = 12) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")


def _period_start(when: datetime) -> datetime:
    d = when.date()
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _pm(db, *, subject, device, value, measured_at, key):
    row = models.PhysiologicalMeasurement(
        health_subject_id=subject.id,
        user_id=subject.linked_user_id,
        device_id=device.id,
        measurement_type="heart_rate",
        numeric_value=value,
        unit="bpm",
        measured_at=measured_at,
        received_at=datetime.now(timezone.utc),
        idempotency_key=key,
        ingestion_status="accepted",
    )
    db.add(row)
    db.commit()
    return row


def _established_baseline(db, subject, when, *, baseline_value: float, dispersion_value: float):
    start = _period_start(when) - timedelta(days=27)
    end = _period_start(when)
    row = models.PhysiologicalBaseline(
        user_id=subject.linked_user_id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        baseline_method="PERSONAL_OBSERVED_BASELINE_V1",
        baseline_value=baseline_value,
        dispersion_value=dispersion_value,
        window_start=start,
        window_end=end,
        derived_at=when,
        coverage=0.8,
        valid_day_count=14,
        quality="ESTABLISHED",
        baseline_version=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_day_hr(db, subject, device, when, values, *, prefix: str):
    d_start, _ = bucket_bounds("daily", ref=when)
    for i, v in enumerate(values):
        _pm(
            db,
            subject=subject,
            device=device,
            value=v,
            measured_at=d_start + timedelta(hours=8, minutes=i),
            key=f"{prefix}-{subject.id}-{i}-{v}",
        )


def _grant_both(db, actor_id, hs_id, recipient_id):
    create_subject_notification_grant(
        db,
        actor_user_id=actor_id,
        health_subject_id=hs_id,
        recipient_user_id=recipient_id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=actor_id,
        health_subject_id=hs_id,
        recipient_user_id=recipient_id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )


def _intents(db, hs_id, *, family: str | None = None, recipient_id: int | None = None):
    q = db.query(models.CaregiverNotificationIntent).filter(
        models.CaregiverNotificationIntent.health_subject_id == hs_id,
        models.CaregiverNotificationIntent.source_entity_type == "I10_HR_STABILITY",
    )
    if family:
        q = q.filter(models.CaregiverNotificationIntent.semantic_family == family)
    if recipient_id is not None:
        q = q.filter(models.CaregiverNotificationIntent.recipient_user_id == recipient_id)
    return q.order_by(models.CaregiverNotificationIntent.id.asc()).all()


def test_1_self_hr_stable(db, patches):
    u = _user(db, "self-stable")
    self_hs = ensure_self_subject_for_account(db, u.id)
    db.commit()
    device = _device(db, u, "dev-self-s")
    _push_prefs(db, u.id)
    when = _when()
    _established_baseline(db, self_hs, when, baseline_value=70.0, dispersion_value=2.0)
    # within band: |median-70| <= 4.4478*2 ≈ 8.9
    _seed_day_hr(db, self_hs, device, when, [70, 71, 69], prefix="ss")
    result = evaluate_canonical_hr_stability(db, health_subject_id=self_hs.id, when=when)
    assert result.status == CanonicalHrStabilityStatus.STABLE
    created = emit_hr_stability_i10_for_subject(db, health_subject_id=self_hs.id, when=when, commit=True)
    assert created
    assert any(i.semantic_family == I10SemanticFamily.HR_DAILY_STABILITY.value for i in created)
    assert all(i.recipient_user_id == u.id for i in created)


def test_2_self_hr_unstable(db, patches):
    u = _user(db, "self-unstable")
    self_hs = ensure_self_subject_for_account(db, u.id)
    db.commit()
    device = _device(db, u, "dev-self-u")
    _push_prefs(db, u.id)
    when = _when()
    _established_baseline(db, self_hs, when, baseline_value=70.0, dispersion_value=1.0)
    # far outside band
    _seed_day_hr(db, self_hs, device, when, [120, 121, 119], prefix="su")
    result = evaluate_canonical_hr_stability(db, health_subject_id=self_hs.id, when=when)
    assert result.status == CanonicalHrStabilityStatus.UNSTABLE_OR_CHANGED
    created = emit_hr_stability_i10_for_subject(db, health_subject_id=self_hs.id, when=when, commit=True)
    assert created
    assert all(i.semantic_family == I10SemanticFamily.HR_INSTABILITY.value for i in created)


def test_3_4_other_hr_stable_and_unstable(db, patches):
    mgr = _user(db, "mgr-other")
    other = create_managed_subject_without_account(
        db, account_user_id=mgr.id, display_name="CarePerson", access_role="MANAGER"
    )
    device = _device(db, mgr, "dev-other")
    _push_prefs(db, mgr.id)
    _grant_both(db, mgr.id, other.id, mgr.id)
    when = _when()
    _established_baseline(db, other, when, baseline_value=75.0, dispersion_value=2.0)
    _seed_day_hr(db, other, device, when, [75, 76, 74], prefix="os")
    stable = evaluate_canonical_hr_stability(db, health_subject_id=other.id, when=when)
    assert stable.status == CanonicalHrStabilityStatus.STABLE
    s_intents = emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when, commit=True)
    assert s_intents
    assert s_intents[0].recipient_user_id == mgr.id
    assert s_intents[0].owner_user_id is None  # accountless OTHER
    assert other.linked_user_id is None

    # second day / other subject values for unstable — wipe day samples via new keys on same day after clearing?
    # Use separate when day for unstable path on same subject
    when2 = _when("2026-09-01")
    _established_baseline(db, other, when2, baseline_value=75.0, dispersion_value=1.0)
    _seed_day_hr(db, other, device, when2, [110, 111, 109], prefix="ou")
    unstable = evaluate_canonical_hr_stability(db, health_subject_id=other.id, when=when2)
    assert unstable.status == CanonicalHrStabilityStatus.UNSTABLE_OR_CHANGED
    u_intents = emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when2, commit=True)
    assert u_intents
    assert u_intents[0].semantic_family == I10SemanticFamily.HR_INSTABILITY.value
    assert u_intents[0].recipient_user_id == mgr.id


def test_5_insufficient_no_notification(db, patches):
    u = _user(db, "insuff")
    self_hs = ensure_self_subject_for_account(db, u.id)
    db.commit()
    _push_prefs(db, u.id)
    when = _when()
    # no baseline, no HR
    result = evaluate_canonical_hr_stability(db, health_subject_id=self_hs.id, when=when)
    assert result.status == CanonicalHrStabilityStatus.INSUFFICIENT_DATA
    assert emit_hr_stability_i10_for_subject(db, health_subject_id=self_hs.id, when=when, commit=True) == []


def test_6_7_baseline_isolation_two_others(db, patches):
    mgr = _user(db, "mgr-iso")
    a = create_managed_subject_without_account(
        db, account_user_id=mgr.id, display_name="OtherA", access_role="MANAGER"
    )
    b = create_managed_subject_without_account(
        db, account_user_id=mgr.id, display_name="OtherB", access_role="MANAGER"
    )
    da = _device(db, mgr, "dev-a")
    db2 = _device(db, mgr, "dev-b")
    when = _when()
    _established_baseline(db, a, when, baseline_value=70.0, dispersion_value=1.0)
    _established_baseline(db, b, when, baseline_value=90.0, dispersion_value=1.0)
    _seed_day_hr(db, a, da, when, [70, 71, 69], prefix="ia")
    _seed_day_hr(db, b, db2, when, [90, 91, 89], prefix="ib")
    ra = evaluate_canonical_hr_stability(db, health_subject_id=a.id, when=when)
    rb = evaluate_canonical_hr_stability(db, health_subject_id=b.id, when=when)
    assert ra.status == CanonicalHrStabilityStatus.STABLE
    assert rb.status == CanonicalHrStabilityStatus.STABLE
    assert ra.evidence.baseline_value == 70.0
    assert rb.evidence.baseline_value == 90.0


def test_8_9_daily_and_instability_reach_account(db, patches):
    mgr = _user(db, "mgr-reach")
    other = create_managed_subject_without_account(
        db, account_user_id=mgr.id, display_name="Reach", access_role="MANAGER"
    )
    device = _device(db, mgr, "dev-reach")
    _push_prefs(db, mgr.id)
    _grant_both(db, mgr.id, other.id, mgr.id)
    when = _when()
    _established_baseline(db, other, when, baseline_value=80.0, dispersion_value=2.0)
    _seed_day_hr(db, other, device, when, [80, 81, 79], prefix="rd")
    emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when, commit=True)
    daily = _intents(db, other.id, family=I10SemanticFamily.HR_DAILY_STABILITY.value, recipient_id=mgr.id)
    assert len(daily) == 1

    when2 = _when("2026-09-02")
    _established_baseline(db, other, when2, baseline_value=80.0, dispersion_value=1.0)
    _seed_day_hr(db, other, device, when2, [130, 131, 129], prefix="ri")
    emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when2, commit=True)
    inst = _intents(db, other.id, family=I10SemanticFamily.HR_INSTABILITY.value, recipient_id=mgr.id)
    assert len(inst) == 1


def test_10_revoked_recipient_fail_closed(db, patches):
    mgr = _user(db, "mgr-rev")
    other = create_managed_subject_without_account(
        db, account_user_id=mgr.id, display_name="Rev", access_role="MANAGER"
    )
    device = _device(db, mgr, "dev-rev")
    _push_prefs(db, mgr.id)
    _grant_both(db, mgr.id, other.id, mgr.id)
    when = _when()
    _established_baseline(db, other, when, baseline_value=70.0, dispersion_value=2.0)
    _seed_day_hr(db, other, device, when, [70, 71, 69], prefix="rv")
    created = emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when, commit=True)
    assert created
    intent = created[0]
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=mgr.id,
        health_subject_id=other.id,
        recipient_user_id=mgr.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    outcome = process_caregiver_delivery_intent(db, intent, commit=True)
    assert outcome is not None
    db.refresh(intent)
    assert intent.status in ("suppressed", "failed", "expired") or intent.status != "delivered"


def test_11_cross_account_denied(db, patches):
    a = _user(db, "acct-a")
    b = _user(db, "acct-b")
    other = create_managed_subject_without_account(
        db, account_user_id=a.id, display_name="OnlyA", access_role="MANAGER"
    )
    device = _device(db, a, "dev-xa")
    _push_prefs(db, a.id)
    _push_prefs(db, b.id)
    _grant_both(db, a.id, other.id, a.id)
    when = _when()
    _established_baseline(db, other, when, baseline_value=70.0, dispersion_value=2.0)
    _seed_day_hr(db, other, device, when, [70, 71, 69], prefix="xa")
    emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when, commit=True)
    assert _intents(db, other.id, recipient_id=b.id) == []
    assert _intents(db, other.id, recipient_id=a.id)


def test_12_no_duplicate_drvs_mad(db, patches):
    mgr = _user(db, "mgr-dupe")
    other = create_managed_subject_without_account(
        db, account_user_id=mgr.id, display_name="Dupe", access_role="MANAGER"
    )
    device = _device(db, mgr, "dev-dupe")
    _push_prefs(db, mgr.id)
    _grant_both(db, mgr.id, other.id, mgr.id)
    when = _when()
    _established_baseline(db, other, when, baseline_value=70.0, dispersion_value=1.0)
    _seed_day_hr(db, other, device, when, [120, 121, 119], prefix="dp")
    mad_intents = emit_hr_stability_i10_for_subject(db, health_subject_id=other.id, when=when, commit=True)
    assert mad_intents
    # Fabricate DRVS row + try emit — must mint zero I10
    packet = models.DevicePacket(
        device_row_id=device.id,
        device_logical_id=device.device_id,
        health_subject_id=other.id,
        client_packet_id="pkt-dupe-1",
        measured_at=when,
        server_received_at=when,
        ingestion_status="accepted",
        provenance_json="{}",
    )
    db.add(packet)
    db.flush()
    row = models.DeviceReportedVitalStatus(
        device_packet_id=packet.id,
        health_subject_id=other.id,
        status="UNSTABLE",
        source_class="DEVICE_REPORTED",
        detected_at=when,
        server_received_at=when,
        provenance_json="{}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    prev = None
    new_eff = get_effective_device_reported_vital_status(db, health_subject_id=other.id)
    drvs = emit_device_reported_vital_status_notifications(
        db,
        health_subject_id=other.id,
        ingested_row=row,
        previous=prev,
        new_effective=new_eff,
        commit=True,
    )
    assert drvs == []
    # still only MAD HR_INSTABILITY intents for this subject/day
    assert len(_intents(db, other.id, family=I10SemanticFamily.HR_INSTABILITY.value)) == 1
    device_status_legacy = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == other.id,
            models.CaregiverNotificationIntent.source_entity_type == "I10_DEVICE_REPORTED_VITAL_STATUS",
        )
        .count()
    )
    assert device_status_legacy == 0


def test_13_mother_als_fixture_generic_other(db, patches):
    son = _user(db, "son-fix")
    mother = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="Mother", access_role="MANAGER"
    )
    assert mother.display_name == "Mother"
    assert mother.linked_user_id is None
    device = _device(db, son, "dev-mother")
    _push_prefs(db, son.id)
    _grant_both(db, son.id, mother.id, son.id)
    when = _when()
    _established_baseline(db, mother, when, baseline_value=72.0, dispersion_value=2.0)
    _seed_day_hr(db, mother, device, when, [72, 73, 71], prefix="mo")
    result = evaluate_canonical_hr_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == CanonicalHrStabilityStatus.STABLE
    intents = emit_hr_stability_i10_for_subject(db, health_subject_id=mother.id, when=when, commit=True)
    assert intents
    body = (intents[0].payload_metadata_json or "").lower()
    assert "mother" not in body
    assert "als" not in body
    assert intents[0].recipient_user_id == son.id
