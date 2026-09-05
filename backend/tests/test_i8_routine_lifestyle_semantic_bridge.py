"""I8 routine/lifestyle semantic bridge — Gate2 habits/events → I8TrustedContext → compose."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i8.context import (
    GATE2_LIFESTYLE_EVENT_LIST_LIMIT,
    load_trusted_context,
)
from backend.app.services.i8.knowledge_bridge import (
    build_personalization,
    compose_grounded_action,
)
from backend.app.services.i8.unified_core import generate_operational_action


@pytest.fixture(scope="session")
def _bridge_tables_present():
    url = os.environ.get("TEST_DATABASE_URL")
    assert url, "TEST_DATABASE_URL required"
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        assert engine.dialect.name == "postgresql", engine.dialect.name
        missing = [
            table
            for table in ("user_habits", "user_lifestyle_events", "i8_operational_plans")
            if not insp.has_table(table)
        ]
        assert not missing, f"missing tables after migrate: {missing}"
    finally:
        engine.dispose()


@pytest.fixture()
def db(_bridge_tables_present):
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_engine(url)
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _profile_tz(db, user_id: int) -> None:
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


def _habit(
    db,
    user_id: int,
    *,
    name: str,
    status: str = "active",
    valid_to=None,
    frequency: str = "daily",
    target=None,
    updated_at=None,
):
    now = datetime.utcnow()
    row = models.UserHabit(
        user_id=user_id,
        name=name,
        frequency=frequency,
        target_json=json.dumps(target) if target is not None else None,
        status=status,
        source="manual",
        notes="secret notes must not leak",
        valid_to=valid_to,
        created_at=now,
        updated_at=updated_at or now,
    )
    db.add(row)
    db.flush()
    return row


def _lifestyle(
    db,
    user_id: int,
    *,
    event_type: str,
    occurred_at=None,
    value=None,
    value_raw: str | None = None,
):
    now = datetime.utcnow()
    row = models.UserLifestyleEvent(
        user_id=user_id,
        event_type=event_type,
        value_json=value_raw if value_raw is not None else (json.dumps(value) if value is not None else None),
        occurred_at=occurred_at or now,
        source="manual",
        notes="notes must not leak",
        created_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _ok_item(*, statement: str = "Keep a steady daily movement pattern") -> RetrievedKnowledgeItem:
    return RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="KU-ROUTINE-1",
        immutable_version_id="v1",
        memory_item_id="m1",
        memory_row_id=1,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=None,
        domain="lifestyle",
        language="en",
        topic_taxonomy=None,
        normalized_statement=statement,
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )


def _ok_retrieval(*_a, **_k):
    return SimpleNamespace(status=STATUS_OK, items=[_ok_item()])


# --- Habits ---


def test_a_valid_son_habit_loaded(db):
    son = _user(db, "son-habit")
    h = _habit(db, son.id, name="daily walk")
    ctx = load_trusted_context(db, son.id)
    assert len(ctx.habits) == 1
    assert ctx.habits[0].name == "daily walk"
    assert ctx.habits[0].habit_id == h.id
    assert ctx.habits[0].frequency == "daily"
    assert all("notes" not in str(f) for f in ctx.habits)


def test_b_expired_habit_excluded(db):
    son = _user(db, "son-exp")
    _habit(db, son.id, name="old habit", valid_to=datetime.utcnow() - timedelta(days=1))
    ctx = load_trusted_context(db, son.id)
    assert ctx.habits == []


def test_c_inactive_habit_excluded(db):
    son = _user(db, "son-inact")
    _habit(db, son.id, name="inactive habit", status="inactive")
    _habit(db, son.id, name="completed habit", status="completed")
    _habit(db, son.id, name="paused habit", status="paused")
    ctx = load_trusted_context(db, son.id)
    names = {h.name for h in ctx.habits}
    assert "inactive habit" not in names
    assert "completed habit" not in names
    assert "paused habit" in names


def test_d_another_users_habit_excluded(db):
    son = _user(db, "son-iso")
    other = _user(db, "other-iso")
    _habit(db, other.id, name="other walk")
    _habit(db, son.id, name="son walk")
    ctx = load_trusted_context(db, son.id)
    assert [h.name for h in ctx.habits] == ["son walk"]


def test_e_habit_context_ref_present(db):
    son = _user(db, "son-ref")
    h = _habit(db, son.id, name="hydrate")
    ctx = load_trusted_context(db, son.id)
    assert {"ref_type": "user_habit", "ref_id": h.id} in ctx.context_refs


def test_f_habit_target_bounded(db):
    son = _user(db, "son-tgt")
    _habit(db, son.id, name="steps", target={"target": "8000", "extra": "x" * 500})
    ctx = load_trusted_context(db, son.id)
    assert ctx.habits[0].target_compact == "8000"
    assert len(ctx.habits[0].target_compact) <= 64


# --- Lifestyle ---


def test_g_son_lifestyle_event_loaded(db):
    son = _user(db, "son-life")
    ev = _lifestyle(db, son.id, event_type="sleep", value={"hours": 7})
    ctx = load_trusted_context(db, son.id)
    assert len(ctx.lifestyle_events) == 1
    assert ctx.lifestyle_events[0].event_type == "sleep"
    assert ctx.lifestyle_events[0].event_id == ev.id
    assert ctx.lifestyle_events[0].value_compact == "7"


def test_h_cross_user_lifestyle_excluded(db):
    son = _user(db, "son-life-iso")
    other = _user(db, "other-life-iso")
    _lifestyle(db, other.id, event_type="hydration")
    _lifestyle(db, son.id, event_type="sleep")
    ctx = load_trusted_context(db, son.id)
    assert [e.event_type for e in ctx.lifestyle_events] == ["sleep"]


def test_i_lifestyle_bound_and_order(db):
    son = _user(db, "son-bound")
    base = datetime.utcnow()
    rows = []
    for i in range(GATE2_LIFESTYLE_EVENT_LIST_LIMIT + 5):
        rows.append(
            models.UserLifestyleEvent(
                user_id=son.id,
                event_type=f"evt-{i}",
                value_json=None,
                occurred_at=base - timedelta(minutes=i),
                source="manual",
                notes=None,
                created_at=base,
            )
        )
    db.add_all(rows)
    db.flush()
    ctx = load_trusted_context(db, son.id)
    assert len(ctx.lifestyle_events) == GATE2_LIFESTYLE_EVENT_LIST_LIMIT
    assert ctx.lifestyle_events[0].event_type == "evt-0"
    assert ctx.lifestyle_events[-1].event_type == f"evt-{GATE2_LIFESTYLE_EVENT_LIST_LIMIT - 1}"


def test_j_malformed_value_fail_safe(db):
    son = _user(db, "son-mal")
    _lifestyle(db, son.id, event_type="sleep", value_raw="{not-json")
    ctx = load_trusted_context(db, son.id)
    assert ctx.lifestyle_events[0].value_compact is not None
    assert len(ctx.lifestyle_events[0].value_compact) <= 64
    assert "notes" not in (ctx.lifestyle_events[0].value_compact or "")


def test_k_lifestyle_context_ref(db):
    son = _user(db, "son-lref")
    ev = _lifestyle(db, son.id, event_type="hydration")
    ctx = load_trusted_context(db, son.id)
    assert {"ref_type": "user_lifestyle_event", "ref_id": ev.id} in ctx.context_refs


def test_l_no_raw_notes_leak(db):
    son = _user(db, "son-notes")
    _habit(db, son.id, name="walk")
    _lifestyle(db, son.id, event_type="sleep", value={"hours": 8})
    ctx = load_trusted_context(db, son.id)
    blob = json.dumps(
        {
            "habits": [h.__dict__ for h in ctx.habits],
            "events": [e.__dict__ for e in ctx.lifestyle_events],
        }
    )
    assert "secret notes" not in blob
    assert "notes must not leak" not in blob


# --- Personalization consumption ---


def test_m_routine_uses_habit_context(db):
    son = _user(db, "son-routine")
    _habit(db, son.id, name="morning stretch")
    ctx = load_trusted_context(db, son.id)
    pers = build_personalization(ctx, domain="routine")
    assert "morning stretch" in pers.routine_terms
    retrieval = _ok_retrieval()
    composition = compose_grounded_action(retrieval, domain="routine", ctx=ctx)
    assert composition is not None
    assert "morning stretch" in composition.suggestions[0].detail
    assert "KU-ROUTINE-1" in composition.rationale
    assert "Personal context" in composition.suggestions[0].detail


def test_n_lifestyle_uses_event_context(db):
    son = _user(db, "son-life-act")
    _lifestyle(db, son.id, event_type="hydration")
    ctx = load_trusted_context(db, son.id)
    pers = build_personalization(ctx, domain="lifestyle")
    assert "hydration" in pers.lifestyle_terms
    composition = compose_grounded_action(_ok_retrieval(), domain="lifestyle", ctx=ctx)
    assert composition is not None
    assert "hydration" in composition.suggestions[0].detail


def test_o_different_context_changes_annotation(db):
    son_a = _user(db, "son-a-ctx")
    son_b = _user(db, "son-b-ctx")
    _habit(db, son_a.id, name="yoga")
    _habit(db, son_b.id, name="cycling")
    ca = compose_grounded_action(
        _ok_retrieval(), domain="routine", ctx=load_trusted_context(db, son_a.id)
    )
    cb = compose_grounded_action(
        _ok_retrieval(), domain="routine", ctx=load_trusted_context(db, son_b.id)
    )
    assert "yoga" in ca.suggestions[0].detail
    assert "cycling" in cb.suggestions[0].detail
    assert ca.suggestions[0].detail != cb.suggestions[0].detail


def test_p_no_personal_data_safe_fallback(db):
    son = _user(db, "son-empty")
    ctx = load_trusted_context(db, son.id)
    assert ctx.habits == []
    assert ctx.lifestyle_events == []
    composition = compose_grounded_action(_ok_retrieval(), domain="routine", ctx=ctx)
    assert composition is not None
    assert "Personal context" not in composition.suggestions[0].detail
    assert "Keep a steady" in composition.suggestions[0].detail


def test_q_i5_provenance_required(db):
    son = _user(db, "son-prov")
    _habit(db, son.id, name="walk")
    ctx = load_trusted_context(db, son.id)
    empty = SimpleNamespace(status=STATUS_OK, items=[])
    assert compose_grounded_action(empty, domain="routine", ctx=ctx) is None


def test_r_personal_facts_cannot_replace_i5(db):
    """Habits alone never mint an action without I5 retrieval."""
    son = _user(db, "son-no-i5")
    _profile_tz(db, son.id)
    grant_memory_consent(db, son.id, commit=True)
    _habit(db, son.id, name="daily walk")
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status="EMPTY", items=[]),
    ):
        result = generate_operational_action(
            db,
            user_id=son.id,
            actor_user_id=son.id,
            request="help with my daily routine",
            domain="routine",
            persist=False,
        )
    # Safety fail-closes on non-OK retrieval before compose (I5 authority preserved).
    assert result.status in {"MISSING_ELIGIBLE_KNOWLEDGE", "MISSING_GROUNDED_ACTION_CONTENT"}
    assert not result.suggestions
    assert result.persisted is False


def test_s_goals_restrictions_preserved(db):
    son = _user(db, "son-goals")
    db.add(
        models.UserGoal(
            user_id=son.id,
            category="lifestyle",
            title="sleep earlier",
            status="active",
            source="manual",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.add(
        models.UserRestriction(
            user_id=son.id,
            restriction_type="diet",
            title="no caffeine late",
            status="active",
            source="manual",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.flush()
    _habit(db, son.id, name="walk")
    ctx = load_trusted_context(db, son.id)
    assert "sleep earlier" in ctx.goals
    assert "no caffeine late" in ctx.restrictions
    pers = build_personalization(ctx, domain="routine")
    assert "sleep earlier" in pers.goal_terms
    assert "no caffeine late" in pers.restriction_terms


def test_t_no_clinical_semantics_in_annotation(db):
    son = _user(db, "son-clin")
    _habit(db, son.id, name="walk")
    composition = compose_grounded_action(
        _ok_retrieval(), domain="routine", ctx=load_trusted_context(db, son.id)
    )
    text = (composition.suggestions[0].detail + composition.rationale).lower()
    for banned in ("adherence", "missed habit", "disruption score", "diagnosis", "prescribe"):
        assert banned not in text


# --- Isolation / persistence ---


def test_u_user_a_never_sees_user_b(db):
    a = _user(db, "iso-a")
    b = _user(db, "iso-b")
    _habit(db, b.id, name="b-only-habit")
    _lifestyle(db, b.id, event_type="b-only-event")
    ctx = load_trusted_context(db, a.id)
    assert ctx.habits == []
    assert ctx.lifestyle_events == []


def test_v_w_persisted_plan_owner_and_idempotency(db):
    son = _user(db, "son-persist")
    _profile_tz(db, son.id)
    grant_memory_consent(db, son.id, commit=True)
    _habit(db, son.id, name="evening walk")
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        side_effect=_ok_retrieval,
    ):
        first = generate_operational_action(
            db,
            user_id=son.id,
            actor_user_id=son.id,
            request="support my evening walk routine",
            domain="routine",
            persist=True,
            plan_idempotency_key="bridge-plan-1",
            action_idempotency_key="bridge-action-1",
        )
        second = generate_operational_action(
            db,
            user_id=son.id,
            actor_user_id=son.id,
            request="support my evening walk routine",
            domain="routine",
            persist=True,
            plan_idempotency_key="bridge-plan-1",
            action_idempotency_key="bridge-action-1",
        )
    assert first.status == "ACTION_PERSISTED"
    assert first.plan_id is not None
    assert second.plan_id == first.plan_id
    assert second.action_id == first.action_id
    plan = db.query(models.I8OperationalPlan).filter(models.I8OperationalPlan.id == first.plan_id).one()
    assert plan.user_id == son.id
    assert "evening walk" in (first.summary or "")


def test_x_consent_still_required(db):
    son = _user(db, "son-consent")
    _habit(db, son.id, name="walk")
    result = generate_operational_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help with routine",
        domain="routine",
        persist=False,
    )
    assert result.status == "CONSENT_REQUIRED"
