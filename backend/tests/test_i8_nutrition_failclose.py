"""I8 ephemeral nutrition: fail-closed, no diagnosis, no new schema."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from types import SimpleNamespace

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_NO_ELIGIBLE_KNOWLEDGE, STATUS_OK
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import correct_fact, write_fact
from backend.app.services.i8.nutrition_planner import plan_nutrition


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key="i8-test", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _ok_retrieval(*_a, **_k):
    return SimpleNamespace(status=STATUS_OK, items=[object()])


def _empty_retrieval(*_a, **_k):
    return SimpleNamespace(status=STATUS_NO_ELIGIBLE_KNOWLEDGE, items=[])


def test_i8_unsafe_request_blocked():
    result = plan_nutrition(None, 1, "please diagnose me and increase dose")
    assert result.status == "UNSAFE_REQUEST_BLOCKED"
    assert result.plan is None
    assert result.grounded is False


def test_i8_insufficient_data(db):
    user = _user(db, "i8-insuf")
    grant_memory_consent(db, user.id, commit=True)
    result = plan_nutrition(db, user.id, "help me eat better")
    assert result.status == "INSUFFICIENT_DATA"
    assert result.plan is None


def test_i8_missing_eligible_knowledge(db, monkeypatch):
    user = _user(db, "i8-missing")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "iranian home cooking", commit=True)
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_planner.retrieve_knowledge_context",
        _empty_retrieval,
    )
    result = plan_nutrition(db, user.id, "suggest a friday meal")
    assert result.status == "STALE_OR_INELIGIBLE_KNOWLEDGE"
    assert result.grounded is False
    assert result.plan is None


def test_i8_stale_knowledge_fail_close(db, monkeypatch):
    user = _user(db, "i8-stale")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "food_habits", "rice and herbs", commit=True)
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_planner.retrieve_knowledge_context",
        lambda *_a, **_k: SimpleNamespace(status="STALE", items=[object()]),
    )
    result = plan_nutrition(db, user.id, "weeknight dinner")
    assert result.status == "STALE_OR_INELIGIBLE_KNOWLEDGE"
    assert result.grounded is False


def test_i8_sufficient_data_ephemeral_grounded(db, monkeypatch):
    user = _user(db, "i8-ok")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "iranian home cooking", commit=True)
    write_fact(db, user.id, "goals", "health_goals", "more vegetables", commit=True)
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_planner.retrieve_knowledge_context",
        _ok_retrieval,
    )
    result = plan_nutrition(db, user.id, "friday lunch ideas")
    assert result.status == "GROUNDED_EPHEMERAL"
    assert result.iran_first is True
    assert result.grounded is True
    assert result.plan is not None
    assert result.plan["persistence"] == "NONE"
    assert result.plan["clinical"] is False


def test_i8_user_correction_uses_current_facts(db, monkeypatch):
    user = _user(db, "i8-corr")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "vegetarian", commit=True)
    monkeypatch.setattr(
        "backend.app.services.i8.nutrition_planner.retrieve_knowledge_context",
        _ok_retrieval,
    )
    first = plan_nutrition(db, user.id, "dinner")
    assert first.status == "GROUNDED_EPHEMERAL"
    correct_fact(db, user.id, "lifestyle", "diet_notes", "pescatarian", commit=True)
    second = plan_nutrition(db, user.id, "dinner")
    assert second.status == "GROUNDED_EPHEMERAL"
    assert second.plan["persistence"] == "NONE"


def test_i8_consent_required(db):
    user = _user(db, "i8-consent")
    result = plan_nutrition(db, user.id, "meal ideas")
    assert result.status == "CONSENT_REQUIRED"
