"""GATE=SEDI-V1-BE-NUTRITION-PRIMARY-USER-E2E-01

Certification Package A — Primary User V1 Nutrition E2E (exactly CASE_01..CASE_12).
SCENARIO_ID=SEDI-V1-REAL-FAMILY-CARE-E2E-01

Canonical path (no meal schema, no Smart-RAG, no clinical invent):
Gate2/I6 prefs → I7 personalization → I5 governed knowledge → I8 nutrition action
→ I8 proactive → I10 coaching seam → DONE/idempotency.
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
from backend.app.services.i8.knowledge_bridge import build_personalization
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.nutrition_primary_path import (
    CANONICAL_AUTHORITY,
    execute_primary_nutrition_action,
)
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


def _ok_item(*, statement: str = "Prefer vegetables and whole grains for lunch") -> RetrievedKnowledgeItem:
    return RetrievedKnowledgeItem(
        knowledge_unit_id=77,
        canonical_unit_id="KU-NUTRITION-V1",
        immutable_version_id="v1",
        memory_item_id="m-nut-v1",
        memory_row_id=77,
        source_profile_id=7,
        provenance_id=9,
        raw_evidence_id=None,
        domain="nutrition",
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
    son = _user(db, "son-nut")
    other = _user(db, "acct-b-nut")
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


def _seed_nutrition_prefs(db, user_id: int) -> None:
    grant_memory_consent(db, user_id, commit=False)
    db.flush()
    write_fact(db, user_id, "lifestyle", "diet_notes", "vegetarian home cooking", commit=False)
    write_fact(db, user_id, "lifestyle", "food_habits", "prefers lunch bowls", commit=False)
    create_goal(
        db,
        user_id,
        GoalCreateIn(category="health", title="eat more vegetables", source="manual"),
    )
    create_restriction(
        db,
        user_id,
        RestrictionCreateIn(
            restriction_type="diet",
            title="avoid red meat",
            severity="medium",
            source="manual",
        ),
    )
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
    item = ContextItem(
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
    return item


def _snap(owner: int, items) -> ContextSnapshot:
    return ContextSnapshot(
        request_id="nut-e2e",
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


def test_CASE_01_PRIMARY_USER_NUTRITION_INPUT(db, patches):
    son, _other, son_self, mother = _seed_family(db)
    _profile(db, son.id)
    db.commit()

    intent = resolve_intent(
        message="create a personal meal plan for weeknight dinners", language="en"
    )
    assert intent.intent_id is IntentId.NUTRITION
    assert intent.request_kind is RequestKind.PERSONALIZED_PLAN
    assert son_self.subject_kind == "self"
    assert son_self.linked_user_id == son.id
    assert mother.subject_kind == "managed"
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0


def test_CASE_02_CANONICAL_PERSISTENCE(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    db.commit()

    facts = (
        db.query(models.UserMemoryFact)
        .filter(
            models.UserMemoryFact.user_id == son.id,
            models.UserMemoryFact.domain == "lifestyle",
            models.UserMemoryFact.key.in_(("diet_notes", "food_habits")),
        )
        .all()
    )
    assert len(facts) >= 2
    assert db.query(models.UserGoal).filter_by(user_id=son.id).count() >= 1
    assert (
        db.query(models.UserRestriction)
        .filter_by(user_id=son.id, restriction_type="diet")
        .count()
        >= 1
    )
    assert not hasattr(models, "UserNutritionPlan")
    assert not hasattr(models, "MealPlan")


def test_CASE_03_PREFERENCES_RESTRICTIONS(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    db.commit()

    ctx = load_trusted_context(db, son.id)
    assert any("vegetable" in g.lower() for g in ctx.goals)
    assert any("meat" in r.lower() or "diet" in r.lower() for r in ctx.restrictions)
    blob = " ".join(ctx.goals + ctx.restrictions).lower()
    assert "diagnos" not in blob
    assert "prescription" not in blob


def test_CASE_04_CROSS_USER_ISOLATION(db, patches):
    son, other, son_self, mother = _seed_family(db)
    _profile(db, son.id)
    _profile(db, other.id)
    _seed_nutrition_prefs(db, son.id)
    grant_memory_consent(db, other.id, commit=False)
    db.flush()
    write_fact(db, other.id, "lifestyle", "diet_notes", "OTHER_USER_SECRET_DIET", commit=False)
    db.commit()

    son_facts = (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.user_id == son.id, models.UserMemoryFact.key == "diet_notes")
        .all()
    )
    other_facts = (
        db.query(models.UserMemoryFact)
        .filter(models.UserMemoryFact.user_id == other.id)
        .all()
    )
    assert son_facts
    assert all("OTHER_USER_SECRET_DIET" not in _fact_text(f) for f in son_facts)
    assert all("vegetarian home cooking" not in _fact_text(f) for f in other_facts)
    assert son_self.linked_user_id == son.id
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    # Mother is accountless managed HS — no Mother Account nutrition ownership.
    # Do not compare HealthSubject.id to UserMemoryFact.user_id (namespaces may collide numerically).
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0
    assert load_trusted_context(db, son.id).user_id == son.id
    assert load_trusted_context(db, other.id).user_id == other.id


def test_CASE_05_I5_GOVERNED_KNOWLEDGE(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    db.commit()

    result = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="suggest a friday vegetarian lunch",
        persist=True,
        plan_idempotency_key=f"nut-i5-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"nut-i5-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED", result.status
    assert result.authority == CANONICAL_AUTHORITY
    assert result.knowledge_refs
    assert all("knowledge_unit_id" in r for r in result.knowledge_refs)
    blob = json.dumps(result.knowledge_refs).lower()
    assert "smart_rag" not in blob
    assert "raw_chunk" not in blob


def test_CASE_06_I7_PERSONALIZATION(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    rebuild_lifelong_profile(db, son.id, commit=False)
    db.commit()

    ctx = load_trusted_context(db, son.id)
    assert ctx.lifelong_profile is not None
    pers = build_personalization(ctx, domain="nutrition")
    assert pers is not None
    row = (
        db.query(models.UserLifelongProfile)
        .filter_by(user_id=son.id, status="active")
        .one()
    )
    payload = json.loads(row.structured_profile_json or "{}")
    assert payload.get("not_diagnosis") is True
    assert payload.get("profile_is_derived_only") is True
    assert any(k.startswith("lifestyle.") for k in payload.get("habits", []))


def test_CASE_07_I8_NUTRITION_ACTION(db, patches):
    son, _other, son_self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    result = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="healthy lunch ideas for home cooking",
        persist=True,
        plan_idempotency_key=f"nut-act-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"nut-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED"
    assert result.action_id is not None
    assert result.persistence == "I8_OPERATIONAL"
    assert result.clinical is False
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert action.user_id == son.id
    assert action.user_id == son_self.linked_user_id
    assert action.action_domain == "nutrition"
    assert action.status == "ACTIVE"


def test_CASE_08_FAIL_SAFE_INSUFFICIENT_EVIDENCE(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    db.commit()

    patches.side_effect = lambda *a, **k: SimpleNamespace(
        status=STATUS_NO_ELIGIBLE_KNOWLEDGE, items=[]
    )
    result = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="suggest a friday meal",
        persist=True,
        plan_idempotency_key=f"nut-fail-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"nut-fail-act-{uuid4().hex[:6]}",
    )
    assert result.status in {
        "MISSING_ELIGIBLE_KNOWLEDGE",
        "STALE_OR_INELIGIBLE_KNOWLEDGE",
    }
    assert result.grounded is False
    assert result.fail_safe is True
    assert result.action_id is None
    assert result.clinical is False


def test_CASE_09_CLINICAL_BOUNDARY(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    db.commit()

    result = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="please diagnose my deficiency and prescribe a therapeutic diet",
        persist=True,
        plan_idempotency_key=f"nut-clin-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"nut-clin-act-{uuid4().hex[:6]}",
    )
    assert result.status in {"UNSAFE_REQUEST_BLOCKED", "THERAPEUTIC_FAIL_CLOSED"}
    assert result.grounded is False
    assert result.action_id is None
    assert result.clinical is False


def test_CASE_10_PROACTIVE_NUTRITION_FOLLOWUP(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    result = evaluate_proactive_trigger(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        trigger_family="schedule",
        request="remind me about a vegetable-forward lunch",
        domain="nutrition",
        schedule_rule_id="midday-nutrition",
        user_local_date=date(2026, 9, 7),
    )
    assert result.trigger_family == "schedule"
    assert result.outcome == "ACTION_CREATED"
    assert result.action_id is not None
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert action.action_domain == "nutrition"
    assert action.user_id == son.id


def test_CASE_11_I10_NUTRITION_SEAM(client, db, patches):
    son, _other, _self, _mother = _seed_family(db)
    when = datetime.now(timezone.utc)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    result = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="healthy lunch ideas",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=f"nut-i10-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"nut-i10-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED", result.status
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()

    delivered = process_i8_coaching_followups(db, now=when, user_id=son.id, force=True)
    assert delivered == 1
    db.commit()
    notif = _notif_for_action(db, son.id, action.id)
    assert notif is not None
    assert notif.user_id == son.id
    decision = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.id == notif.i10_policy_decision_id)
        .one()
    )
    assert decision.semantic_family == I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value
    assert decision.source_id == str(action.id)
    assert (
        db.query(models.I8OperationalPlanAction)
        .filter_by(user_id=son.id, action_domain="nutrition")
        .count()
        == 1
    )
    assert CoachingPlanDomain.NUTRITION.value == "nutrition"


def test_CASE_12_IDEMPOTENCY_COMPLETION(client, db, patches):
    son, other, _self, _mother = _seed_family(db)
    when = datetime.now(timezone.utc)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    _prefs(db, son.id)
    db.commit()

    plan_key = f"nut-idem-plan-{son.id}"
    act_key = f"nut-idem-act-{son.id}-lunch"
    first = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="healthy lunch ideas",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=plan_key,
        action_idempotency_key=act_key,
    )
    assert first.status == "ACTION_PERSISTED"
    second = execute_primary_nutrition_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="healthy lunch ideas",
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

    assert (
        _feedback(client, other.id, notif.id, {"reaction": "interact", "action_id": "done"}).status_code
        == 403
    )
    db.refresh(action)
    assert action.status == "ACTIVE"

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
        action_domain="nutrition",
        action_type="meal_suggestion",
        action_idempotency_key=f"future-nut-{uuid4().hex[:6]}",
        summary_text="Later lunch suggestion",
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


def test_orchestrator_nutrition_ready_skips_llm(db, patches):
    son, _other, _self, _mother = _seed_family(db)
    _profile(db, son.id)
    _seed_nutrition_prefs(db, son.id)
    db.commit()

    items = [
        _item(key="lifestyle.goal.veg", section="lifestyle", source=ContextSource.LIFESTYLE, value="veg", owner=son.id),
        _item(key="profile.birth_year", section="profile", source=ContextSource.PROFILE, value=1990, owner=son.id),
        _item(key="profile.sex", section="profile", source=ContextSource.PROFILE, value="male", owner=son.id),
        _item(key="profile.height_cm", section="profile", source=ContextSource.PROFILE, value=178, owner=son.id),
        _item(key="profile.weight_kg", section="profile", source=ContextSource.PROFILE, value=78, owner=son.id),
        _item(key=CONFIRMED_NONE_CONDITIONS, section="health", source=ContextSource.HEALTH, value="none", owner=son.id),
        _item(key=CONFIRMED_NONE_MEDICATIONS, section="health", source=ContextSource.HEALTH, value="none", owner=son.id),
        _item(key=CONFIRMED_NONE_RESTRICTIONS, section="lifestyle", source=ContextSource.LIFESTYLE, value="none", owner=son.id),
    ]
    snap = _snap(son.id, items)
    intent = resolve_intent(message="create a personal meal plan", language="en")
    assert intent.intent_id is IntentId.NUTRITION
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
        return {"message": "LLM invented Dr. Fake Diet Clinic meal plan"}

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
        message="create a personal meal plan for dinners",
        language="en",
        interaction_source="chat",
    )
    assert llm_calls["n"] == 0
    assert "NUTRITION_PRIMARY_PATH" in (out.reason_codes or [])
    assert "Dr. Fake" not in (out.message or "")
    assert (
        db.query(models.I8OperationalPlanAction)
        .filter_by(user_id=son.id, action_domain="nutrition")
        .count()
        >= 1
    )


def test_authority_matrix_v1_requirements():
    intent = IntentResult(
        intent_id=IntentId.NUTRITION,
        request_kind=RequestKind.PERSONALIZED_PLAN,
        rule_id="test",
        registry_version=REGISTRY_VERSION,
        confidence_band=IntentConfidenceBand.HIGH,
    )
    reqs = {r.requirement_id for r in requirements_for(intent)}
    assert "nut.meal_prefs" not in reqs
    assert "nut.goal" in reqs
    from backend.app.services.i8.nutrition_planner import plan_nutrition

    assert callable(plan_nutrition)
    assert callable(generate_operational_action)
