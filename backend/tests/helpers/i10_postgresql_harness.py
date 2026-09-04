"""I10 PostgreSQL validation harness — isolated disposable DB + Alembic (B04)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

_ALEMBIC_ROOT = Path(__file__).resolve().parents[2]
_REV_073 = "073_i9_subject_native_rollup_baseline"
_REV_074 = "074_i10_notification_domain_foundation"
_REV_075 = "075_i10_care_network_identity_grants"
_REV_076 = "076_i10_care_network_delivery_foundation"
_REV_077 = "077_i10_medication_adherence_foundation"
_REV_078 = "078_health_subject_condition_foundation"


def i10_test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


def i10_alembic_cfg(url: str) -> Config:
    cfg = Config(str(_ALEMBIC_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ALEMBIC_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def i10_admin_and_isolated_urls(base_url: str, *, suffix: str) -> tuple[str, str, str]:
    parsed = urlparse(base_url)
    base_db = parsed.path.lstrip("/")
    isolated_db = f"{base_db}_{suffix}_{uuid.uuid4().hex[:8]}"
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    isolated_url = urlunparse(parsed._replace(path=f"/{isolated_db}"))
    return admin_url, isolated_url, isolated_db


@dataclass
class I10IsolatedPgDb:
    url: str
    db_name: str
    engine: object
    cfg: Config
    admin_engine: object

    @classmethod
    def create(cls, *, suffix: str, revision: str | None = None) -> I10IsolatedPgDb:
        base_url = i10_test_database_url()
        if not base_url:
            pytest.skip("TEST_DATABASE_URL required for I10 PostgreSQL validation")
        admin_url, url, db_name = i10_admin_and_isolated_urls(base_url, suffix=suffix)
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        engine = create_engine(url, future=True)
        cfg = i10_alembic_cfg(url)
        os.environ["DATABASE_URL"] = url
        os.environ["TEST_DATABASE_URL"] = url
        target = revision or _REV_078
        command.upgrade(cfg, target)
        return cls(
            url=url,
            db_name=db_name,
            engine=engine,
            cfg=cfg,
            admin_engine=admin_engine,
        )

    def close(self) -> None:
        self.engine.dispose()
        with self.admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{self.db_name}" WITH (FORCE)'))
        self.admin_engine.dispose()

    def head(self) -> str:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    def session_factory(self) -> sessionmaker:
        return sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(scope="module")
def i10_pg_db_module():
    """Module-scoped Alembic-head PostgreSQL DB for I10 B01 runtime tests."""
    isolated = I10IsolatedPgDb.create(suffix="i10b01", revision=_REV_078)
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture()
def db(i10_pg_db_module):
    SessionLocal, isolated = i10_pg_db_module
    connection = isolated.engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def pg_column_exists(conn, table: str, column: str) -> bool:
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


def pg_table_exists(conn, table: str) -> bool:
    return (
        conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table
                """
            ),
            {"table": table},
        ).scalar_one()
        > 0
    )


def pg_index_exists(conn, index_name: str) -> bool:
    return (
        conn.execute(
            text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"),
            {"name": index_name},
        ).scalar_one()
        > 0
    )
