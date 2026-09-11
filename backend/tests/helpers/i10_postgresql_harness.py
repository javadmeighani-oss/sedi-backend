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
_REV_060 = "060_db03_w4_w6_scale_inspect_roles"
_REV_061 = "061_scis01_pgvector_kce_foundation"
_REV_073 = "073_i9_subject_native_rollup_baseline"
_REV_074 = "074_i10_notification_domain_foundation"
_REV_075 = "075_i10_care_network_identity_grants"
_REV_076 = "076_i10_care_network_delivery_foundation"
_REV_077 = "077_i10_medication_adherence_foundation"
_REV_078 = "078_health_subject_condition_foundation"
_REV_079 = "079_i10_cni_owner_provenance_nullable"
_REV_080 = "080_i9_device_reported_vital_status"
_REV_081 = "081_self_health_subject_1to1_hardening"
_REV_082 = "082_sedi_intro_completed_at"
_REV_083 = "083_otp_purpose_phone_change"
ALEMBIC_HEAD = _REV_083


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


def _vector_extension_available(conn) -> bool:
    try:
        row = conn.execute(
            text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).first()
        return row is not None
    except Exception:
        return False


def _apply_soft_061(engine) -> None:
    """Apply 061 semantics without pgvector (BYTEA stand-in). Engagement certs do not use RAG."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE knowledge_chunk_embeddings DROP CONSTRAINT IF EXISTS ck_kce_backend_kind_vocab")
        )
        conn.execute(
            text(
                """
                ALTER TABLE knowledge_chunk_embeddings
                  ADD CONSTRAINT ck_kce_backend_kind_vocab
                  CHECK (backend_kind IS NULL OR backend_kind IN (
                    'JSON_INLINE', 'EXTERNAL_VECTOR_DEFERRED', 'PGVECTOR'
                  ))
                """
            )
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS embedding_vector BYTEA")
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(64)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS embedding_model_version VARCHAR(64)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS chunker_version VARCHAR(64)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS chunk_version INTEGER DEFAULT 1 NOT NULL"
            )
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS section_path TEXT")
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS content_language VARCHAR(16)"
            )
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS search_document TEXT")
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunk_embeddings ADD COLUMN IF NOT EXISTS search_tsv tsvector")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_kce_search_tsv ON knowledge_chunk_embeddings USING gin (search_tsv)"
            )
        )


def _upgrade_with_optional_soft_vector(cfg: Config, engine, target: str) -> str:
    soft = (os.environ.get("SEDI_I10_SOFT_VECTOR_STUB") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    with engine.connect() as conn:
        vector_ok = _vector_extension_available(conn)
    if vector_ok or not soft:
        command.upgrade(cfg, target)
        return "REAL_VECTOR" if vector_ok else "FULL_UPGRADE"

    command.upgrade(cfg, _REV_060)
    _apply_soft_061(engine)
    command.stamp(cfg, _REV_061)
    command.upgrade(cfg, target)
    return "SOFT_BYTEA_STUB"


@dataclass
class I10IsolatedPgDb:
    url: str
    db_name: str
    engine: object
    cfg: Config
    admin_engine: object
    vector_mode: str = "UNKNOWN"

    @classmethod
    def create(cls, *, suffix: str, revision: str | None = None) -> I10IsolatedPgDb:
        # Preserve the original service URL across sequential creates. create() rewrites
        # TEST_DATABASE_URL to the isolated DB; without a pinned base, suffixes nest and
        # CREATE DATABASE names collide / exceed limits.
        base_key = "SEDI_I10_HARNESS_BASE_DATABASE_URL"
        base_url = os.environ.get(base_key) or i10_test_database_url()
        if not base_url:
            pytest.skip("TEST_DATABASE_URL required for I10 PostgreSQL validation")
        os.environ.setdefault(base_key, base_url)
        admin_url, url, db_name = i10_admin_and_isolated_urls(base_url, suffix=suffix)
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        engine = create_engine(url, future=True)
        cfg = i10_alembic_cfg(url)
        os.environ["DATABASE_URL"] = url
        os.environ["TEST_DATABASE_URL"] = url
        target = revision or ALEMBIC_HEAD
        vector_mode = _upgrade_with_optional_soft_vector(cfg, engine, target)
        return cls(
            url=url,
            db_name=db_name,
            engine=engine,
            cfg=cfg,
            admin_engine=admin_engine,
            vector_mode=vector_mode,
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
    isolated = I10IsolatedPgDb.create(suffix="i10b01", revision=ALEMBIC_HEAD)
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
