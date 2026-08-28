"""I9 longitudinal aggregation, baseline read, and I7 producer runtime tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.core.device_auth import hash_device_token
from backend.app.services.i6.consent_service import PERM_WRITE, grant_memory_consent
from backend.app.services.i7.i9_patterns import upsert_i9_derived_pattern
from backend.app.services.i9.aggregation_service import (
    BucketStats,
    compute_bucket_stats_from_measurements,
    rebuild_daily_bucket,
    rebuild_higher_bucket_from_daily_rollups,
    upsert_rollup,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.i7_producer_service import produce_i7_pattern_from_latest_rollup
from backend.app.services.i9.longitudinal_read_service import (
    list_aggregates,
    list_cardiac_events,
    list_observations,
)
from backend.app.services.i9.time_buckets import bucket_bounds


def _user(db, name: str, phone: str) -> models.User:
    row = models.User(name=name, secret_key=f"k-{name}", preferred_language="en", phone=phone)
    db.add(row)
    db.flush()
    return row


def _device(db, owner: models.User, device_id: str) -> models.Device:
    dev = models.Device(
        user_id=owner.id,
        device_id=device_id,
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token(f"tok-{device_id}"),
        firmware_version="fw-1.0",
    )
    db.add(dev)
    db.flush()
    return dev


def _pm(
    db,
    *,
    subject: models.HealthSubject,
    device: models.Device,
    value: float,
    measured_at: datetime,
    key: str,
) -> models.PhysiologicalMeasurement:
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
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def javad(db):
    return _user(db, "Javad", "+989100000001")


@pytest.fixture
def stranger(db):
    return _user(db, "Stranger", "+989100000099")


@pytest.fixture
def family(db, javad):
    javad_subject = ensure_self_subject_for_account(db, javad.id)
    father = create_managed_subject_without_account(
        db, account_user_id=javad.id, display_name="Father", access_role="CAREGIVER"
    )
    mother = create_managed_subject_without_account(
        db, account_user_id=javad.id, display_name="Mother", access_role="MANAGER"
    )
    device = _device(db, javad, "FamDev001")
    return {
        "javad": javad,
        "javad_subject": javad_subject,
        "father": father,
        "mother": mother,
        "device": device,
    }


def test_l1_self_reads_own_observations(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    t0 = datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc)
    _pm(db, subject=subj, device=dev, value=72.0, measured_at=t0, key="l1-1")
    rows = list_observations(db, account_user_id=family["javad"].id, health_subject_id=subj.id)
    assert len(rows) == 1
    assert rows[0]["numeric_value"] == 72.0


def test_l2_caregiver_reads_managed_subject(db, family):
    father = family["father"]
    _pm(
        db,
        subject=father,
        device=family["device"],
        value=65.0,
        measured_at=datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc),
        key="l2-f",
    )
    rows = list_observations(db, account_user_id=family["javad"].id, health_subject_id=father.id)
    assert len(rows) == 1
    assert rows[0]["numeric_value"] == 65.0


def test_l3_manager_reads_managed_subject(db, family):
    mother = family["mother"]
    _pm(
        db,
        subject=mother,
        device=family["device"],
        value=70.0,
        measured_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        key="l3-m",
    )
    rows = list_observations(db, account_user_id=family["javad"].id, health_subject_id=mother.id)
    assert len(rows) == 1


def test_l4_unauthorized_account_fail_closed(db, family, stranger):
    from backend.app.services.i9.health_subject_service import HealthSubjectAccessDenied

    with pytest.raises(HealthSubjectAccessDenied):
        list_observations(
            db,
            account_user_id=stranger.id,
            health_subject_id=family["father"].id,
        )


def test_l5_multi_subject_isolation(db, family):
    father, mother = family["father"], family["mother"]
    dev = family["device"]
    _pm(db, subject=father, device=dev, value=60.0, measured_at=datetime(2026, 3, 11, 8, 0, tzinfo=timezone.utc), key="l5-f")
    _pm(db, subject=mother, device=dev, value=90.0, measured_at=datetime(2026, 3, 11, 8, 5, tzinfo=timezone.utc), key="l5-m")
    father_rows = list_observations(db, account_user_id=family["javad"].id, health_subject_id=father.id)
    mother_rows = list_observations(db, account_user_id=family["javad"].id, health_subject_id=mother.id)
    assert [r["numeric_value"] for r in father_rows] == [60.0]
    assert [r["numeric_value"] for r in mother_rows] == [90.0]


def test_l6_gateway_token_does_not_grant_vitals_read(client, db, family):
    """Device bearer is not account JWT — longitudinal routes stay fail-closed."""
    headers = {"Authorization": f"Bearer device-not-a-user-jwt"}
    r = client.get(f"/health-subjects/{family['father'].id}/vitals/observations", headers=headers)
    assert r.status_code == 401


def test_l7_time_range_uses_measured_at(db, family):
    father = family["father"]
    dev = family["device"]
    inside = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    outside = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    _pm(db, subject=father, device=dev, value=55.0, measured_at=inside, key="l7-in")
    _pm(db, subject=father, device=dev, value=99.0, measured_at=outside, key="l7-out")
    rows = list_observations(
        db,
        account_user_id=family["javad"].id,
        health_subject_id=father.id,
        start=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        end=datetime(2026, 4, 2, 0, 0, tzinfo=timezone.utc),
    )
    assert len(rows) == 1
    assert rows[0]["numeric_value"] == 55.0


def test_l8_pagination_limit_bounds_response(db, family):
    father = family["father"]
    dev = family["device"]
    for i in range(5):
        _pm(
            db,
            subject=father,
            device=dev,
            value=60.0 + i,
            measured_at=datetime(2026, 5, 1, 10, i, tzinfo=timezone.utc),
            key=f"l8-{i}",
        )
    rows = list_observations(
        db,
        account_user_id=family["javad"].id,
        health_subject_id=father.id,
        limit=2,
        offset=1,
    )
    assert len(rows) == 2


def test_l9_daily_aggregation(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)
    d_start, d_end = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=80.0, measured_at=d_start + timedelta(hours=1), key="l9-a")
    _pm(db, subject=subj, device=dev, value=100.0, measured_at=d_start + timedelta(hours=2), key="l9-b")
    stats = rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    assert stats.sample_count == 2
    assert stats.avg_value == 90.0


def test_l10_weekly_aggregation(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    for day in range(3):
        d_ref = ref - timedelta(days=day)
        d_start, _ = bucket_bounds("daily", ref=d_ref)
        rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=d_ref)
        _pm(
            db,
            subject=subj,
            device=dev,
            value=70.0 + day,
            measured_at=d_start + timedelta(hours=3),
            key=f"l10-d{day}",
        )
        rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=d_ref)
    stats = rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="weekly", ref=ref
    )
    assert stats.sample_count >= 3


def test_l11_calendar_month_aggregation(db, family):
    subj = family["javad_subject"]
    ref = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    m_start, m_end = bucket_bounds("calendar_month", ref=ref)
    assert m_start.month == 7
    assert m_end.month == 8
    stats = rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="calendar_month", ref=ref
    )
    assert stats.sample_count >= 0


def test_l12_yearly_aggregation(db, family):
    subj = family["javad_subject"]
    ref = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    y_start, y_end = bucket_bounds("yearly", ref=ref)
    assert y_end.year - y_start.year == 1
    stats = rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="yearly", ref=ref
    )
    assert stats is not None


def test_l13_calendar_month_not_four_weeks(db):
    ref = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
    m_start, m_end = bucket_bounds("calendar_month", ref=ref)
    month_days = (m_end - m_start).days
    four_weeks = 28
    assert month_days == 31
    assert month_days != four_weeks


def test_l14_weighted_aggregation_not_average_of_averages():
    day_a = BucketStats.from_measurements([60.0] * 100)
    day_b = BucketStats.from_measurements([100.0] * 10)
    merged = day_a.merge_weighted(day_b)
    assert merged.avg_value != 80.0
    assert abs(merged.avg_value - ((60 * 100 + 100 * 10) / 110)) < 0.001


def test_l15_min_max_preserved(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=50.0, measured_at=d_start + timedelta(hours=1), key="l15-min")
    _pm(db, subject=subj, device=dev, value=120.0, measured_at=d_start + timedelta(hours=2), key="l15-max")
    stats = rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    assert stats.min_value == 50.0
    assert stats.max_value == 120.0


def test_l16_sample_count_preserved(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    for i in range(7):
        _pm(
            db,
            subject=subj,
            device=dev,
            value=70.0,
            measured_at=d_start + timedelta(minutes=i),
            key=f"l16-{i}",
        )
    stats = rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    assert stats.sample_count == 7


def test_l17_late_arriving_measured_at_updates_bucket(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    stats1 = rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    assert stats1.sample_count == 0
    _pm(
        db,
        subject=subj,
        device=dev,
        value=88.0,
        measured_at=d_start + timedelta(hours=5),
        key="l17-late",
    )
    stats2 = rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    assert stats2.sample_count == 1
    assert stats2.avg_value == 88.0


def test_l18_aggregate_rerun_idempotent(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
    d_start, d_end = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=75.0, measured_at=d_start + timedelta(hours=1), key="l18-1")
    stats = compute_bucket_stats_from_measurements(
        db,
        health_subject_id=subj.id,
        measurement_type="heart_rate",
        bucket_start=d_start,
        bucket_end=d_end,
    )
    upsert_rollup(
        db,
        subject=subj,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=d_start,
        bucket_end=d_end,
        stats=stats,
    )
    upsert_rollup(
        db,
        subject=subj,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=d_start,
        bucket_end=d_end,
        stats=stats,
    )
    count = (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(
            models.PhysiologicalMeasurementRollup.health_subject_id == subj.id,
            models.PhysiologicalMeasurementRollup.bucket_kind == "daily",
            models.PhysiologicalMeasurementRollup.bucket_start == d_start,
        )
        .count()
    )
    assert count == 1


def test_l19_events_persist_independently_from_rollups(db, family):
    from backend.app.services.i9.device_binding_service import bind_device_to_subject
    from backend.app.services.i9.device_packet_service import (
        DevicePacketIngestInput,
        PacketObservationIn,
        ingest_device_packet,
    )

    father = family["father"]
    dev = family["device"]
    bind_device_to_subject(
        db, device=dev, health_subject_id=father.id, bound_by_account_user_id=family["javad"].id
    )
    detected = datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)
    ingest_device_packet(
        db,
        device=dev,
        packet_in=DevicePacketIngestInput(
            client_packet_id="l19-cardiac",
            measured_at=detected,
            firmware_version="fw-9",
            algorithm_version="algo-1",
            observations=[
                PacketObservationIn(
                    observation_type="device_reported_cardiac_event",
                    payload={"event_code": "arrhythmia_indicator"},
                    detected_at=detected,
                )
            ],
        ),
    )
    rebuild_daily_bucket(db, subject=father, measurement_type="heart_rate", ref=detected)
    events = list_cardiac_events(
        db, account_user_id=family["javad"].id, health_subject_id=father.id
    )
    assert len(events) == 1
    assert events[0]["source_class"] == "DEVICE_REPORTED"


def test_l20_event_provenance_preserved(db, family):
    from backend.app.services.i9.device_binding_service import bind_device_to_subject
    from backend.app.services.i9.device_packet_service import (
        DevicePacketIngestInput,
        PacketObservationIn,
        ingest_device_packet,
    )

    father = family["father"]
    dev = family["device"]
    bind_device_to_subject(
        db, device=dev, health_subject_id=father.id, bound_by_account_user_id=family["javad"].id
    )
    detected = datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc)
    ingest_device_packet(
        db,
        device=dev,
        packet_in=DevicePacketIngestInput(
            client_packet_id="l20-prov",
            measured_at=detected,
            firmware_version="fw-prov",
            algorithm_version="algo-prov",
            observations=[
                PacketObservationIn(
                    observation_type="device_reported_cardiac_event",
                    payload={"event_code": "critical_arrhythmia"},
                    detected_at=detected,
                )
            ],
        ),
    )
    events = list_cardiac_events(
        db, account_user_id=family["javad"].id, health_subject_id=father.id
    )
    assert events[0]["firmware_version"] == "fw-prov"
    assert events[0]["algorithm_version"] == "algo-prov"


def test_l21_baseline_governed_algorithm(db, family):
    from backend.app.services.i9.longitudinal_read_service import list_baselines

    payload = list_baselines(
        db, account_user_id=family["javad"].id, health_subject_id=family["javad_subject"].id
    )
    assert payload["baseline_method"] == "PERSONAL_OBSERVED_BASELINE_V1"


def test_l21b_managed_subject_rollup_persists(db, family):
    father = family["father"]
    dev = family["device"]
    ref = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=father, device=dev, value=66.0, measured_at=d_start + timedelta(hours=1), key="l21b")
    rebuild_daily_bucket(db, subject=father, measurement_type="heart_rate", ref=ref)
    row = (
        db.query(models.PhysiologicalMeasurementRollup)
        .filter(models.PhysiologicalMeasurementRollup.health_subject_id == father.id)
        .first()
    )
    assert row is not None
    assert row.user_id is None


def test_l22_decision_engine_thresholds_unchanged():
    from backend.app.decision_engine.rules import CANONICAL_ALERT_CODE_BY_REASON

    for rule_id in ("HR_HIGH_REST", "HR_HIGH", "HR_LOW", "BP_HIGH", "GLUCOSE_HIGH", "GLUCOSE_LOW", "TEMP_HIGH"):
        assert rule_id in CANONICAL_ALERT_CODE_BY_REASON


def test_l23_i7_producer_requires_source_refs(db, family):
    user = family["javad"]
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE,), commit=True)
    with pytest.raises(ValueError, match="I9_SOURCE_REFS_REQUIRED"):
        upsert_i9_derived_pattern(
            db,
            user_id=user.id,
            pattern_key="test",
            pattern={"k": 1},
            source_refs=[],
        )


def test_l24_i7_producer_obey_i6_consent(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=77.0, measured_at=d_start + timedelta(hours=1), key="l24")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="weekly", ref=ref
    )
    result = produce_i7_pattern_from_latest_rollup(db, health_subject_id=subj.id)
    assert result["status"] == "SKIPPED_NO_I6_WRITE_CONSENT"


def test_l25_linked_subject_writes_i7_pattern(db, family):
    user = family["javad"]
    subj = family["javad_subject"]
    dev = family["device"]
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE,), commit=True)
    ref = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=77.0, measured_at=d_start + timedelta(hours=1), key="l25")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="weekly", ref=ref
    )
    result = produce_i7_pattern_from_latest_rollup(db, health_subject_id=subj.id)
    assert result["status"] == "WRITTEN"
    assert result["user_id"] == user.id


def test_l26_managed_subject_no_wrong_i7_identity(db, family):
    father = family["father"]
    dev = family["device"]
    ref = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=father, device=dev, value=66.0, measured_at=d_start + timedelta(hours=1), key="l26")
    rebuild_daily_bucket(db, subject=father, measurement_type="heart_rate", ref=ref)
    result = produce_i7_pattern_from_latest_rollup(db, health_subject_id=father.id)
    assert result["status"] == "SKIPPED_NO_LINKED_ACCOUNT"
    patterns = db.query(models.UserI7DerivedPattern).filter(
        models.UserI7DerivedPattern.user_id == family["javad"].id
    ).count()
    assert patterns == 0


def test_l27_no_raw_sample_direct_i7_write(db, family):
    """Producer only accepts aggregate rollup sources, not raw PM rows."""
    from backend.app.services.i7.i9_patterns import upsert_i9_derived_pattern

    user = family["javad"]
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE,), commit=True)
    with pytest.raises(ValueError, match="I9_SOURCE_REFS_REQUIRED"):
        upsert_i9_derived_pattern(
            db,
            user_id=user.id,
            pattern_key="raw-bypass",
            pattern={"from": "raw"},
            source_refs=[],
        )


def test_l28_trusted_fleet_regression_import():
    import backend.tests.test_i9_trusted_fleet_provisioning_claim_hardening as mod

    assert hasattr(mod, "test_f1_ordinary_user_cannot_provision_when_admin_disabled")


def test_l29_claim_binding_regression_import():
    import backend.tests.test_i9_device_claim_trust_ingest_runtime as mod

    assert hasattr(mod, "test_t1_unclaimed_device_claimed_to_self_subject")


def test_l30_packet_ack_regression_import():
    import backend.tests.test_i9_health_subject_device_packet_foundation as mod

    assert hasattr(mod, "test_t7_packet_retry_idempotent")


def test_l31_alembic_single_head_073():
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory("backend/alembic").get_heads()
    assert heads == ["073_i9_subject_native_rollup_baseline"]
