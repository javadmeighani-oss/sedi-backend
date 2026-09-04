"""C04 migration 078 upgrade/downgrade/re-upgrade PostgreSQL validation."""

from __future__ import annotations

from alembic import command
from sqlalchemy import text

from backend.tests.helpers.i10_postgresql_harness import (
    I10IsolatedPgDb,
    _REV_077,
    _REV_078,
    pg_column_exists,
    pg_table_exists,
)


def test_migration_078_cycle_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="c04mig078", revision=_REV_077)
    try:
        assert isolated.head() == _REV_077
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "health_subject_conditions")
            assert not pg_column_exists(conn, "health_subjects", "creation_idempotency_key")

        command.upgrade(isolated.cfg, _REV_078)
        assert isolated.head() == _REV_078

        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "health_subject_conditions")
            assert pg_column_exists(conn, "health_subjects", "creation_idempotency_key")
            assert pg_column_exists(conn, "health_subjects", "created_by_account_user_id")

        command.downgrade(isolated.cfg, _REV_077)
        assert isolated.head() == _REV_077

        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "health_subject_conditions")

        command.upgrade(isolated.cfg, _REV_078)
        assert isolated.head() == _REV_078
        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "health_subject_conditions")
            ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert ver == _REV_078
    finally:
        isolated.close()
