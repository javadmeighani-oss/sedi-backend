"""I9→I10 nonclinical vital stability contract (PO MAD band) + MANAGER fleet scan."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.core.device_auth import hash_device_token
from backend.app.services.i10.care_digest_producer_worker import (
    run_care_digest_producer_for_subject,
    run_care_digest_producer_scan,
)
from backend.app.services.i10.care_network_access import (
    grant_caregiver_subject_access,
)
from backend.app.services.i10.care_network_grants import (
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.care_subject_status_facts import (
    CareSubjectDataStatus,
    assemble_care_subject_status_facts,
)
from backend.app.services.i10.caregiver_data_gap import is_care_data_gap_candidate
from backend.app.services.i10.caregiver_status_digest import FORBIDDEN_PHRASES, render_care_status_digest_body
from backend.app.services.i10.policy_types import I10NotificationScope, I10SemanticFamily
from backend.app.services.i9.baseline_service import compute_daily_median_for_subject
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account
from backend.app.services.i9.nonclinical_vital_stability import (
    RAW_MAD_MULTIPLIER,
    NonclinicalVitalMonitoringStatus,
    evaluate_nonclinical_heart_rate_stability,
)
from backend.app.services.i9.time_buckets import bucket_bounds

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch.dict(
    "os.environ",
    {
        "SEDI_I10_CARE_DIGEST_PRODUCER_ENABLED": "true",
        "SEDI_I10_CARE_NETWORK_DELIVERY_ENABLED": "true",
    },
    clear=False,
)


@pytest.fixture
def patches():
    with _GATE4_PATCH, _FLAG_PATCH:
        yield


def _user(db, name: str, *, lang: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{name}", preferred_language=lang)
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


def _push(db, user_id: int, token: str) -> None:
    db.add(models.PushDevice(user_id=user_id, platform="android", fcm_token=token, is_active=True))
    db.commit()


def _prefs(db, user_id: int, *, health_alert: bool = True) -> None:
    db.add(
        models.NotificationPrefs(
            user_id=user_id,
            companion_enabled=True,
            health_alert_enabled=health_alert,
            reminder_medication_enabled=True,
            reminder_appointment_enabled=True,
            reminder_system_enabled=True,
        )
    )
    db.commit()


def _when(day: str = "2026-08-31", hour: int = 12) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")


def _period_start(when: datetime) -> datetime:
    day = when.date()
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _pm(db, *, subject, device, value, measured_at, key, ingestion_status="accepted"):
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
        ingestion_status=ingestion_status,
    )
    db.add(row)
    db.commit()
    return row


def _rollup(
    db,
    subject: models.HealthSubject,
    when: datetime,
    *,
    sample_count: int = 12,
    coverage: float = 0.85,
    hours_before_end: float = 2.0,
    user_id=None,
):
    start = _period_start(when)
    bucket_end = when - timedelta(hours=hours_before_end)
    row = models.PhysiologicalMeasurementRollup(
        user_id=user_id if user_id is not None else subject.linked_user_id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=start,
        bucket_end=bucket_end,
        sample_count=sample_count,
        avg_value=80.0,
        min_value=70.0,
        max_value=90.0,
        coverage=coverage,
    )
    db.add(row)
    db.commit()
    return row


def _established_baseline(
    db,
    subject: models.HealthSubject,
    when: datetime,
    *,
    baseline_value: float,
    dispersion_value: float,
    quality: str = "ESTABLISHED",
):
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
        valid_day_count=14 if quality == "ESTABLISHED" else 10,
        quality=quality,
        baseline_version=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_current_day_hr(db, subject, device, when, values: list[float], *, prefix: str = "cur"):
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


def _mother_family(db, *, manager_general: bool = True):
    """Son Account + accountless Mother HS (MANAGER) + optional CAREGIVER peer."""
    son = _user(db, "son")
    mother = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="Mother", access_role="MANAGER"
    )
    assert mother.linked_user_id is None
    device = _device(db, son, f"gadget-{son.id}")
    _push(db, son.id, f"fcm-son-{son.id}")
    _prefs(db, son.id)
    if manager_general:
        create_subject_notification_grant(
            db,
            actor_user_id=son.id,
            health_subject_id=mother.id,
            recipient_user_id=son.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
        create_subject_notification_grant(
            db,
            actor_user_id=son.id,
            health_subject_id=mother.id,
            recipient_user_id=son.id,
            notification_scope=I10NotificationScope.DEVICE_STATUS,
        )
    return son, mother, device


# --- A–C daily median ---


def test_a_daily_median_deterministic(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _seed_current_day_hr(db, mother, device, when, [60.0, 80.0, 100.0])
    m1 = compute_daily_median_for_subject(db, health_subject_id=mother.id, ref=when)
    m2 = compute_daily_median_for_subject(db, health_subject_id=mother.id, ref=when)
    assert m1 == 80.0
    assert m2 == 80.0


def test_b_accepted_measurements_only(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    d_start, _ = bucket_bounds("daily", ref=when)
    _pm(
        db,
        subject=mother,
        device=device,
        value=90.0,
        measured_at=d_start + timedelta(hours=1),
        key="rej-1",
        ingestion_status="rejected",
    )
    _pm(
        db,
        subject=mother,
        device=device,
        value=70.0,
        measured_at=d_start + timedelta(hours=2),
        key="acc-1",
        ingestion_status="accepted",
    )
    assert compute_daily_median_for_subject(db, health_subject_id=mother.id, ref=when) == 70.0


def test_c_mother_subject_isolation(db, patches):
    son, mother, device = _mother_family(db)
    other = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="Other", access_role="MANAGER"
    )
    when = _when()
    _seed_current_day_hr(db, mother, device, when, [72.0, 74.0, 76.0], prefix="m")
    _seed_current_day_hr(db, other, device, when, [120.0, 130.0, 140.0], prefix="o")
    assert compute_daily_median_for_subject(db, health_subject_id=mother.id, ref=when) == 74.0
    assert compute_daily_median_for_subject(db, health_subject_id=other.id, ref=when) == 130.0


# --- D–H MAD band ---


def test_d_established_inside_band_stable(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    # limit = 4.4478*2 = 8.8956; median 102 is inside
    _seed_current_day_hr(db, mother, device, when, [102.0, 102.0, 102.0])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_STABLE
    facts = assemble_care_subject_status_facts(db, health_subject_id=mother.id, when=when)
    assert facts.monitoring_status == "NONCLINICAL_STABLE"
    body = render_care_status_digest_body(facts).lower()
    assert "consistent with the recent established personal pattern" in body
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in body


def test_e_equal_to_threshold_stable(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    mad = 2.0
    baseline = 100.0
    limit = RAW_MAD_MULTIPLIER * mad
    _established_baseline(db, mother, when, baseline_value=baseline, dispersion_value=mad)
    target = baseline + limit
    _seed_current_day_hr(db, mother, device, when, [target, target, target])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_STABLE
    assert result.delta is not None and abs(result.delta - limit) < 1e-9


def test_f_just_above_band_changed(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    mad = 2.0
    baseline = 100.0
    limit = RAW_MAD_MULTIPLIER * mad
    _established_baseline(db, mother, when, baseline_value=baseline, dispersion_value=mad)
    target = baseline + limit + 0.0001
    _seed_current_day_hr(db, mother, device, when, [target, target, target])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_CHANGED
    facts = assemble_care_subject_status_facts(db, health_subject_id=mother.id, when=when)
    assert facts.monitoring_status == "NONCLINICAL_CHANGED"
    assert "meaningful change" in render_care_status_digest_body(facts).lower()


def test_g_positive_negative_delta_symmetric(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    mad = 2.0
    baseline = 100.0
    limit = RAW_MAD_MULTIPLIER * mad
    _established_baseline(db, mother, when, baseline_value=baseline, dispersion_value=mad)
    high = baseline + limit + 1.0
    _seed_current_day_hr(db, mother, device, when, [high], prefix="hi")
    high_r = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    db.query(models.PhysiologicalMeasurement).delete()
    db.commit()
    low = baseline - limit - 1.0
    _seed_current_day_hr(db, mother, device, when, [low], prefix="lo")
    low_r = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert high_r.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_CHANGED
    assert low_r.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_CHANGED
    assert high_r.delta == pytest.approx(low_r.delta)


def test_h_tiny_deviation_not_changed(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    _seed_current_day_hr(db, mother, device, when, [100.5, 100.5, 100.5])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.NONCLINICAL_STABLE
    assert result.status != NonclinicalVitalMonitoringStatus.NONCLINICAL_CHANGED


# --- I–M fail closed ---


def test_i_provisional_insufficient(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(
        db, mother, when, baseline_value=100.0, dispersion_value=2.0, quality="PROVISIONAL"
    )
    _seed_current_day_hr(db, mother, device, when, [100.0])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.DATA_INSUFFICIENT
    assert result.reason == "baseline_provisional"


def test_j_none_insufficient(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _seed_current_day_hr(db, mother, device, when, [100.0])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.DATA_INSUFFICIENT
    assert result.reason == "baseline_none"


def test_k_mad_zero_insufficient(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=0.0)
    _seed_current_day_hr(db, mother, device, when, [100.0])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.DATA_INSUFFICIENT
    assert result.reason == "mad_zero"


def test_l_missing_dispersion_fail_closed(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    row = (
        db.query(models.PhysiologicalBaseline)
        .filter(models.PhysiologicalBaseline.health_subject_id == mother.id)
        .one()
    )
    row.dispersion_value = None
    db.commit()
    _seed_current_day_hr(db, mother, device, when, [100.0])
    result = evaluate_nonclinical_heart_rate_stability(db, health_subject_id=mother.id, when=when)
    assert result.status == NonclinicalVitalMonitoringStatus.DATA_INSUFFICIENT
    assert result.reason == "dispersion_invalid"


def test_m_partial_data_insufficient(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when, coverage=0.2)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    _seed_current_day_hr(db, mother, device, when, [100.0])
    facts = assemble_care_subject_status_facts(db, health_subject_id=mother.id, when=when)
    assert facts.data_status == CareSubjectDataStatus.PARTIAL_DATA
    assert facts.monitoring_status == "DATA_INSUFFICIENT"


# --- N–P data gap ---


def test_n_stale_care_data_gap(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when, hours_before_end=60.0)
    facts = assemble_care_subject_status_facts(db, health_subject_id=mother.id, when=when)
    assert facts.data_status == CareSubjectDataStatus.STALE_DATA
    assert facts.monitoring_status is None
    assert is_care_data_gap_candidate(facts) is True
    assert facts.monitoring_status != "NONCLINICAL_STABLE"


def test_o_no_data_care_data_gap(db, patches):
    son, mother, _ = _mother_family(db)
    when = _when()
    _rollup(db, mother, when, sample_count=0, coverage=0.0)
    facts = assemble_care_subject_status_facts(db, health_subject_id=mother.id, when=when)
    assert facts.data_status == CareSubjectDataStatus.NO_DATA
    assert facts.monitoring_status is None
    assert is_care_data_gap_candidate(facts) is True


def test_p_stale_never_emits_stable(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when, hours_before_end=60.0)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    _seed_current_day_hr(db, mother, device, when, [100.0])
    facts = assemble_care_subject_status_facts(db, health_subject_id=mother.id, when=when)
    assert facts.monitoring_status is None
    assert facts.monitoring_status != "NONCLINICAL_STABLE"


# --- Q–S fleet scan ---


def test_q_manager_son_discovered_by_fleet_scan(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    _seed_current_day_hr(db, mother, device, when, [100.0])
    summary = run_care_digest_producer_scan(db, when=when, limit=50, deliver=False)
    assert summary["processed"] >= 1
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.recipient_user_id == son.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .one()
    )
    assert intent.owner_user_id is None
    assert mother.linked_user_id is None


def test_r_caregiver_still_discovered(db, patches):
    son, mother, device = _mother_family(db, manager_general=True)
    cg = _user(db, "cg-peer")
    grant_caregiver_subject_access(
        db, actor_user_id=son.id, health_subject_id=mother.id, recipient_account_user_id=cg.id
    )
    _push(db, cg.id, f"fcm-cg-{cg.id}")
    _prefs(db, cg.id)
    create_subject_notification_grant(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    when = _when()
    _rollup(db, mother, when)
    summary = run_care_digest_producer_scan(db, when=when, limit=50, deliver=False)
    assert summary["processed"] >= 1
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.recipient_user_id == cg.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .count()
        == 1
    )


def test_s_manager_caregiver_overlap_no_subject_dup(db, patches):
    son, mother, device = _mother_family(db)
    # Son already MANAGER; also add CAREGIVER access row for same account if allowed —
    # if grant API rejects duplicate, simulate second role scan via caregiver peer only.
    cg = _user(db, "cg2")
    grant_caregiver_subject_access(
        db, actor_user_id=son.id, health_subject_id=mother.id, recipient_account_user_id=cg.id
    )
    when = _when()
    _rollup(db, mother, when)
    # Count distinct subjects returned by the same filter the scan uses
    rows = (
        db.query(models.HealthSubject.id)
        .join(
            models.AccountHealthSubjectAccess,
            models.AccountHealthSubjectAccess.health_subject_id == models.HealthSubject.id,
        )
        .filter(
            models.HealthSubject.id == mother.id,
            models.AccountHealthSubjectAccess.access_role.in_(("CAREGIVER", "MANAGER")),
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .distinct()
        .all()
    )
    assert len(rows) == 1
    summary = run_care_digest_producer_scan(db, when=when, limit=50, deliver=False)
    # subject processed once → one status intent per eligible recipient (son)
    son_status = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.recipient_user_id == son.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .count()
    )
    assert son_status == 1
    assert summary["processed"] >= 1


# --- T–Z care network ---


def test_t_unrelated_account_blocked(db, patches):
    son, mother, device = _mother_family(db)
    stranger = _user(db, "stranger")
    _push(db, stranger.id, "fcm-stranger")
    _prefs(db, stranger.id)
    when = _when()
    _rollup(db, mother, when)
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=True)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(models.CaregiverNotificationIntent.recipient_user_id == stranger.id)
        .count()
        == 0
    )


def test_u_access_revoke_fail_closed(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=False)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == son.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .one()
    )
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == mother.id,
            models.AccountHealthSubjectAccess.account_user_id == son.id,
        )
        .all()
    )
    for a in access:
        a.is_active = False
        a.revoked_at = when.replace(tzinfo=None)
    db.commit()
    from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent

    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"


def test_v_grant_revoke_fail_closed(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=False)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.recipient_user_id == son.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .one()
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent

    outcome = process_caregiver_delivery_intent(db, intent)
    assert outcome["status"] == "suppressed"


def test_w_prefs_respected(db, patches):
    son, mother, device = _mother_family(db)
    cg = _user(db, "cg-prefs")
    grant_caregiver_subject_access(
        db, actor_user_id=son.id, health_subject_id=mother.id, recipient_account_user_id=cg.id
    )
    _push(db, cg.id, f"fcm-{cg.id}")
    _prefs(db, cg.id)
    create_subject_notification_grant(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    when = _when()
    _rollup(db, mother, when)
    db.query(models.NotificationPrefs).filter(models.NotificationPrefs.user_id == son.id).update(
        {"health_alert_enabled": False}
    )
    db.commit()
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=True)
    notifs = (
        db.query(models.Notification)
        .join(
            models.CaregiverNotificationIntent,
            models.CaregiverNotificationIntent.notification_id == models.Notification.id,
        )
        .filter(
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value
        )
        .all()
    )
    assert {n.user_id for n in notifs} == {cg.id}


def test_x_multi_caregiver_independent(db, patches):
    son, mother, device = _mother_family(db)
    cg = _user(db, "cg-indep")
    grant_caregiver_subject_access(
        db, actor_user_id=son.id, health_subject_id=mother.id, recipient_account_user_id=cg.id
    )
    _push(db, cg.id, f"fcm-{cg.id}")
    _prefs(db, cg.id)
    create_subject_notification_grant(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=cg.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    when = _when()
    _rollup(db, mother, when)
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=False)
    recipients = {
        r.recipient_user_id
        for r in db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .all()
    }
    assert recipients == {son.id, cg.id}


def test_y_occurrence_idempotency(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=False)
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=False)
    assert (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.recipient_user_id == son.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .count()
        == 1
    )


def test_z_b06_delivery_revalidation_and_identity(db, patches):
    son, mother, device = _mother_family(db)
    when = _when()
    _rollup(db, mother, when)
    _established_baseline(db, mother, when, baseline_value=100.0, dispersion_value=2.0)
    _seed_current_day_hr(db, mother, device, when, [100.0])
    run_care_digest_producer_for_subject(db, health_subject_id=mother.id, when=when, deliver=True)
    intent = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == mother.id,
            models.CaregiverNotificationIntent.recipient_user_id == son.id,
            models.CaregiverNotificationIntent.semantic_family
            == I10SemanticFamily.CARE_STATUS_DIGEST.value,
        )
        .one()
    )
    assert intent.owner_user_id is None
    assert mother.linked_user_id is None
    assert intent.health_subject_id == mother.id
    assert intent.recipient_user_id == son.id
    assert intent.recipient_user_id != mother.id
    # No fake mother account
    assert db.query(models.User).filter(models.User.name == "Mother").count() == 0
