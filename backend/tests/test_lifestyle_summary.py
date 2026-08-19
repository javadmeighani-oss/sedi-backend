# tests/test_lifestyle_summary.py
"""
Tests for Stage 17.3 - Lifestyle summary sources (explainability).
Asserts sources exist for What I know and Recent patterns when data is present.
"""

import pytest
from datetime import datetime, timedelta

from backend.app.models import User, UserProfileKnowledge, UserMemoryFact, DailyMemorySummary, UserFact
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.lifestyle.summary_service import generate_summary


@pytest.fixture
def test_user(db):
    """Create test user"""
    user = User(name="SummaryTest", secret_key="sk", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_summary_what_i_know_has_sources_when_profile_exists(db, test_user):
    """When UserProfileKnowledge exists, What I know section has sources."""
    profile = UserProfileKnowledge(
        user_id=test_user.id,
        baseline_summary="User likes morning walks",
        goals_json='["exercise daily"]',
        preferences_json="{}",
    )
    db.add(profile)
    db.commit()

    data = generate_summary(db, test_user.id, language="en")
    sections = {s["title"]: s for s in data["sections"]}
    what_i_know = sections.get("What I know") or sections.get("آنچه می‌دانم")
    assert what_i_know is not None
    sources = what_i_know.get("sources")
    assert sources is not None
    assert len(sources) >= 1
    assert any(s.get("type") == "user_profile_knowledge" for s in sources)


def test_summary_what_i_know_has_sources_when_memory_facts_exist(db, test_user):
    """When UserMemoryFact exists, What I know section has sources."""
    grant_memory_consent(db, test_user.id, commit=True)
    fact = UserMemoryFact(
        user_id=test_user.id,
        domain="lifestyle",
        key="sleep_duration_hours",
        value_json="7.0",
        confidence=0.9,
        source="chat",
    )
    db.add(fact)
    db.commit()

    data = generate_summary(db, test_user.id, language="en")
    sections = {s["title"]: s for s in data["sections"]}
    what_i_know = sections.get("What I know") or sections.get("آنچه می‌دانم")
    assert what_i_know is not None
    sources = what_i_know.get("sources")
    assert sources is not None
    assert len(sources) >= 1
    assert any(s.get("type") == "user_memory_fact" for s in sources)


def test_summary_recent_patterns_has_sources_when_daily_summaries_exist(db, test_user):
    """When DailyMemorySummary exists, Recent patterns section has sources."""
    summary_row = DailyMemorySummary(
        user_id=test_user.id,
        summary="User slept well and walked 5000 steps.",
        mood="good",
        created_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(summary_row)
    db.commit()

    data = generate_summary(db, test_user.id, language="en")
    sections = {s["title"]: s for s in data["sections"]}
    recent = sections.get("Recent patterns") or sections.get("الگوهای اخیر") or sections.get("الأنماط الأخيرة")
    assert recent is not None
    sources = recent.get("sources")
    assert sources is not None
    assert len(sources) >= 1
    assert any(s.get("type") == "daily_summary" for s in sources)


def test_summary_sources_backward_compatible_empty_data(db, test_user):
    """With no data, sections still exist; sources may be empty (backward compatible)."""
    data = generate_summary(db, test_user.id, language="en")
    assert "sections" in data
    assert len(data["sections"]) >= 2
    # sources field is optional; clients can ignore
    for s in data["sections"]:
        assert "title" in s
        assert "body" in s