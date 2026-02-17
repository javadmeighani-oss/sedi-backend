"""
Pytest conftest: ensure backend.app resolves; disable scheduler in tests; alias app.* to backend.app.*.
Session fixture: run Alembic upgrade on test DB so schema exists (fixes relation 'users' does not exist).
"""
import os
import sys
import importlib
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command

# Before any app/backend.app import: disable scheduler and set test env
os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "true")
os.environ.setdefault("ENV", "test")

# backend project root = folder containing tests/ and backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Alias app.* to backend.app.* so SQLAlchemy tables are not defined twice
sys.modules.setdefault("app", importlib.import_module("backend.app"))
sys.modules.setdefault("app.models", importlib.import_module("backend.app.models"))
sys.modules.setdefault("app.main", importlib.import_module("backend.app.main"))
sys.modules.setdefault("app.core", importlib.import_module("backend.app.core"))
sys.modules.setdefault("app.core.scheduler", importlib.import_module("backend.app.core.scheduler"))


def _get_test_db_url() -> str:
    return (
        os.getenv("TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/sedi_test"
    )


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    """
    Ensures schema exists in test DB (fixes: relation 'users' does not exist).
    Runs alembic upgrade head once per test session.
    """
    db_url = _get_test_db_url()
    engine = create_engine(db_url, future=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def db():
    """SQLAlchemy session for tests."""
    db_url = _get_test_db_url()
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


if os.environ.get("PYTEST_DEBUG_IMPORTS"):
    try:
        import backend
        print(f"[conftest] backend.__file__ = {getattr(backend, '__file__', 'N/A')}")
    except ImportError:
        print("[conftest] backend import failed")
