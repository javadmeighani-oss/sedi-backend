# backend/tests/conftest.py
import os
import sys
from pathlib import Path

import backend.app as backend_app

# Temporary namespace alias for transitional architecture
sys.modules["app"] = backend_app

# Remove legacy app/ path from sys.path to avoid importing both app.* and backend.app.*
_repo = Path(__file__).resolve().parents[2]
_legacy_app_path = str(_repo / "app")
sys.path = [p for p in sys.path if p != _legacy_app_path]

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from backend.app.database import Base, get_db as _app_get_db
from backend.app.main import app as sedi_app


def _import_all_models() -> None:
    """
    Ensure SQLAlchemy models are imported so they register on Base.metadata
    before Base.metadata.create_all() runs in tests.
    """
    import backend.app.models  # noqa: F401


def _mask_db_url(url: str) -> str:
    """Mask password part in URLs like scheme://user:pass@host:port/db."""
    if not url:
        return url
    at = url.find("@")
    if at == -1:
        return url
    before_at = url[:at]
    after_at = url[at:]
    colon_after_scheme = url.find("//") + 2 if "//" in url else 0
    creds = before_at[colon_after_scheme:]
    if ":" in creds:
        user, _ = creds.split(":", 1)
        masked_creds = user + ":***"
        return url[:colon_after_scheme] + masked_creds + after_at
    return url


def _get_db_url() -> str:
    test_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if test_url:
        print("[tests] using TEST_DATABASE_URL=" + _mask_db_url(test_url))
        return test_url

    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        lower = url.lower()
        if any(x in lower for x in ("sedi_db", "prod", "production")):
            raise RuntimeError(
                "Refusing to run tests against production-like DATABASE_URL. "
                "Set TEST_DATABASE_URL to a safe test database."
            )
        print("[tests] using DATABASE_URL=" + _mask_db_url(url))
        return url

    fallback = "postgresql://postgres:postgres@localhost:5432/postgres"
    print("[tests] using fallback DB URL=" + _mask_db_url(fallback))
    return fallback


# Single shared test engine for the whole pytest session (fast + consistent)
_TEST_ENGINE = create_engine(_get_db_url(), future=True)

_TestSession = sessionmaker(
    bind=_TEST_ENGINE,
    autoflush=False,
    autocommit=False,
    future=True,
)


@pytest.fixture(scope="session", autouse=True)
def _create_drop_all():
    """
    Create tables once for the full test session.
    Most tests assume clean DB; they should clean up their own inserted rows.
    If a test needs full isolation, it can use its own transaction/rollback.
    """
    _import_all_models()
    Base.metadata.create_all(bind=_TEST_ENGINE)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=_TEST_ENGINE)


@pytest.fixture()
def db():
    connection = _TEST_ENGINE.connect()
    transaction = connection.begin()

    session = _TestSession(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    sedi_app.dependency_overrides[_app_get_db] = _override_get_db
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)
