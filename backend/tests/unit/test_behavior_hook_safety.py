"""
Unit tests: Behavior Layer V1 hook safety.
- When BEHAVIOR_V1_ENABLED is false, apply_behavior_to_question returns data unchanged.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def test_behavior_disabled_output_unchanged(db_session, behavior_user_id):
    """When BEHAVIOR_V1_ENABLED is false, apply_behavior_to_question returns the same dict (no lead-in)."""
    from unittest.mock import patch
    from backend.app.behavior.service import apply_behavior_to_question

    data = {
        "user_id": behavior_user_id,
        "question_type": "confirm_candidate",
        "text": "درست متوجه شدم داروی «متفورمین» مصرف می‌کنید؟",
        "options": ["بله، درسته", "نه"],
    }
    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=False):
        result = apply_behavior_to_question(db_session, behavior_user_id, data, "fa")
    assert result == data
    assert result["text"] == "درست متوجه شدم داروی «متفورمین» مصرف می‌کنید؟"


def test_behavior_disabled_no_lead_in_prepended(db_session, behavior_user_id):
    """When disabled, text is not prefixed with lead-in (deterministic check)."""
    from unittest.mock import patch
    from backend.app.behavior.service import apply_behavior_to_question
    from backend.app.behavior.texts_fa import get_lead_in

    data = {"question_type": "confirm_candidate", "text": "خوابت چطوره?"}
    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=False):
        result = apply_behavior_to_question(db_session, behavior_user_id, data, "fa")
    lead_in = get_lead_in("fa")
    assert not result["text"].startswith(lead_in)
    assert result["text"] == "خوابت چطوره?"


@pytest.fixture
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.database import Base
    import backend.app.models  # noqa: F401
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def behavior_user_id(db_session):
    from sqlalchemy import text
    uid = 70002
    db_session.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, datetime('now'))"
        ),
        {"id": uid, "name": "Hook Safety Test", "secret": "y", "lang": "fa"},
    )
    db_session.commit()
    return uid
