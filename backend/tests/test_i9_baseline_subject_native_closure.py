"""I9 baseline, subject-native persistence, migration 073, and rebuild authorization closure."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect

from backend.app import models
from backend.app.core.device_auth import hash_device_token
from backend.app.services.i6.consent_service import PERM_WRITE, grant_memory_consent
from backend.app.services.i9.aggregation_service import rebuild_daily_bucket, upsert_rollup, compute_bucket_stats_from_measurements, find_rollup_row
from backend.app.services.i9.baseline_service import (
    BASELINE_METHOD,
    BASELINE_SCOPE_V1,
    ROLLING_WINDOW_DAYS,
    compute_personal_observed_baseline,
    rebuild_subject_vitals_internal,
    upsert_personal_observed_baseline,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.i7_producer_service import produce_i7_pattern_from_latest_rollup
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
    )
    db.add(dev)
    db.flush()
    return dev


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
    db.flush()
    return row


def _seed_daily_hr(db, subject, device, ref, days_values: dict[int, list[float]]):
    """days_values: offset from ref day (0=today) -> list of HR values that day."""
    d_start, _ = bucket_bounds("daily", ref=ref)
    for offset, values in days_values.items():
        day_start = d_start - timedelta(days=offset)
        for i, v in enumerate(values):
            _pm(
                db,
                subject=subject,
                device=device,
                value=v,
                measured_at=day_start + timedelta(hours=10, minutes=i),
                key=f"seed-{offset}-{i}-{v}",
            )


@pytest.fixture
def javad(db):
    return _user(db, "Javad", "+989100000101")


@pytest.fixture
def family(db, javad):
    javad_subject = ensure_self_subject_for_account(db, javad.id)
    father = create_managed_subject_without_account(
        db, account_user_id=javad.id, display_name="Father", access_role="CAREGIVER"
    )
    device = _device(db, javad, "ClosureDev001")
    return {"javad": javad, "javad_subject": javad_subject, "father": father, "device": device}


def test_c01_alembic_single_head_073():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "heads"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "073_i9_subject_native_rollup_baseline (head)" in result.stdout


def test_c02_migration_073_columns_present(db):
    insp = inspect(db.bind)
    pmr_cols = {c["name"] for c in insp.get_columns("physiological_measurement_rollups")}
    pb_cols = {c["name"] for c in insp.get_columns("physiological_baselines")}
    assert "health_subject_id" in pmr_cols
    assert "baseline_method" in pb_cols
    assert "dispersion_value" in pb_cols
    assert "valid_day_count" in pb_cols


def test_c03_linked_subject_rollup_persistence(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=80.0, measured_at=d_start + timedelta(hours=1), key="c03")
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    row = find_rollup_row(
        db, health_subject_id=subj.id, measurement_type="heart_rate", bucket_kind="daily", bucket_start=d_start
    )
    assert row is not None
    assert row.health_subject_id == subj.id
    assert row.user_id == subj.linked_user_id


def test_c04_managed_no_account_rollup_persistence(db, family):
    father = family["father"]
    dev = family["device"]
    ref = datetime(2026, 12, 2, 12, 0, tzinfo=timezone.utc)
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=father, device=dev, value=65.0, measured_at=d_start + timedelta(hours=2), key="c04")
    rebuild_daily_bucket(db, subject=father, measurement_type="heart_rate", ref=ref)
    row = find_rollup_row(
        db, health_subject_id=father.id, measurement_type="heart_rate", bucket_kind="daily", bucket_start=d_start
    )
    assert row is not None
    assert row.health_subject_id == father.id
    assert row.user_id is None
    assert father.linked_user_id is None


def test_c05_linked_subject_baseline_persistence(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 10, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [70.0 + i] for i in range(7)})
    row = upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    assert row is not None
    assert row.health_subject_id == subj.id
    assert row.baseline_method == BASELINE_METHOD
    assert row.quality == "PROVISIONAL"


def test_c06_managed_no_account_baseline_persistence(db, family):
    father = family["father"]
    dev = family["device"]
    ref = datetime(2026, 12, 11, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, father, dev, ref, {i: [60.0 + i] for i in range(7)})
    row = upsert_personal_observed_baseline(db, subject=father, ref=ref)
    assert row is not None
    assert row.health_subject_id == father.id
    assert row.user_id is None


def test_c07_under_7_valid_days_no_baseline(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 12, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {0: [72.0], 1: [73.0], 2: [74.0], 3: [75.0], 4: [76.0], 5: [77.0]})
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert computed.status == "NONE"
    assert computed.valid_day_count == 6
    row = upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    assert row is None


def test_c08_7_days_provisional(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 13, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [70.0 + i] for i in range(7)})
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert computed.status == "PROVISIONAL"
    assert computed.valid_day_count == 7


def test_c09_13_days_provisional(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 14, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [70.0 + (i % 5)] for i in range(13)})
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert computed.status == "PROVISIONAL"
    assert computed.valid_day_count == 13


def test_c10_14_days_established(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 15, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [68.0 + (i % 3)] for i in range(14)})
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert computed.status == "ESTABLISHED"
    assert computed.valid_day_count == 14


def test_c11_exact_median_of_daily_medians(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 16, 12, 0, tzinfo=timezone.utc)
    # days with medians 60,70,80,90,100,110,120 -> median=90
    daily = {i: [60.0 + i * 10.0] for i in range(7)}
    _seed_daily_hr(db, subj, dev, ref, daily)
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert computed.baseline_value == 90.0


def test_c12_exact_mad(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 17, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [60.0 + i * 10.0] for i in range(7)})
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    # medians 60..120 center 90 deviations 30,20,10,0,10,20,30 -> MAD median=20
    assert computed.dispersion_value == 20.0


def test_c13_28_day_rolling_window(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 18, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [70.0] for i in range(28)})
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert computed.valid_day_count == 28
    assert abs(computed.coverage - 1.0) < 0.001
    assert (computed.window_end - computed.window_start).days >= ROLLING_WINDOW_DAYS - 1


def test_c14_late_data_recompute(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 19, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [70.0 + i] for i in range(7)})
    first = upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    first_value = first.baseline_value
    d_start, _ = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=200.0, measured_at=d_start + timedelta(hours=5), key="c14-late")
    second = upsert_personal_observed_baseline(db, subject=subj, ref=ref)
    assert second is not None
    assert second.baseline_value != first_value


def test_c15_technical_rejected_excluded_only(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
    d_start, d_end = bucket_bounds("daily", ref=ref)
    _pm(db, subject=subj, device=dev, value=80.0, measured_at=d_start + timedelta(hours=1), key="c15-acc")
    _pm(
        db,
        subject=subj,
        device=dev,
        value=999.0,
        measured_at=d_start + timedelta(hours=2),
        key="c15-rej",
        ingestion_status="rejected",
    )
    rows = compute_bucket_stats_from_measurements(
        db,
        health_subject_id=subj.id,
        measurement_type="heart_rate",
        bucket_start=d_start,
        bucket_end=d_end,
    )
    assert rows.sample_count == 1
    assert rows.avg_value == 80.0


def test_c16_extreme_hr_not_silently_removed(db, family):
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 21, 12, 0, tzinfo=timezone.utc)
    days = {i: [68.0 + (i % 3)] for i in range(6)}
    d_start, _ = bucket_bounds("daily", ref=ref)
    days[0] = [40.0, 180.0]
    _seed_daily_hr(db, subj, dev, ref, days)
    computed = compute_personal_observed_baseline(db, health_subject_id=subj.id, ref=ref)
    assert 110.0 in computed.daily_medians


def test_c17_subject_isolation_baseline(db, family):
    father = family["father"]
    mother = create_managed_subject_without_account(
        db, account_user_id=family["javad"].id, display_name="Mother", access_role="CAREGIVER"
    )
    dev = family["device"]
    ref = datetime(2026, 12, 22, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, father, dev, ref, {i: [55.0] for i in range(7)})
    _seed_daily_hr(db, mother, dev, ref, {i: [95.0] for i in range(7)})
    f_row = upsert_personal_observed_baseline(db, subject=father, ref=ref)
    m_row = upsert_personal_observed_baseline(db, subject=mother, ref=ref)
    assert f_row.baseline_value == 55.0
    assert m_row.baseline_value == 95.0


def test_c18_caregiver_read_baselines_api(client, db, family, monkeypatch):
    from unittest.mock import patch
    from backend.app.services import auth_otp_service as svc

    javad = family["javad"]
    father = family["father"]
    monkeypatch.setenv("OTP_SECRET", "test_closure")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, javad.phone)
    token = client.post("/auth/verify_otp", json={"phone": javad.phone, "code": "123456"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.get(f"/health-subjects/{father.id}/vitals/baselines", headers=headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_c19_public_rebuild_route_removed(client, db, family, monkeypatch):
    from unittest.mock import patch
    from backend.app.services import auth_otp_service as svc

    javad = family["javad"]
    father = family["father"]
    monkeypatch.setenv("OTP_SECRET", "test_closure2")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, javad.phone)
    token = client.post("/auth/verify_otp", json={"phone": javad.phone, "code": "123456"}).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        f"/health-subjects/{father.id}/vitals/aggregates/rebuild",
        json={"measurement_type": "heart_rate", "bucket_kind": "daily", "ref": "2026-12-01T12:00:00+00:00"},
        headers=headers,
    )
    assert r.status_code == 404


def test_c20_internal_rebuild_service(db, family):
    father = family["father"]
    dev = family["device"]
    ref = datetime(2026, 12, 23, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, father, dev, ref, {i: [66.0] for i in range(7)})
    result = rebuild_subject_vitals_internal(db, subject=father, ref=ref)
    assert result["status"] == "PROVISIONAL"


def test_c21_i7_consent_and_managed_skip(db, family):
    from backend.app.services.i9.aggregation_service import rebuild_higher_bucket_from_daily_rollups

    user = family["javad"]
    subj = family["javad_subject"]
    dev = family["device"]
    ref = datetime(2026, 12, 24, 12, 0, tzinfo=timezone.utc)
    _seed_daily_hr(db, subj, dev, ref, {i: [77.0] for i in range(7)})
    rebuild_daily_bucket(db, subject=subj, measurement_type="heart_rate", ref=ref)
    rebuild_higher_bucket_from_daily_rollups(
        db, subject=subj, measurement_type="heart_rate", bucket_kind="weekly", ref=ref
    )
    assert produce_i7_pattern_from_latest_rollup(db, health_subject_id=subj.id)["status"] == "SKIPPED_NO_I6_WRITE_CONSENT"
    grant_memory_consent(db, user.id, permissions=(PERM_WRITE,), commit=True)
    written = produce_i7_pattern_from_latest_rollup(db, health_subject_id=subj.id)
    assert written["status"] == "WRITTEN"
    assert produce_i7_pattern_from_latest_rollup(db, health_subject_id=family["father"].id)["status"] == "SKIPPED_NO_LINKED_ACCOUNT"
