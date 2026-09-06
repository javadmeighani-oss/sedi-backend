"""GATE=SEDI-V1-BE-PRIMARY-USER-I8-PG16-CROSS-I-ACCEPTANCE-01

Primary Son Cross-I acceptance on PostgreSQL 16 using existing seams only.
SCENARIO_ID=SEDI-V1-REAL-FAMILY-CARE-E2E-01
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
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
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i8.action_completion import (
    CANONICAL_TERMINAL_ACTION_STATUS,
    I8ActionCompletionError,
    complete_exact_operational_action,
)
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.knowledge_bridge import build_personalization
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.unified_core import generate_operational_action
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i10.coaching_worker import process_i8_coaching_followups
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


@pytest.fixture
def patches():
    item = RetrievedKnowledgeItem(
        knowledge_unit_id=42,
        canonical_unit_id="KU-ROUTINE-CROSS-I",
        immutable_version_id="v1",
        memory_item_id="m-cross-i",
        memory_row_id=42,
        source_profile_id=7,
        provenance_id=9,
        raw_evidence_id=None,
        domain="lifestyle",
        language="en",
        topic_taxonomy=None,
        normalized_statement="Keep a steady daily movement pattern",
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )
    with _GATE4, _FLAG, _I5 as i5:
        i5.side_effect = lambda *a, **k: SimpleNamespace(status=STATUS_OK, items=[item])
        yield


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


def _habit(db, user_id: int, name: str) -> models.UserHabit:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = models.UserHabit(
        user_id=user_id,
        name=name,
        frequency="daily",
        status="active",
        source="manual",
        notes="must-not-leak-to-i10",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _insert_lifelong(db, user_id: int, *, consent_id: int | None, habits=None):
    now = datetime.now(timezone.utc)
    payload = {
        "authority": "I6_FACTS_ARE_SOT",
        "profile_is_derived_only": True,
        "not_diagnosis": True,
        "generator_version": "i7-v1-lifelong-profile",
        "habits": habits or ["lifestyle.evening_stretch"],
        "preferences": ["preferences.quiet_mornings"],
        "goals": [],
    }
    row = models.UserLifelongProfile(
        user_id=user_id,
        version=1,
        status="active",
        structured_profile_json=json.dumps(payload, sort_keys=True),
        narrative_compact="Derived compact profile; not source of truth.",
        source_fact_ids_json="[]",
        source_event_refs_json="[]",
        consent_id=consent_id,
        generator_version="i7-v1-lifelong-profile",
        built_from_period_start=now - timedelta(days=30),
        built_from_period_end=now,
    )
    db.add(row)
    db.flush()
    return row


def _seed_family(db):
    """Son Account + SELF HS + Mother managed/accountless HS (no cross-namespace id compares)."""
    son = _user(db, "son-x")
    other = _user(db, "acct-b")
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


def test_scenario_id():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_flow_a_routine_lifestyle_cross_i(client, db, patches):
    """Gate2 → I7 → I5 governed knowledge → I8 proactive → I10 → DONE lifecycle."""
    son, _other, son_self, mother = _seed_family(db)
    # Delivery clock must match generate_operational_action local-day window (uses now).
    when = datetime.now(timezone.utc)

    # Identity
    assert son_self.subject_kind == "self"
    assert son_self.linked_user_id == son.id
    assert mother.subject_kind == "managed"
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0

    if db.query(models.UserProfileCore).filter_by(user_id=son.id).first() is None:
        db.add(models.UserProfileCore(user_id=son.id, timezone="UTC"))
        db.flush()

    habit = _habit(db, son.id, "evening stretch")
    consent = grant_memory_consent(db, son.id, commit=False)
    lifelong = _insert_lifelong(db, son.id, consent_id=consent.id)
    _prefs(db, son.id)
    db.commit()

    # Gate2 + I7 seams (Son only)
    ctx = load_trusted_context(db, son.id)
    assert any(h.name == "evening stretch" for h in ctx.habits)
    assert ctx.lifelong_profile is not None
    assert ctx.lifelong_profile.profile_id == lifelong.id
    assert any(r.get("ref_type") == "user_habit" for r in ctx.context_refs)
    assert any(r.get("ref_type") == "user_lifelong_profile" for r in ctx.context_refs)
    pers = build_personalization(ctx, domain="routine")
    assert pers.routine_terms
    assert db.query(models.UserLifelongProfile).filter_by(user_id=son.id).count() == 1
    # Mother has no Account → no Mother I7 row ownership possible via linked_user_id
    assert mother.linked_user_id is None
    assert (
        db.query(models.UserLifelongProfile)
        .filter(models.UserLifelongProfile.user_id != son.id)
        .count()
        == 0
    )

    # I5 governed knowledge → I8 persist (mocked retrieve; no Smart-RAG activation)
    result = generate_operational_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help with my daily routine stretch",
        domain="routine",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=f"cross-i-plan-{son.id}-{uuid4().hex[:6]}",
        action_idempotency_key=f"cross-i-act-{son.id}-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED", result.status
    assert result.action_id is not None
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert action.user_id == son.id
    assert action.user_id == son_self.linked_user_id
    assert action.status == "ACTIVE"
    refs = json.loads(action.knowledge_refs_json or "[]")
    assert refs, "governed knowledge refs required"
    assert all("knowledge_unit_id" in r for r in refs)
    # I5 refs are evidence pointers, not I10 enqueue commands
    assert not any("enqueue" in json.dumps(r).lower() for r in refs)

    # I10 delivery + provenance
    delivered = process_i8_coaching_followups(db, now=when, user_id=son.id, force=True)
    assert delivered == 1
    db.commit()
    notif = _notif_for_action(db, son.id, action.id)
    assert notif is not None
    assert notif.user_id == son.id
    assert notif.source_id == str(action.id)
    decision = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.id == notif.i10_policy_decision_id)
        .one()
    )
    assert decision.source_id == str(action.id)
    assert decision.decision == "SEND"

    # Non-DONE does not mutate I8
    r_non = _feedback(client, son.id, notif.id, {"reaction": "interact", "action_id": "NOT_NOW"})
    assert r_non.status_code == 200, r_non.text
    db.refresh(action)
    assert action.status == "ACTIVE"
    assert db.query(models.UserLifelongProfile).filter_by(user_id=son.id).count() == 1
    # No new lifelong profiles from feedback
    assert db.query(models.UserLifelongProfile).count() == 1

    # DONE → exact I8 completion
    r_done = _feedback(client, son.id, notif.id, {"reaction": "interact", "action_id": "done"})
    assert r_done.status_code == 200, r_done.text
    db.refresh(action)
    assert action.status == CANONICAL_TERMINAL_ACTION_STATUS
    assert (
        db.query(models.NotificationFeedback)
        .filter_by(notification_id=notif.id, action="done")
        .count()
        >= 1
    )
    assert (
        db.query(models.InteractionEvent)
        .filter_by(source_notification_id=notif.id, event_type="notification_done")
        .count()
        >= 1
    )
    # No adherence / clinical rows invented by DONE
    assert not hasattr(action, "adherence_score")
    assert db.query(models.UserLifelongProfile).count() == 1

    # Idempotent DONE
    r_again = _feedback(client, son.id, notif.id, {"reaction": "interact", "action_id": "done"})
    assert r_again.status_code == 200, r_again.text
    db.refresh(action)
    assert action.status == "COMPLETED"

    # No redelivery of completed occurrence
    assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) == 0

    # Future same-domain action remains deliverable
    window = resolve_local_day_window(db, son.id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.get_active_plan(db, user_id=son.id, user_local_date=window.user_local_date)
    assert plan is not None
    future = repo.create_action(
        db,
        user_id=son.id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_item",
        action_idempotency_key=f"future-{uuid4().hex[:6]}",
        summary_text="Evening stretch later",
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
    # Habit still owned by Son Account (Gate2 authority unchanged)
    db.refresh(habit)
    assert habit.user_id == son.id


def test_no_substitution_and_fail_closed(client, db, patches):
    son, other, son_self, mother = _seed_family(db)
    when = datetime.now(timezone.utc)
    if db.query(models.UserProfileCore).filter_by(user_id=son.id).first() is None:
        db.add(models.UserProfileCore(user_id=son.id, timezone="UTC"))
        db.flush()
    consent = grant_memory_consent(db, son.id, commit=False)
    _insert_lifelong(db, son.id, consent_id=consent.id)
    _prefs(db, son.id)
    db.commit()

    # Mother HS must not be usable as Son Account identity for generation
    # (skip numeric collision: HealthSubject.id may equal an unrelated User.id)
    existing_account_ids = {u.id for u in db.query(models.User).all()}
    if mother.id not in existing_account_ids:
        denied = generate_operational_action(
            db,
            user_id=mother.id,
            actor_user_id=mother.id,
            request="help with routine",
            domain="routine",
            persist=True,
            generation_mode="proactive",
        )
        assert denied.status != "ACTION_PERSISTED"
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"

    # Subject substitution: Mother managed HS via Son actor must not inherit Son Gate2/I7 habits
    from backend.app.services.i8.subject_context import (
        load_subject_trusted_context,
        to_i8_trusted_context_compat,
    )

    sub_ctx = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=mother.id
    )
    compat = to_i8_trusted_context_compat(sub_ctx)
    assert compat.habits == []
    assert compat.lifestyle_events == []
    assert compat.lifelong_profile is None

    # Legitimate Son action + delivery (single action first — avoid multi-delivery policy variance)
    ok = generate_operational_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help with my daily routine walk",
        domain="routine",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=f"ns-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"ns-act-{uuid4().hex[:6]}",
    )
    assert ok.status == "ACTION_PERSISTED", ok.status
    a1 = db.query(models.I8OperationalPlanAction).filter_by(id=ok.action_id).one()
    assert a1.user_id == son.id
    assert a1.user_id == son_self.linked_user_id

    n = process_i8_coaching_followups(db, now=when, user_id=son.id, force=True)
    assert n == 1
    db.commit()
    n1 = _notif_for_action(db, son.id, a1.id)
    assert n1 is not None

    # Second Son action exists for client redirection proof (need not be delivered yet)
    ok2 = generate_operational_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help with my evening stretch routine",
        domain="routine",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=f"ns-plan2-{uuid4().hex[:6]}",
        action_idempotency_key=f"ns-act2-{uuid4().hex[:6]}",
    )
    assert ok2.status == "ACTION_PERSISTED", ok2.status
    a2 = db.query(models.I8OperationalPlanAction).filter_by(id=ok2.action_id).one()
    assert a2.id != a1.id
    assert a2.user_id == son.id

    # Account B cannot complete Son notification
    r_xuser = _feedback(client, other.id, n1.id, {"reaction": "interact", "action_id": "done"})
    assert r_xuser.status_code == 403
    db.refresh(a1)
    assert a1.status == "ACTIVE"

    # Unrelated notification cannot complete
    unrelated = models.Notification(
        user_id=son.id,
        type="connection_ping",
        title="Other",
        body="Unrelated",
        priority="normal",
        channel="push",
        status="queued",
    )
    db.add(unrelated)
    db.commit()
    r_unrel = _feedback(client, son.id, unrelated.id, {"reaction": "interact", "action_id": "done"})
    assert r_unrel.status_code == 422
    db.refresh(a1)
    assert a1.status == "ACTIVE"

    # Client Mother HS id as i8_action_id cannot redirect
    r_mhs = _feedback(
        client,
        son.id,
        n1.id,
        {"reaction": "interact", "action_id": "done", "i8_action_id": mother.id},
    )
    assert r_mhs.status_code == 422
    db.refresh(a1)
    assert a1.status == "ACTIVE"

    # Client other valid Son action id cannot redirect
    r_redir = _feedback(
        client,
        son.id,
        n1.id,
        {"reaction": "interact", "action_id": "done", "i8_action_id": a2.id},
    )
    assert r_redir.status_code == 422
    db.refresh(a1)
    db.refresh(a2)
    assert a1.status == "ACTIVE"
    assert a2.status == "ACTIVE"

    # Provenance mismatch fail-closed
    n1.source_id = str(a2.id)
    db.commit()
    r_prov = _feedback(client, son.id, n1.id, {"reaction": "interact", "action_id": "done"})
    assert r_prov.status_code == 422
    db.refresh(a1)
    assert a1.status == "ACTIVE"

    # Nonexistent action
    with pytest.raises(I8ActionCompletionError) as missing:
        complete_exact_operational_action(db, actor_user_id=son.id, action_id=9_999_999, now=when)
    assert missing.value.code == "ACTION_NOT_FOUND"

    # Expired / superseded / invalid fail-closed
    a2.status = "SUPERSEDED"
    db.commit()
    with pytest.raises(I8ActionCompletionError) as ei:
        complete_exact_operational_action(db, actor_user_id=son.id, action_id=a2.id, now=when)
    assert ei.value.code == "ACTION_NOT_COMPLETABLE"

    a_exp = db.query(models.I8OperationalPlanAction).filter_by(id=ok.action_id).one()
    a_exp.status = "ACTIVE"
    a_exp.expires_at = when - timedelta(hours=1)
    # restore clean source for unrelated checks already done
    db.commit()
    with pytest.raises(I8ActionCompletionError) as ex:
        complete_exact_operational_action(db, actor_user_id=son.id, action_id=a_exp.id, now=when)
    assert ex.value.code == "ACTION_EXPIRED"

    # I10 cannot create I8 actions via feedback-only path
    before = db.query(models.I8OperationalPlanAction).count()
    # recreate a deliverable notification path already exercised; like alone
    like_n = models.Notification(
        user_id=son.id,
        type="companion",
        title="x",
        body="y",
        priority="normal",
        channel="push",
        status="queued",
        source_id=str(a1.id),
    )
    db.add(like_n)
    db.commit()
    # without coaching provenance, DONE fails; LIKE must not create actions
    r_like = _feedback(client, son.id, like_n.id, {"reaction": "like"})
    assert r_like.status_code in {200, 422}
    assert db.query(models.I8OperationalPlanAction).count() == before


def test_authority_non_interference_matrix(db, patches):
    """I5/I7/I8/I10 remain distinct; Mother monitoring does not enter Son SELF context."""
    son, _other, son_self, mother = _seed_family(db)
    if db.query(models.UserProfileCore).filter_by(user_id=son.id).first() is None:
        db.add(models.UserProfileCore(user_id=son.id, timezone="UTC"))
        db.flush()
    _habit(db, son.id, "morning walk")
    consent = grant_memory_consent(db, son.id, commit=False)
    _insert_lifelong(db, son.id, consent_id=consent.id, habits=["lifestyle.morning_walk"])
    db.commit()

    ctx = load_trusted_context(db, son.id)
    assert ctx.user_id == son.id
    assert ctx.lifelong_profile is not None
    # HealthSubject namespace is not Account namespace semantically
    assert son_self.linked_user_id == son.id
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"

    # I7 does not complete actions
    assert db.query(models.I8OperationalPlanAction).filter_by(user_id=son.id).count() == 0

    result = generate_operational_action(
        db,
        user_id=son.id,
        actor_user_id=son.id,
        request="help with my morning walk routine",
        domain="routine",
        persist=True,
        generation_mode="proactive",
        plan_idempotency_key=f"auth-plan-{uuid4().hex[:6]}",
        action_idempotency_key=f"auth-act-{uuid4().hex[:6]}",
    )
    assert result.status == "ACTION_PERSISTED"
    action = db.query(models.I8OperationalPlanAction).filter_by(id=result.action_id).one()
    assert action is not None
    # I5 knowledge on action is governed refs only
    refs = json.loads(action.knowledge_refs_json or "[]")
    assert refs
    blob = json.dumps(refs).lower()
    assert "smart_rag" not in blob
    assert "raw_chunk" not in blob

    # I8 completion API is I8-owned; I5/I7 modules are not invoked by complete_exact
    complete_exact_operational_action(db, actor_user_id=son.id, action_id=action.id)
    db.refresh(action)
    assert action.status == "COMPLETED"
    # I7 unchanged by completion
    assert db.query(models.UserLifelongProfile).filter_by(user_id=son.id).count() == 1
    # Mother still accountless / no I7
    assert mother.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0
