"""A3 G12 — i9_vital_observation_contexts schema scaffold (persistence only)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app import models
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.helpers.i10_postgresql_harness import (
    ALEMBIC_HEAD,
    I10IsolatedPgDb,
    _REV_085,
    _REV_086,
    pg_table_exists,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "086_i9_vital_observation_context_authority.py"
)


def test_g12_static_no_thresholds_or_seeds():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "INSERT INTO" not in src.upper()
    assert "i9_vital_observation_contexts" in src
    for token in ("37.5", "39.5", "TACHYCARDIA", "FEVER", "HYPOXEMIA"):
        assert token not in src
    for token in ("100", "60", "95", "50", "120", "38"):
        assert f"'{token}'" not in src
        assert f" {token} " not in src


def test_g12_static_alembic_single_head():
    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [_REV_086]
    assert ALEMBIC_HEAD == _REV_086
    assert script.get_revision(_REV_086).down_revision == _REV_085


def test_g12_static_no_runtime_wiring():
    """G12 schema only; G13 may wire persistence/load — still no routers/I10."""
    root = Path(__file__).resolve().parents[1] / "app"
    allowed = {
        "services/i9/vital_observation_context_persistence.py",
        "services/i9/vital_observation_context.py",
        "services/i9/device_packet_service.py",
    }
    hits = []
    for path in root.rglob("*.py"):
        if path.name in ("models.py",):
            continue
        text_src = path.read_text(encoding="utf-8")
        if "i9_vital_observation_contexts" in text_src or "I9VitalObservationContext" in text_src:
            rel = str(path.relative_to(root)).replace("\\", "/")
            if rel not in allowed:
                hits.append(rel)
    assert hits == [], f"unexpected runtime consumers: {hits}"


def test_g12_migration_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="g12mig086", revision=_REV_085)
    try:
        assert isolated.head() == _REV_085
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "i9_vital_observation_contexts")

        command.upgrade(isolated.cfg, _REV_086)
        assert isolated.head() == _REV_086
        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "i9_vital_observation_contexts")
            assert conn.execute(text("SELECT COUNT(*) FROM i9_vital_observation_contexts")).scalar_one() == 0
            cols = {
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='i9_vital_observation_contexts'
                        """
                    )
                )
            }
            for required in (
                "health_subject_id",
                "source_class",
                "source_row_id",
                "metric",
                "observed_at",
                "activity_state",
                "altitude_value",
                "altitude_unit",
                "temperature_method",
                "quality_state",
                "confirmation_state",
                "context_authority_json",
                "occurrence_key",
            ):
                assert required in cols
            # Existing tables unchanged by G12 (no new columns on them)
            hd_cols = {
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='health_data'
                        """
                    )
                )
            }
            assert "activity_state" not in hd_cols
            assert "quality_state" not in hd_cols

        command.downgrade(isolated.cfg, _REV_085)
        assert isolated.head() == _REV_085
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "i9_vital_observation_contexts")
            assert pg_table_exists(conn, "i9_absolute_vital_policies")

        command.upgrade(isolated.cfg, _REV_086)
        assert isolated.head() == _REV_086
    finally:
        isolated.close()


def test_g12_fk_idempotency_and_null_unknown_allowed():
    isolated = I10IsolatedPgDb.create(suffix="g12fk086", revision=_REV_086)
    Session = isolated.session_factory()
    db = Session()
    try:
        user = models.User(
            name="G12User",
            secret_key="k-g12",
            preferred_language="en",
            phone="+989191120001",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        subject = ensure_self_subject_for_account(db, user.id, commit=True)
        hd = models.HealthData(
            user_id=user.id,
            heart_rate="72",
            created_at=datetime.now(timezone.utc),
        )
        db.add(hd)
        db.commit()
        db.refresh(hd)

        now = datetime.now(timezone.utc)
        row = models.I9VitalObservationContext(
            health_subject_id=subject.id,
            source_class="LEGACY_HEALTHDATA",
            source_row_id=int(hd.id),
            health_data_id=hd.id,
            metric="heart_rate",
            observed_at=now,
            activity_state=None,
            altitude_value=None,
            altitude_unit=None,
            temperature_method=None,
            quality_state=None,
            confirmation_state=None,
            context_authority_json='{"note":"all_null_means_unknown"}',
            occurrence_key=f"i9:voc:LEGACY_HEALTHDATA:{hd.id}:heart_rate",
        )
        db.add(row)
        db.commit()

        # Missing HealthSubject rejected
        db.add(
            models.I9VitalObservationContext(
                health_subject_id=9_999_999,
                source_class="LEGACY_HEALTHDATA",
                source_row_id=int(hd.id) + 1,
                metric="spo2",
                observed_at=now,
                occurrence_key="i9:voc:bad-subject",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Occurrence idempotency
        db.add(
            models.I9VitalObservationContext(
                health_subject_id=subject.id,
                source_class="LEGACY_HEALTHDATA",
                source_row_id=int(hd.id),
                health_data_id=hd.id,
                metric="heart_rate",
                observed_at=now,
                occurrence_key=f"i9:voc:LEGACY_HEALTHDATA:{hd.id}:heart_rate",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # source_class+source_row_id+metric uniqueness
        db.add(
            models.I9VitalObservationContext(
                health_subject_id=subject.id,
                source_class="LEGACY_HEALTHDATA",
                source_row_id=int(hd.id),
                health_data_id=hd.id,
                metric="heart_rate",
                observed_at=now,
                occurrence_key="i9:voc:dup-source-metric",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        assert db.execute(text("SELECT COUNT(*) FROM i9_vital_observation_contexts")).scalar_one() == 1
    finally:
        db.close()
        isolated.close()
