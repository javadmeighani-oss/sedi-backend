# tests/test_lifestyle_fact_extractor.py
"""
Unit tests for Stage 17.1 - Lifestyle fact extraction (deterministic patterns).
"""

import pytest

from backend.app.services.lifestyle.fact_extractor import (
    extract_candidates_from_turn,
    CandidateFact,
    _normalize_value,
)


def test_extract_sleep_duration_en():
    """English: I sleep about 7 hours"""
    candidates = extract_candidates_from_turn(
        user_id=1,
        user_message="I sleep about 7 hours",
        assistant_message="",
        language="en",
    )
    assert len(candidates) >= 1
    sleep = next((c for c in candidates if c.key == "sleep_duration_hours"), None)
    assert sleep is not None
    assert sleep.value == 7.0
    assert sleep.is_explicit is True
    assert sleep.confidence >= 0.85


def test_extract_steps_en():
    """English: I walked 5000 steps"""
    candidates = extract_candidates_from_turn(
        user_id=1,
        user_message="I walked 5000 steps today",
        assistant_message="",
        language="en",
    )
    assert len(candidates) >= 1
    steps = next((c for c in candidates if c.key == "steps_count"), None)
    assert steps is not None
    assert steps.value == 5000


def test_extract_mood_en():
    """English: I feel good"""
    candidates = extract_candidates_from_turn(
        user_id=1,
        user_message="I feel good today",
        assistant_message="",
        language="en",
    )
    assert len(candidates) >= 1
    mood = next((c for c in candidates if c.key == "mood"), None)
    assert mood is not None
    assert "good" in str(mood.value).lower()


def test_extract_empty_turn():
    """Empty turn returns no candidates"""
    candidates = extract_candidates_from_turn(1, "", "", "en")
    assert candidates == []


def test_normalize_sleep_duration():
    assert _normalize_value("sleep_duration_hours", "7") == 7.0
    assert _normalize_value("sleep_duration_hours", "7.5") == 7.5
    assert _normalize_value("sleep_duration_hours", "25") is None


def test_normalize_steps():
    assert _normalize_value("steps_count", "5000") == 5000
    assert _normalize_value("exercise_minutes", "30") == 30
