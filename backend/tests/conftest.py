# backend/tests/conftest.py
import os
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


def _get_db_url() -> str:
    return (
        os.getenv("TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/postgres"
    )


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
    session = _TestSession()
    try:
        yield session
        session.commit()
    finally:
        session.close()


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
