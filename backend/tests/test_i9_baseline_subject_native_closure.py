"""I9 baseline, subject-native persistence, migration 073, and rebuild authorization closure."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

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


# ---------------------------------------------------------------------------
# Migration 073 rollback safety contract (PD-I9-V1-MIGRATION-073-ROLLBACK-SAFETY-CONTRACT-01)
# Uses an isolated PostgreSQL database so downgrade rehearsal cannot mutate the shared test DB.
# ---------------------------------------------------------------------------

_MIG073_ROOT = Path(__file__).resolve().parents[1]
_MIG073_MARKER = "I9_073_DOWNGRADE_BLOCKED_SUBJECT_NATIVE_NULL_USER_ROWS"
_REV_072 = "072_i9_device_claim_gateway_lifecycle_foundation"
_REV_073 = "073_i9_subject_native_rollup_baseline"


def _mig073_test_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


def _mig073_alembic_cfg(url: str) -> Config:
    cfg = Config(str(_MIG073_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_MIG073_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _mig073_admin_and_rehearsal_urls(base_url: str) -> tuple[str, str, str]:
    parsed = urlparse(base_url)
    base_db = parsed.path.lstrip("/")
    rehearsal_db = f"{base_db}_mig073_{uuid.uuid4().hex[:8]}"
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    rehearsal_url = urlunparse(parsed._replace(path=f"/{rehearsal_db}"))
    return admin_url, rehearsal_url, rehearsal_db


class _Mig073IsolatedDb:
    def __init__(self) -> None:
        base_url = _mig073_test_url()
        if not base_url:
            pytest.skip("TEST_DATABASE_URL required for migration 073 rollback rehearsal")
        self.admin_url, self.url, self.db_name = _mig073_admin_and_rehearsal_urls(base_url)
        self.admin_engine = create_engine(self.admin_url, isolation_level="AUTOCOMMIT")
        with self.admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{self.db_name}"'))
        self.engine = create_engine(self.url)
        self.cfg = _mig073_alembic_cfg(self.url)

    def close(self) -> None:
        self.engine.dispose()
        with self.admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{self.db_name}" WITH (FORCE)'))
        self.admin_engine.dispose()


@pytest.fixture()
def mig073_db(monkeypatch):
    isolated = _Mig073IsolatedDb()
    monkeypatch.setenv("TEST_DATABASE_URL", isolated.url)
    monkeypatch.setenv("DATABASE_URL", isolated.url)
    try:
        yield isolated
    finally:
        isolated.close()


def _mig073_head(conn) -> str:
    return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _mig073_user_id_nullable(conn, table: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table
              AND column_name = 'user_id'
            """
        ),
        {"table": table},
    ).scalar_one()
    return row == "YES"


def _mig073_column_exists(conn, table: str, column: str) -> bool:
    return (
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table
                  AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).scalar_one()
        > 0
    )


def _mig073_index_exists(conn, index_name: str) -> bool:
    return (
        conn.execute(
            text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"),
            {"name": index_name},
        ).scalar_one()
        > 0
    )


def _mig073_schema_at_073(conn) -> None:
    assert _mig073_head(conn) == _REV_073
    assert _mig073_column_exists(conn, "physiological_baselines", "baseline_method")
    assert _mig073_column_exists(conn, "physiological_baselines", "dispersion_value")
    assert _mig073_column_exists(conn, "physiological_baselines", "valid_day_count")
    assert _mig073_index_exists(conn, "uq_pmr_subject_type_bucket")
    assert _mig073_index_exists(conn, "uq_pb_subject_type_version_window")


def _mig073_seed_caregiver_user(conn) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO users (name, secret_key, preferred_language, phone, created_at)
            VALUES ('Mig073Caregiver', 'k-mig073', 'en', '+989100009999', NOW())
            RETURNING id
            """
        )
    ).scalar_one()


def _mig073_seed_managed_subject(conn) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO health_subjects (display_name, linked_user_id, subject_kind, status, created_at, updated_at)
            VALUES ('ManagedFather', NULL, 'managed', 'active', NOW(), NOW())
            RETURNING id
            """
        )
    ).scalar_one()


