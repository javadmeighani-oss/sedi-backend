"""G4 scenario-first integration — A Nutrition + B Exercise + C06 DONE loop.

GATE=SEDI-V1-BE-FINALCERT-G4-A-B-C06-NUTRITION-EXERCISE-DONE-LOOP-SCENARIO-PG16-REVALIDATION-01
SCENARIO=SEDI-V1-REAL-FAMILY-CARE-E2E-01

Does NOT add ledger cases. Proves family slice + A/B/C06 cross-locks.

A ledger → test_v1_nutrition_primary_user_e2e.py CASE_01..12 (§452/v745)
B ledger → test_v1_exercise_primary_user_e2e.py CASE_01..10 (§453/v746)
C06 ledger → test_i8_proactive_followup_loop_02.py (§443 + ratified):
  C06-01 DONE_EXACT_I8_ACTION ← test_a + test_f
  C06-02 NON_DONE_ISOLATION ← test_j_q
  C06-03 EXPIRES_AT_FAIL_CLOSED ← test_i_expired_at
  C06-04 HTTP_FEEDBACK_DONE_IDEMPOTENT_SEAM ← test_b
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievedKnowledgeItem
from backend.app.services.i8.action_completion import (
    CANONICAL_TERMINAL_ACTION_STATUS,
    I8ActionCompletionError,
    complete_exact_operational_action,
)
from backend.app.services.i8.context import load_trusted_context
from backend.app.services.i8.exercise_primary_path import execute_primary_exercise_action
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.nutrition_primary_path import execute_primary_nutrition_action
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.unified_core import generate_operational_action
from backend.app.services.i10.coaching_worker import process_i8_coaching_followups
from backend.tests.helpers.i10_postgresql_harness import ALEMBIC_HEAD, I10IsolatedPgDb
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family


@pytest.fixture(scope="module")
def g4_pg_db_module():
    isolated = I10IsolatedPgDb.create(suffix="g4abc06", revision=ALEMBIC_HEAD)
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture()
def db(g4_pg_db_module):
    SessionLocal, isolated = g4_pg_db_module
    connection = isolated.engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


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


def _profile_tz(db, user_id: int) -> None:
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first():
        return
    db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
    db.flush()


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
                fcm_token=f"fcm-g4-{user_id}-{uuid4().hex[:6]}",
                is_active=True,
            )
        )
    db.flush()


def _ok_item(*, domain: str = "nutrition"):
    return RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id=f"KU-G4-{domain.upper()}",
        immutable_version_id="v1",
        memory_item_id="m-g4",
        memory_row_id=1,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=None,
        domain=domain,
        language="en",
        topic_taxonomy=None,
        normalized_statement="Keep steady daily movement and balanced meals",
        evidence_strength="MODERATE",
        freshness_state="fresh",
        conflict_state="none",
        medical_safety_state="SAFE",
        runtime_eligibility="eligible",
        rank_score=10,
    )


def _seed_action(db, user_id: int, *, when, key: str, domain: str = "routine"):
    window = resolve_local_day_window(db, user_id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.get_active_plan(db, user_id=user_id, user_local_date=window.user_local_date)
    if plan is None:
        plan = repo.create_plan(
            db,
            user_id=user_id,
            user_local_date=window.user_local_date,
            timezone_snapshot=window.timezone_snapshot,
            generation_mode="proactive",
            plan_idempotency_key=f"g4-plan-{user_id}-{key}-{uuid4().hex[:4]}",
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
        )
    action = repo.create_action(
        db,
        user_id=user_id,
        plan_id=plan.id,
        action_domain=domain,
        action_type=f"{domain}_item",
        action_idempotency_key=f"g4-{key}-{uuid4().hex[:4]}",
        summary_text=f"G4 {domain} {key}",
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.flush()
    return plan, action


def test_g4_scenario_id_canonical():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_g4_family_identity_locks(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    assert fam.son_self_hs.subject_kind == "self"
    assert fam.son_self_hs.linked_user_id == fam.son.id
    assert fam.mother_hs.subject_kind == "managed"
    assert fam.mother_hs.linked_user_id is None
    assert fam.son_self_hs.id != fam.mother_hs.id
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0


def test_g4_nutrition_exercise_user_isolation(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    _profile_tz(db, fam.stranger.id)
    now = datetime.utcnow()
    db.add(
        models.UserHabit(
            user_id=fam.son.id,
            name="son_nutrition_habit",
            frequency="daily",
            status="active",
            source="manual",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        models.UserLifestyleEvent(
            user_id=fam.son.id,
            event_type="son_exercise_walk",
            occurred_at=now,
            source="manual",
            created_at=now,
        )
    )
    db.add(
        models.UserHabit(
            user_id=fam.stranger.id,
            name="stranger_habit",
            frequency="daily",
            status="active",
            source="manual",
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    son_ctx = load_trusted_context(db, fam.son.id)
    stranger_ctx = load_trusted_context(db, fam.stranger.id)
    assert any(h.name == "son_nutrition_habit" for h in son_ctx.habits)
    assert any(e.event_type == "son_exercise_walk" for e in son_ctx.lifestyle_events)
    assert not any(h.name == "stranger_habit" for h in son_ctx.habits)
    assert not any(h.name == "son_nutrition_habit" for h in stranger_ctx.habits)
    assert fam.mother_hs.linked_user_id is None


def test_g4_personal_ne_governed_and_i5_required(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status="EMPTY", items=[]),
    ):
        blocked = generate_operational_action(
            db,
            user_id=fam.son.id,
            actor_user_id=fam.son.id,
            request="help with my daily nutrition",
            domain="nutrition",
            persist=False,
        )
    assert blocked.status in {"MISSING_ELIGIBLE_KNOWLEDGE", "MISSING_GROUNDED_ACTION_CONTENT"}
    assert not blocked.suggestions


def test_g4_nutrition_exercise_paths_with_governed_knowledge(db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    _profile_tz(db, fam.son.id)
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status=STATUS_OK, items=[_ok_item(domain="nutrition")]),
    ):
        nut = execute_primary_nutrition_action(
            db,
            user_id=fam.son.id,
            actor_user_id=fam.son.id,
            request="healthy lunch ideas",
            persist=False,
        )
    assert nut.status in {"ACTION_READY", "GROUNDED_EPHEMERAL", "ACTION_PERSISTED"}
    assert nut.clinical is False
    assert "diagnos" not in (nut.summary or "").lower()
    assert "diagnos" not in (nut.user_message or "").lower()
    with patch(
        "backend.app.services.i8.unified_core.retrieve_governed_knowledge",
        return_value=SimpleNamespace(status=STATUS_OK, items=[_ok_item(domain="exercise")]),
    ):
        ex = execute_primary_exercise_action(
            db,
            user_id=fam.son.id,
            actor_user_id=fam.son.id,
            request="gentle daily activity ideas",
            persist=False,
        )
    assert ex.status in {"ACTION_READY", "GROUNDED_EPHEMERAL", "ACTION_PERSISTED"}
    assert ex.clinical is False


def test_g4_c06_done_exact_expired_nondone_idempotent(client, db):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False, commit=False)
    son = fam.son
    stranger = fam.stranger
    _profile_tz(db, son.id)
    _prefs(db, son.id)
    when = datetime.now(timezone.utc)

    with patch(
        "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
        return_value=True,
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        _plan, action = _seed_action(db, son.id, when=when, key="done1")
        assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) == 1
        db.flush()
        notif = (
            db.query(models.Notification)
            .filter_by(user_id=son.id)
            .order_by(models.Notification.id.asc())
            .first()
        )
        assert notif is not None

        # Wrong user blocked
        r_wrong = client.post(
            f"/notifications/{notif.id}/feedback",
            headers=_auth(stranger.id),
            json={"reaction": "interact", "action_id": "done"},
        )
        assert r_wrong.status_code == 403
        db.refresh(action)
        assert action.status == "ACTIVE"

        # Non-DONE isolation
        r_like = client.post(
            f"/notifications/{notif.id}/feedback",
            headers=_auth(son.id),
            json={"reaction": "like"},
        )
        assert r_like.status_code == 200
        db.refresh(action)
        assert action.status == "ACTIVE"

        # Exact DONE
        r_done = client.post(
            f"/notifications/{notif.id}/feedback",
            headers=_auth(son.id),
            json={"reaction": "interact", "action_id": "done"},
        )
        assert r_done.status_code == 200, r_done.text
        db.refresh(action)
        assert action.status == CANONICAL_TERMINAL_ACTION_STATUS

        # Idempotent retry
        r_again = client.post(
            f"/notifications/{notif.id}/feedback",
            headers=_auth(son.id),
            json={"reaction": "interact", "action_id": "done"},
        )
        assert r_again.status_code == 200
        db.refresh(action)
        assert action.status == "COMPLETED"

        # Expired fail-closed
        _p2, expired = _seed_action(db, son.id, when=when, key="expired")
        expired.expires_at = when - timedelta(hours=1)
        db.flush()
        with pytest.raises(I8ActionCompletionError) as ei:
            complete_exact_operational_action(
                db, actor_user_id=son.id, action_id=expired.id, now=when
            )
        assert ei.value.code == "ACTION_EXPIRED"
        db.refresh(expired)
        assert expired.status == "ACTIVE"

        # Wrong client action id redirection blocked
        _p3, a1 = _seed_action(db, son.id, when=when, key="redir-a1")
        _p4, a2 = _seed_action(db, son.id, when=when, key="redir-a2")
        assert process_i8_coaching_followups(db, now=when, user_id=son.id, force=True) >= 1
        db.flush()
        n1 = (
            db.query(models.Notification)
            .filter(models.Notification.user_id == son.id)
            .order_by(models.Notification.id.desc())
            .first()
        )
        r_redir = client.post(
            f"/notifications/{n1.id}/feedback",
            headers=_auth(son.id),
            json={"reaction": "interact", "action_id": "done", "i8_action_id": a2.id},
        )
        assert r_redir.status_code == 422
        db.refresh(a1)
        db.refresh(a2)
        assert a1.status == "ACTIVE"
        assert a2.status == "ACTIVE"

    assert fam.mother_hs.linked_user_id is None
    assert db.query(models.User).filter(models.User.name == "MOTHER_ALS").count() == 0
