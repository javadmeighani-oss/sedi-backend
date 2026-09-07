"""Isolated SQLite session for I6/I7/I8 service tests. No Postgres required."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.database import Base


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    tables = [
        models.User.__table__,
        models.UserConsent.__table__,
        models.UserConsentScope.__table__,
        models.UserMemoryFact.__table__,
        models.UserPeriodSummary.__table__,
        models.UserLifelongProfile.__table__,
        models.UserMemoryExportJob.__table__,
        models.Memory.__table__,
        models.UserProfileCore.__table__,
    ]
    for name in (
        "UserProfileFact",
        "KcUserFact",
        "UserGoal",
        "UserRestriction",
        "UserHabit",
        "UserLifestyleEvent",
        "MedicalCondition",
        "UserCondition",
        "Medication",
        "UserMedication",
        "I8OperationalPlan",
        "I8OperationalPlanAction",
        "UserMemoryPurgeReceipt",
        "UserI7DerivedPattern",
    ):
        model = getattr(models, name, None)
        if model is not None and hasattr(model, "__table__"):
            tables.append(model.__table__)
    Base.metadata.create_all(engine, tables=tables)
    # I8 physiological projection requires HealthSubject tables; optional in this harness.
    monkeypatch.setattr(
        "backend.app.services.i8.context.get_i8_governed_context_projection",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "backend.app.services.i8.context.projection_context_refs",
        lambda *_a, **_k: [],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