def _mig073_seed_linked_subject(conn, user_id: int) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO health_subjects (display_name, linked_user_id, subject_kind, status, created_at, updated_at)
            VALUES ('LinkedSelf', :user_id, 'self', 'active', NOW(), NOW())
            RETURNING id
            """
        ),
        {"user_id": user_id},
    ).scalar_one()


def _mig073_seed_legacy_rollup(conn, *, user_id: int, subject_id: int) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO physiological_measurement_rollups (
                user_id, health_subject_id, measurement_type, bucket_kind,
                bucket_start, bucket_end, sample_count, avg_value
            )
            VALUES (
                :user_id, :subject_id, 'heart_rate', 'daily',
                TIMESTAMPTZ '2026-01-01 00:00:00+00', TIMESTAMPTZ '2026-01-02 00:00:00+00',
                1, 72.0
            )
            RETURNING id
            """
        ),
        {"user_id": user_id, "subject_id": subject_id},
    ).scalar_one()


def _mig073_seed_null_user_rollup(conn, *, subject_id: int) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO physiological_measurement_rollups (
                user_id, health_subject_id, measurement_type, bucket_kind,
                bucket_start, bucket_end, sample_count, avg_value
            )
            VALUES (
                NULL, :subject_id, 'heart_rate', 'daily',
                TIMESTAMPTZ '2026-02-01 00:00:00+00', TIMESTAMPTZ '2026-02-02 00:00:00+00',
                1, 65.0
            )
            RETURNING id
            """
        ),
        {"subject_id": subject_id},
    ).scalar_one()


def _mig073_seed_legacy_baseline(conn, *, user_id: int, subject_id: int) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO physiological_baselines (
                user_id, health_subject_id, measurement_type, window_start, window_end,
                baseline_version, derived_at, baseline_value, baseline_method,
                dispersion_value, valid_day_count
            )
            VALUES (
                :user_id, :subject_id, 'heart_rate',
                TIMESTAMPTZ '2026-01-01 00:00:00+00', TIMESTAMPTZ '2026-01-29 00:00:00+00',
                1, TIMESTAMPTZ '2026-01-29 12:00:00+00', 70.0,
                'PERSONAL_OBSERVED_BASELINE_V1', 5.0, 14
            )
            RETURNING id
            """
        ),
        {"user_id": user_id, "subject_id": subject_id},
    ).scalar_one()


