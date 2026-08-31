"""I10-B09 migration 077 upgrade/downgrade/re-upgrade PostgreSQL validation."""

from __future__ import annotations

from alembic import command
from sqlalchemy import text

from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_076,
    _REV_077,
    pg_table_exists,
)


def test_migration_077_cycle_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="i10mig077", revision=_REV_076)
    try:
        assert isolated.head() == _REV_076
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "medication_dose_occurrences")

        command.upgrade(isolated.cfg, _REV_077)
        assert isolated.head() == _REV_077

        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "medication_dose_occurrences")

        command.downgrade(isolated.cfg, _REV_076)
        assert isolated.head() == _REV_076

        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "medication_dose_occurrences")

        command.upgrade(isolated.cfg, _REV_077)
        assert isolated.head() == _REV_077
    finally:
        isolated.close()
