# tests/test_user_context_service.py
"""
Tests for Stage 23 Step 1 - UserContextService (read-only context pack).
"""

import pytest
from datetime import datetime, timedelta

from app.database import Base, engine, SessionLocal
from app.models import User, UserProfileKnowledge, UserMemoryFact, DailyMemorySummary

# Import service; may use backend.app or app depending on runtime
try:
    from backend.app.services.user_context import UserContextService, UserContextPack
except ImportError:
    from app.services.user_context import UserContextService, UserContextPack


@pytest.fixture
def db():
    """Database session fixture."""
    Base.metadata.create_all(bind=engine)
    session = next(SessionLocal())
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db):
    """Create test user."""
    user = User(name="ContextTest", secret_key="sk", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_get_user_context_returns_pack_with_user_id(db, test_user):
    """get_user_context returns a UserContextPack with correct user_id and does not crash when optional sources are missing."""
    svc = UserContextService(db)
    pack = svc.get_user_context(test_user.id)
    assert isinstance(pack, UserContextPack)
    assert pack.user_id == test_user.id
    assert pack.preferred_name is None or isinstance(pack.preferred_name, str)
    assert pack.quiet_hours is not None
    assert pack.lifestyle is not None
    assert pack.source_meta is not None


def test_get_user_context_empty_data_does_not_crash(db, test_user):
    """With no profile/facts/summaries, pack still returned with defaults."""
    svc = UserContextService(db)
    pack = svc.get_user_context(test_user.id)
    assert pack.user_id == test_user.id
    assert pack.daily_memory_summary is None
    assert pack.verified_facts == {}
    assert pack.goals is None or pack.goals.items == []


def test_get_user_context_quiet_hours_from_user_memory_fact(db, test_user):
    """When UserMemoryFact has preferences.quiet_hours, pack contains quiet_hours."""
    fact = UserMemoryFact(
        user_id=test_user.id,
        domain="preferences",
        key="quiet_hours",
        value_json='{"start": "22:00", "end": "08:00"}',
        confidence=0.9,
        source="manual",
    )
    db.add(fact)
    db.commit()

    svc = UserContextService(db)
    pack = svc.get_user_context(test_user.id)
    assert pack.quiet_hours is not None
    assert pack.quiet_hours.start == "22:00"
    assert pack.quiet_hours.end == "08:00"


def test_get_user_context_preferred_name_from_profile(db, test_user):
    """When UserProfileKnowledge has display_name, preferred_name is set."""
    profile = UserProfileKnowledge(
        user_id=test_user.id,
        display_name="Ali",
        language="fa",
        baseline_summary="",
    )
    db.add(profile)
    db.commit()

    svc = UserContextService(db)
    pack = svc.get_user_context(test_user.id)
    assert pack.preferred_name == "Ali"
    assert pack.language == "fa"


def test_get_user_context_daily_memory_summary_latest(db, test_user):
    """When DailyMemorySummary exists, daily_memory_summary is latest summary text."""
    old = DailyMemorySummary(
        user_id=test_user.id,
        summary="Old day summary.",
        created_at=datetime.utcnow() - timedelta(days=2),
    )
    new = DailyMemorySummary(
        user_id=test_user.id,
        summary="Latest day summary.",
        created_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(old)
    db.add(new)
    db.commit()

    svc = UserContextService(db)
    pack = svc.get_user_context(test_user.id)
    assert pack.daily_memory_summary == "Latest day summary."


def test_get_user_context_nonexistent_user_returns_pack(db):
    """Non-existent user_id still returns a pack (no crash); caller may validate user_id separately."""
    svc = UserContextService(db)
    pack = svc.get_user_context(999999)
    assert pack.user_id == 999999
    assert pack.preferred_name is None
    assert pack.daily_memory_summary is None