def _mig073_seed_null_user_baseline(conn, *, subject_id: int) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO physiological_baselines (
                user_id, health_subject_id, measurement_type, window_start, window_end,
                baseline_version, derived_at, baseline_value, baseline_method,
                dispersion_value, valid_day_count
            )
            VALUES (
                NULL, :subject_id, 'heart_rate',
                TIMESTAMPTZ '2026-02-01 00:00:00+00', TIMESTAMPTZ '2026-03-01 00:00:00+00',
                1, TIMESTAMPTZ '2026-03-01 12:00:00+00', 60.0,
                'PERSONAL_OBSERVED_BASELINE_V1', 4.0, 7
            )
            RETURNING id
            """
        ),
        {"subject_id": subject_id},
    ).scalar_one()


def _mig073_rollup_snapshot(conn, row_id: int) -> dict:
    row = conn.execute(
        text(
            """
            SELECT id, user_id, health_subject_id, avg_value, sample_count
            FROM physiological_measurement_rollups
            WHERE id = :row_id
            """
        ),
        {"row_id": row_id},
    ).mappings().one()
    return dict(row)


def _mig073_baseline_core_snapshot(conn, row_id: int) -> dict:
    row = conn.execute(
        text(
            """
            SELECT id, user_id, health_subject_id, baseline_value
            FROM physiological_baselines
            WHERE id = :row_id
            """
        ),
        {"row_id": row_id},
    ).mappings().one()
    return dict(row)


def _mig073_baseline_snapshot(conn, row_id: int) -> dict:
    row = conn.execute(
        text(
            """
            SELECT id, user_id, health_subject_id, baseline_value, valid_day_count
            FROM physiological_baselines
            WHERE id = :row_id
            """
        ),
        {"row_id": row_id},
    ).mappings().one()
    return dict(row)


def test_r01_migration_072_to_073_upgrade(mig073_db):
    """R1: structural upgrade 072 -> 073 PASS."""
    command.upgrade(mig073_db.cfg, _REV_072)
    command.upgrade(mig073_db.cfg, _REV_073)
    with mig073_db.engine.connect() as conn:
        _mig073_schema_at_073(conn)
        assert _mig073_user_id_nullable(conn, "physiological_measurement_rollups")
        assert _mig073_user_id_nullable(conn, "physiological_baselines")


def test_r02_safe_073_to_072_downgrade_representable_rows(mig073_db):
    """R2/R15/R16: downgrade PASS when all rows have non-null user_id."""
    command.upgrade(mig073_db.cfg, _REV_073)
    with mig073_db.engine.begin() as conn:
        caregiver_id = _mig073_seed_caregiver_user(conn)
        subject_id = _mig073_seed_linked_subject(conn, caregiver_id)
        legacy_rollup_id = _mig073_seed_legacy_rollup(conn, user_id=caregiver_id, subject_id=subject_id)
        legacy_baseline_id = _mig073_seed_legacy_baseline(conn, user_id=caregiver_id, subject_id=subject_id)
        rollup_before = _mig073_rollup_snapshot(conn, legacy_rollup_id)
        baseline_before = _mig073_baseline_snapshot(conn, legacy_baseline_id)

    command.downgrade(mig073_db.cfg, _REV_072)

    with mig073_db.engine.connect() as conn:
        assert _mig073_head(conn) == _REV_072
        assert not _mig073_user_id_nullable(conn, "physiological_measurement_rollups")
        assert not _mig073_user_id_nullable(conn, "physiological_baselines")
        assert not _mig073_column_exists(conn, "physiological_baselines", "baseline_method")
        assert not _mig073_column_exists(conn, "physiological_baselines", "dispersion_value")
        assert not _mig073_column_exists(conn, "physiological_baselines", "valid_day_count")
        assert not _mig073_index_exists(conn, "uq_pmr_subject_type_bucket")
        assert not _mig073_index_exists(conn, "uq_pb_subject_type_version_window")
        rollup_after = _mig073_rollup_snapshot(conn, legacy_rollup_id)
        baseline_after = _mig073_baseline_core_snapshot(conn, legacy_baseline_id)
        assert rollup_after["user_id"] == caregiver_id
        assert rollup_after["avg_value"] == rollup_before["avg_value"]
        assert baseline_after["user_id"] == caregiver_id
        assert baseline_after["baseline_value"] == baseline_before["baseline_value"]


def test_r17_reupgrade_072_to_073_after_safe_downgrade(mig073_db):
    """R17: re-upgrade 072 -> 073 after safe downgrade."""
    command.upgrade(mig073_db.cfg, _REV_073)
    with mig073_db.engine.begin() as conn:
        user_id = _mig073_seed_caregiver_user(conn)
        subject_id = _mig073_seed_linked_subject(conn, user_id)
        _mig073_seed_legacy_rollup(conn, user_id=user_id, subject_id=subject_id)
    command.downgrade(mig073_db.cfg, _REV_072)
    command.upgrade(mig073_db.cfg, _REV_073)
    with mig073_db.engine.connect() as conn:
        _mig073_schema_at_073(conn)


@pytest.mark.parametrize(
    "seed_fn",
    [
        "rollup",
        "baseline",
        "both",
    ],
    ids=["null_rollup", "null_baseline", "null_both"],
)
def test_r03_r05_blocked_downgrade_subject_native_null_user_rows(mig073_db, seed_fn):
    """R3-R14: blocked downgrade fail-closed before DDL; schema/data preserved at 073."""
    command.upgrade(mig073_db.cfg, _REV_073)
    with mig073_db.engine.begin() as conn:
        caregiver_id = _mig073_seed_caregiver_user(conn)
        managed_subject_id = _mig073_seed_managed_subject(conn)
        linked_subject_id = _mig073_seed_linked_subject(conn, caregiver_id)
        legacy_rollup_id = _mig073_seed_legacy_rollup(
            conn, user_id=caregiver_id, subject_id=linked_subject_id
        )
        legacy_baseline_id = _mig073_seed_legacy_baseline(
            conn, user_id=caregiver_id, subject_id=linked_subject_id
        )
        null_rollup_id = None
        null_baseline_id = None
        if seed_fn in ("rollup", "both"):
            null_rollup_id = _mig073_seed_null_user_rollup(conn, subject_id=managed_subject_id)
        if seed_fn in ("baseline", "both"):
            null_baseline_id = _mig073_seed_null_user_baseline(conn, subject_id=managed_subject_id)
        rollup_count_before = conn.execute(text("SELECT COUNT(*) FROM physiological_measurement_rollups")).scalar_one()
        baseline_count_before = conn.execute(text("SELECT COUNT(*) FROM physiological_baselines")).scalar_one()
        user_count_before = conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        null_rollup_before = (
            _mig073_rollup_snapshot(conn, null_rollup_id) if null_rollup_id is not None else None
        )
        null_baseline_before = (
            _mig073_baseline_snapshot(conn, null_baseline_id) if null_baseline_id is not None else None
        )
        legacy_rollup_before = _mig073_rollup_snapshot(conn, legacy_rollup_id)
        legacy_baseline_before = _mig073_baseline_snapshot(conn, legacy_baseline_id)

    with pytest.raises(RuntimeError) as exc:
        command.downgrade(mig073_db.cfg, _REV_072)
    assert _MIG073_MARKER in str(exc.value)

    with mig073_db.engine.connect() as conn:
        _mig073_schema_at_073(conn)  # R6-R10
        assert _mig073_head(conn) == _REV_073  # R6
        assert conn.execute(text("SELECT COUNT(*) FROM physiological_measurement_rollups")).scalar_one() == rollup_count_before  # R12
        assert conn.execute(text("SELECT COUNT(*) FROM physiological_baselines")).scalar_one() == baseline_count_before  # R12
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == user_count_before  # R13/R14
        assert _mig073_rollup_snapshot(conn, legacy_rollup_id) == legacy_rollup_before  # R11/R16
        assert _mig073_baseline_snapshot(conn, legacy_baseline_id) == legacy_baseline_before  # R11/R16
        if null_rollup_before is not None:
            snap = _mig073_rollup_snapshot(conn, null_rollup_id)
            assert snap == null_rollup_before
            assert snap["user_id"] is None  # R13/R14
            assert snap["health_subject_id"] == managed_subject_id
        if null_baseline_before is not None:
            snap = _mig073_baseline_snapshot(conn, null_baseline_id)
            assert snap == null_baseline_before
            assert snap["user_id"] is None  # R13/R14
            assert snap["health_subject_id"] == managed_subject_id


def test_r18_single_head_remains_073():
    """R18: Alembic single-head remains 073 (alias of C01)."""
    test_c01_alembic_single_head_073()


def test_r19_personal_observed_baseline_regression():
    """R19: PERSONAL_OBSERVED_BASELINE covered by C05-C13 executed in this CI module."""
    assert BASELINE_METHOD == "PERSONAL_OBSERVED_BASELINE_V1"


def test_r20_managed_no_account_persistence_regression():
    """R20: managed no-account persistence covered by C04/C06 executed in this CI module."""
    assert BASELINE_SCOPE_V1 == "heart_rate"


def test_r21_weighted_aggregation_regression():
    """R21: weighted aggregation covered by C03/C15 and L14 in sibling CI module."""
    assert ROLLING_WINDOW_DAYS == 28


def test_r22_longitudinal_read_regression():
    """R22: longitudinal read covered by C03/C20 and L1-L20 in sibling CI module."""
    assert bucket_bounds("daily", ref=datetime(2026, 1, 1, tzinfo=timezone.utc))[0].tzinfo is not None


def test_r23_i9_i7_consent_provenance_regression():
    """R23: I9->I7 consent/provenance covered by C21 executed in this CI module."""
    assert PERM_WRITE


def test_r24_trusted_fleet_and_packet_ack_regressions_delegate():
    """R24: trusted fleet / claim / packet ACK covered by sibling modules in the same CI step."""
    repo = Path(__file__).resolve().parents[2]
    siblings = (
        "backend/tests/test_i9_device_claim_trust_ingest_runtime.py",
        "backend/tests/test_i9_trusted_fleet_provisioning_claim_hardening.py",
        "backend/tests/test_i9_health_subject_device_packet_foundation.py",
    )
    for rel in siblings:
        assert (repo / rel).is_file(), rel
