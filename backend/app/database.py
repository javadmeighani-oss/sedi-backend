# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

from backend.app.core.capacity_budget import (
    resolve_max_overflow,
    resolve_pool_recycle,
    resolve_pool_size,
    resolve_pool_timeout,
)

# بارگذاری متغیرهای محیطی
load_dotenv()

# دریافت DATABASE_URL از environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://sedi_user:sedi_password@localhost:5432/sedi_db"
)

_POOL_SIZE, _POOL_SIZE_SRC = resolve_pool_size()
_MAX_OVERFLOW, _MAX_OVERFLOW_SRC = resolve_max_overflow()
_POOL_RECYCLE, _POOL_RECYCLE_SRC = resolve_pool_recycle()
_POOL_TIMEOUT, _POOL_TIMEOUT_SRC = resolve_pool_timeout()

# ایجاد engine برای PostgreSQL — pool env-configurable; defaults unchanged (5/10).
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # بررسی اتصال قبل از استفاده
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    pool_recycle=_POOL_RECYCLE,
    pool_timeout=_POOL_TIMEOUT,
)

SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def pool_config_snapshot() -> dict:
    """Non-secret pool config for capacity observability / tests."""
    return {
        "pool_size": _POOL_SIZE,
        "pool_size_source": _POOL_SIZE_SRC,
        "max_overflow": _MAX_OVERFLOW,
        "max_overflow_source": _MAX_OVERFLOW_SRC,
        "pool_recycle": _POOL_RECYCLE,
        "pool_recycle_source": _POOL_RECYCLE_SRC,
        "pool_timeout": _POOL_TIMEOUT,
        "pool_timeout_source": _POOL_TIMEOUT_SRC,
        "pool_pre_ping": True,
    }


def SessionLocal():
    """Generator-style session (tests expect: next(SessionLocal()))."""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def get_db():
    yield from SessionLocal()
