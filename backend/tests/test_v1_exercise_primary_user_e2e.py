"""GATE=SEDI-V1-BE-EXERCISE-PRIMARY-USER-E2E-01

Certification Package B — Primary User V1 Exercise E2E (exactly CASE_01..CASE_10).
SCENARIO_ID=SEDI-V1-REAL-FAMILY-CARE-E2E-01

Canonical path (no exercise planner schema, no Smart-RAG, no clinical invent):
Gate2/I6 prefs → I7 personalization → I5 governed knowledge → I8 exercise action
→ I8 proactive → I10 EXERCISE_PLAN_FOLLOW_UP → DONE/idempotency.
I3 intent = ACTIVITY; I8 domain = exercise.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.schemas.gate2 import GoalCreateIn, RestrictionCreateIn
from backend.app.services.gate2_data_service import create_goal, create_restriction
from backend.app.services.i5.runtime_knowledge_retrieval import (
    STATUS_NO_ELIGIBLE_KNOWLEDGE,
    STATUS_OK,
    RetrievedKnowledgeItem,
)
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
from backend.app.services.i8.action_completion import CANONICAL_TERMINAL_ACTION_STATUS
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.exercise_primary_path import (
    CANONICAL_AUTHORITY,
    execute_primary_exercise_action,
)
from backend.app.services.i8.knowledge_bridge import build_personalization
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.proactive_orchestrator import evaluate_proactive_trigger
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.unified_core import generate_operational_action
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i10.coaching_followup_types import CoachingPlanDomain
from backend.app.services.i10.coaching_worker import process_i8_coaching_followups
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.intelligence.context_types import (
    SOURCE_SORT_RANK,
    ContextItem,
    ContextProvenance,
    ContextSnapshot,
    ContextSource,
)
from backend.app.services.intelligence.contracts import (
    IntentConfidenceBand,
    IntentId,
    IntentResult,
    ReadinessStatus,
    RequestKind,
)
from backend.app.services.intelligence.intent_registry import REGISTRY_VERSION, resolve_intent
from backend.app.services.intelligence.missing_information import (
    CONFIRMED_NONE_CONDITIONS,
    CONFIRMED_NONE_MEDICATIONS,
    CONFIRMED_NONE_RESTRICTIONS,
    evaluate_readiness,
    requirements_for,
)
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4 = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG = patch(
    "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
    return_value=True,
)
_I5 = patch(
    "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
)


def _ok_item(*, statement: str = "Prefer short daily walking sessions") -> RetrievedKnowledgeItem:
    return RetrievedKnowledgeItem(
        knowledge_unit_id=88,
        canonical_unit_id="KU-EXERCISE-V1",
        immutable_version_id="v1",
        memory_item_id="m-ex-v1",
        memory_row_id=88,
        source_profile_id=7,
        provenance_id=9,
        raw_evidence_id=None,
        domain="exercise",
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


@pytest.fixture
def patches():
    with _GATE4, _FLAG, _I5 as i5:
        i5.side_effect = lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[_ok_item()])
        yield i5


@pytest.fixture()
def client(db):
    def _override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _user(db, label: str) -> models.User:
    row = models.User(
        name=f"{label}-{uuid4().hex[:6]}",
        secret_key=f"sk-{uuid4().hex}",
        preferred_language="en",
    )
    db.add(row)
    db.flush()
    return row


def _prefs(db, user_id: int) -> None:
    if db.query(models.NotificationPrefs).filter_by(user_id=user_id).first() is None:
        db.add(
            models.NotificationPrefs(
                user_id=user_id,
                companion_enabled=True,
                health_alert_enabled=True,
                reminder_system_enabled=True,
            )
        )
    if db.query(models.PushDevice).filter_by(user_id=user_id, is_active=True).first() is None:
        db.add(
            models.PushDevice(
                user_id=user_id,
                platform="android",
                fcm_token=f"fcm-{user_id}-{uuid4().hex[:6]}",
                is_active=True,
            )
        )
    db.flush()


def _seed_family(db):
    son = _user(db, "son-ex")
    other = _user(db, "acct-b-ex")
    son_self = ensure_self_subject_for_account(db, son.id, display_name="SON_SELF", commit=False)
    mother = create_managed_subject_without_account(
        db,
        account_user_id=son.id,
        display_name="MOTHER_ALS",
        access_role="MANAGER",
        commit=False,
    )
    db.flush()
    return son, other, son_self, mother


def _profile(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first() is None:
        db.add(
            models.UserProfileCore(
                user_id=user_id,
                timezone="UTC",
                birth_year=1990,
                sex="male",
                height_cm=178,
                weight_kg=78.0,
            )
        )
        db.flush()


def _habit(db, user_id: int, name: str) -> models.UserHabit:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = models.UserHabit(
        user_id=user_id,
        name=name,
        frequency="daily",
        status="active",
        source="manual",
        notes="must-not-leak",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _seed_exercise_prefs(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=False)
    db.flush()
    write_fact(db, user_id, "lifestyle", "activity_level", "prefers morning walking", commit=False)
    create_goal(
        db,
        user_id,
        GoalCreateIn(category="fitness", title="walk more regularly", source="manual"),
    )
    create_restriction(
        db,
        user_id,
        RestrictionCreateIn(
            restriction_type="exercise",
            title="avoid high-impact jumping",
            severity="medium",
            source="manual",
        ),
    )
    _habit(db, user_id, "morning walk")
    db.flush()


def _feedback(client, user_id, notif_id, payload):
    return client.post(
        f"/notifications/{notif_id}/feedback",
        headers=_auth(user_id),
        json=payload,
    )


def _notif_for_action(db, user_id: int, action_id: int) -> models.Notification:
    return (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.source_id == str(action_id),
        )
        .order_by(models.Notification.id.desc())
        .first()
    )


def _item(*, key: str, section: str, source: ContextSource, value, owner: int) -> ContextItem:
    return ContextItem(
        canonical_key=key,
        section=section,  # type: ignore[arg-type]
        source=source,
        structured_value=value,
        display_text=f"{key}={value}",
        provenance=ContextProvenance(source=source, owner_user_id=owner, query_label="t"),
        observed_at=None,
        freshness="fresh",  # type: ignore[arg-type]
        sensitivity="medium",  # type: ignore[arg-type]
        consent="explicit",  # type: ignore[arg-type]
        may_send_to_llm=True,
        sort_rank=SOURCE_SORT_RANK[source],
    )


def _snap(owner: int, items) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="ex-e2e",
        owner_user_id=owner,
        sections={},
        items=list(items),
        preferred_name=None,
        conflict_count=0,
        truncated_count=0,
        reason_codes=(),
        adapter_order=(),
    )


def _fact_text(row: models.UserMemoryFact) -> str:
    raw = row.value_json or ""
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return str(raw)
    if isinstance(parsed, dict):
        return str(parsed.get("value") or parsed)
    return str(parsed)


def test_scenario_id():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_CASE_01_PRIMARY_USER_EXERCISE_INPUT(db, patches):
    son, _other, son_self, mother = _seed_family(db)
    _profile(db, son.id)
    db.commit()

    intent = resolve_intent(
        message="create an exercise routine three times a week", language="en"
    )
    assert intent.intent_id is IntentId.ACTIVITY
    assert intent.request_kind is RequestKind.PERSONALIZED_PLAN
    assert son_self.subject_kind == "self"
    assert son_self.linked_user_id == son.id
    assert mother.subject_kind == "managed"
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0


def test_CASE_02_GOALS_PREFS_RESTRICTIONS(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    db.commit()

    ctx = load_trusted_context(db, son.id)
    assert any("walk" in g.lower() for g in ctx.goals)
    assert any("jump" in r.lower() or "exercise" in r.lower() for r in ctx.restrictions)
    assert any(h.name == "morning walk" for h in ctx.habits)
    blob = " ".join(ctx.goals + ctx.restrictions).lower()
    assert "diagnos" not in blob
    assert "prescription" not in blob


def test_CASE_03_CANONICAL_PERSISTENCE(db, patches):
    son, other, _self, mother = _seed_family(db)
    _profile(db, son.id)
    _profile(db, other.id)
    _seed_exercise_prefs(db, son.id)
    grant_memory_consent(db, other.id, commit=False)
    db.flush()
    write_fact(db, other.id, "lifestyle", "activity_level", "OTHER_USER_SECRET_WALK", commit=False)
    db.commit()

    facts = (
        db.query(models.UserMemoryFact)
        .filter(
            models.UserMemoryFact.user_id == son.id,
            models.UserMemoryFact.domain == "lifestyle",
            models.UserMemoryFact.key == "activity_level",
        )
        .all()
    )
    assert facts
    other_facts = (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.user_id == other.id)
        .all()
    )
    assert all("OTHER_USER_SECRET_WALK" not in _fact_text(f) for f in facts)
    assert all("morning walking" not in _fact_text(f) for f in other_facts)
    assert not hasattr(models, "UserExercisePlan")
    assert not hasattr(models, "ExercisePlanner")
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0


def test_CASE_04_I5_GOVERNED_KNOWLEDGE(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    db.commit()

    result = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="suggest a short morning walk",
        persist=True,
        plan_idempotency_key=f"ex-i5-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"ex-i5-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED", result.status
    assert result.authority == CANONICAL_AUTHORITY
    assert result.knowledge_refs
    assert all("knowledge_unit_id" in r for r in result.knowledge_refs)
    blob = json.dumps(result.knowledge_refs).lower()
    assert "smart_rag" not in blob
    assert "raw_chunk" not in blob


def test_CASE_05_I7_PERSONALIZATION(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    rebuild_lifelong_profile(db, son.id, commit=False)
    db.commit()

    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is not None
    pers = build_personalization(ctx, domain="exercise")
    assert pers is not None
    row = (
        db.query(models.UserLifelongProfile)
        .filter_by(user_id=son.id, status="active")
        .one()
    )
    payload = json.loads(row.structured_profile_json or "{}")
    assert payload.get("not_diagnosis") is True
    assert payload.get("profile_is_derived_only") is True


def test_CASE_06_I8_EXERCISE_ACTION(db, patches):
    son, _other, son_self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    result = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help me walk more this week",
        persist=True,
        plan_idempotency_key=f"ex-act-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"ex-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED"
    assert result.action_id is not None
    assert result.persistence == "I8_OPERATIONAL"
    assert result.clinical is False
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert action.user_id == son.id
    assert action.user_id == son_self.linked_user_id
    assert action.action_domain == "exercise"
    assert action.status == "ACTIVE"


def test_CASE_07_CLINICAL_SAFETY_BOUNDARY(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    db.commit()

    result = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="diagnose my heart and prescribe ALS-safe therapeutic exercise",
        persist=True,
        plan_idempotency_key=f"ex-clin-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"ex-clin-act-{uuid4().hex[:6]}",
    )
    assert result.status in {
        "UNSAFE_REQUEST_BLOCKED",
        "THERAPEUTIC_FAIL_CLOSED",
        "UNSUPPORTED_CLINICAL_APPLICABILITY",
    }
    assert result.grounded is False
    assert result.action_id is None
    assert result.clinical is False

    # Insufficient evidence fail-safe (not clinical invent)
    patches.side_effect = lambda *a, **k: SimpleNamespace(
        status=STATUS_NO_ELIGIBLE_KNOWLEDGE, items=[]
    )
    miss = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="suggest a friday walk",
        persist=True,
        plan_idempotency_key=f"ex-miss-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"ex-miss-act-{uuid4().hex[:6]}",
    )
    assert miss.status in {"MISSING_ELIGIBLE_KNOWLEDGE", "STALE_OR_INELIGIBLE_KNOWLEDGE"}
    assert miss.fail_safe is True
    assert miss.action_id is None


def test_CASE_08_PROACTIVE_I10_SEAM(client, db, patches):
    son, _other, _self, _mother = _seed_family(db)
    when = datetime.now(timezone.utc)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    proactive = evaluate_proactive_trigger(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        trigger_family="schedule",
        request="remind me about a short morning walk",
        domain="exercise",
        schedule_rule_id="morning-exercise",
        user_local_date=date(2026, 9, 7),
    )
    assert proactive.trigger_family == "schedule"
    assert proactive.outcome == "ACTION_CREATED"
    assert proactive.action_id is not None
    action = db.query(models.I8OperationalPlanAction).filter_by(id=proactive.action_id).one()
    assert action.action_domain == "exercise"

    delivered = process_i8_coaching_followups(db, now=when, user_id=son.id, force=True)
    assert delivered == 1
    db.commit()
    notif = _notif_for_action(db, son.id, action.id)
    assert notif is not None
    decision = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.id == notif.i10_policy_decision_id)
        .one()
    )
    assert decision.semantic_family == I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP.value
    assert decision.source_id == str(action.id)
    assert CoachingPlanDomain.EXERCISE.value == "exercise"
    # I10 did not mint a second I8 exercise action.
    assert (
        db.query(models.I8OperationalPlanAction)
        .filter_by(user_id=son.id, action_domain="exercise")
        .count()
        == 1
    )


def test_CASE_09_ISOLATION(client, db, patches):
    son, other, son_self, mother = _seed_family(db)
    when = datetime.now(timezone.utc)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    result = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help me walk more",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=f"ex-iso-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"ex-iso-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED"
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert action.user_id == son.id
    assert action.user_id == son_self.linked_user_id
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0

    assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) == 1
    db.commit()
    notif = _notif_for_action(db, son.id, action.id)
    assert notif is not None
    # Other account cannot DONE Son notification
    assert (
        _feedback(client, other.id, notif.id, {"reaction": "interact", "action_id": "done"}).status_code
        == 403
    )
    db.refresh(action)
    assert action.status == "ACTIVE"


def test_CASE_10_IDEMPOTENCY_DONE(client, db, patches):
    son, _other, _self, _mother = _seed_family(db)
    when = datetime.now(timezone.utc)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    plan_key = f"ex-idem-plan-{son.id}"
    act_key = f"ex-idem-act-{son.id}-walk"
    first = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help me walk more",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=plan_key,
        action_idempotency_key=act_key,
    )
    assert first.status == "ACTION_PERSISTED"
    second = execute_primary_exercise_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help me walk more",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=plan_key,
        action_idempotency_key=act_key,
    )
    assert second.action_id == first.action_id

    action = db.query(models.I8OperationalPlanAction).filter_by(id=first.action_id).one()
    assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) == 1
    db.commit()
    notif = _notif_for_action(db, son.id, action.id)
    assert notif is not None

    r_done = _feedback(client, son.id, notif.id, {"reaction": "interact", "action_id": "done"})
    assert r_done.status_code == 200, r_done.text
    db.refresh(action)
    assert action.status == CANONICAL_TERMINAL_ACTION_STATUS
    assert (
        _feedback(client, son.id, notif.id, {"reaction": "interact", "action_id": "done"}).status_code
        == 200
    )
    db.refresh(action)
    assert action.status == "COMPLETED"
    assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) == 0

    window = resolve_local_day_window(db, son.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.get_active_plan(db, user_id=son.id, user_local_date=window.user_local_date)
    assert plan is not None
    future = repo.create_action(
        db,
        user_id=son.id,
        plan_id=plan.id,
        action_domain="exercise",
        action_type="activity_suggestion",
        action_idempotency_key=f"future-ex-{uuid4().hex[:6]}",
        summary_text="Later walk suggestion",
        presentation_json="{}",
        knowledge_refs_json=action.knowledge_refs_json,
        context_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.commit()
    assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) == 1
    db.refresh(future)
    assert future.status == "ACTIVE"
    assert future.id != action.id


def test_orchestrator_activity_ready_skips_llm(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_exercise_prefs(db, son.id)
    db.commit()

    items = [
        _item(key="lifestyle.goal.walk", section="lifestyle", source=ContextSource.LIFESTYLE, value="walk", owner=son.id),
        _item(key="profile.birth_year", section="profile", source=ContextSource.PROFILE, value=1990, owner=son.id),
        _item(key="profile.sex", section="profile", source=ContextSource.PROFILE, value="male", owner=son.id),
        _item(key="profile.height_cm", section="profile", source=ContextSource.PROFILE, value=178, owner=son.id),
        _item(key="profile.weight_kg", section="profile", source=ContextSource.PROFILE, value=78, owner=son.id),
        _item(key=CONFIRMED_NONE_CONDITIONS, section="health", source=ContextSource.HEALTH, value="none", owner=son.id),
        _item(key=CONFIRMED_NONE_MEDICATIONS, section="health", source=ContextSource.HEALTH, value="none", owner=son.id),
        _item(key=CONFIRMED_NONE_RESTRICTIONS, section="lifestyle", source=ContextSource.LIFESTYLE, value="none", owner=son.id),
    ]
    snap = _snap(son.id, items)
    intent = resolve_intent(message="create an exercise plan for me", language="en")
    assert intent.intent_id is IntentId.ACTIVITY
    readiness = evaluate_readiness(
        snapshot=snap,
        intent=intent,
        authenticated_user_id=son.id,
        language="en",
    )
    assert readiness.status is ReadinessStatus.READY

    llm_calls = {"n": 0}

    def _llm(*_a, **_k):
        llm_calls["n"] += 1
        return {"message": "LLM invented cardiac rehab prescription for ALS"}

    class _Asm:
        def assemble(self, *_a, **_k):
            return snap

        def build_compatibility_projection(self, snapshot):
            return SimpleNamespace(text="proj", preferred_name="Son", truncated=False)

    orch = IntelligenceOrchestrator(
        db=db,
        structured_mode=True,
        context_assembler=_Asm(),
        legacy_generator=_llm,
    )
    out = orch.process(
        authenticated_user_id=son.id,
        message="create an exercise plan for me",
        language="en",
        interaction_source="chat",
    )
    assert llm_calls["n"] == 0
    assert "EXERCISE_PRIMARY_PATH" in (out.reason_codes or [])
    assert "ALS" not in (out.message or "")
    assert (
        db.query(models.I8OperationalPlanAction)
        .filter_by(user_id=son.id, action_domain="exercise")
        .count()
        >= 1
    )


def test_negative_authority_matrix():
    intent = IntentResult(
        intent_id=IntentId.ACTIVITY,
        request_kind=RequestKind.PERSONALIZED_PLAN,
        rule_id="test",
        registry_version=REGISTRY_VERSION,
        confidence_band=IntentConfidenceBand.HIGH,
    )
    reqs = {r.requirement_id for r in requirements_for(intent)}
    assert "act.goal" in reqs
    assert "nut.meal_prefs" not in reqs
    assert callable(generate_operational_action)
    assert CANONICAL_AUTHORITY == "I8_OPERATIONAL_EXERCISE"
