"""Isolated SQLite session for I6/I7/I8 service tests. No Postgres required."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.database import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            models.User.__table__,
            models.UserConsent.__table__,
            models.UserConsentScope.__table__,
            models.UserMemoryFact.__table__,
            models.UserPeriodSummary.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
