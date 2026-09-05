"""GATE=SEDI-V1-BE-I8-PROACTIVE-FOLLOWUP-LOOP-02 — DONE → exact I8 action completion."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.i8.action_completion import (
    CANONICAL_TERMINAL_ACTION_STATUS,
    complete_exact_operational_action,
)
from backend.app.services.i8.local_day import resolve_local_day_window
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i10.coaching_worker import process_i8_coaching_followups
from backend.app.services.i10.interaction_vocabulary import CanonicalInteractionVerb
from backend.tests.helpers.stage_b_family_fixture import SCENARIO_ID, seed_stage_b_family

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4 = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG = patch(
    "backend.app.services.i10.coaching_worker.coaching_followup_enabled",
    return_value=True,
)


@pytest.fixture
def patches():
    with _GATE4, _FLAG:
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
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}


def _prefs(db, user_id: int, *, companion=True, health=True) -> None:
    existing = db.query(models.NotificationPrefs).filter_by(user_id=user_id).first()
    if existing is None:
        db.add(
            models.NotificationPrefs(
                user_id=user_id,
                companion_enabled=companion,
                health_alert_enabled=health,
                reminder_system_enabled=True,
            )
        )
    else:
        existing.companion_enabled = companion
        existing.health_alert_enabled = health
    if db.query(models.PushDevice).filter_by(user_id=user_id, is_active=True).first() is None:
        db.add(
            models.PushDevice(
                user_id=user_id, platform="android", fcm_token=f"fcm-{user_id}-{user_id}", is_active=True
            )
        )
    db.flush()


def _seed_routine_action(db, user_id: int, *, when, key: str = "walk-1", summary: str = "Walk"):
    if db.query(models.UserProfileCore).filter_by(user_id=user_id).first() is None:
        db.add(models.UserProfileCore(user_id=user_id, timezone="UTC"))
        db.flush()
    window = resolve_local_day_window(db, user_id, now_utc=when)
    repo = I8OperationalRepository()
    plan = repo.create_plan(
        db,
        user_id=user_id,
        user_local_date=window.user_local_date,
        timezone_snapshot=window.timezone_snapshot,
        generation_mode="proactive",
        plan_idempotency_key=f"plan-{user_id}-{key}",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    action = repo.create_action(
        db,
        user_id=user_id,
        plan_id=plan.id,
        action_domain="routine",
        action_type="routine_item",
        action_idempotency_key=key,
        summary_text=summary,
        presentation_json="{}",
        knowledge_refs_json="[]",
        context_refs_json="[]",
        safety_state="SAFE",
        valid_from=window.valid_from,
        valid_until=window.valid_until,
        expires_at=window.expires_at,
    )
    db.flush()
    return plan, action, when


def _deliver(db, user_id: int, when) -> models.Notification:
    db.commit()
    assert process_i8_coaching_followups(db, now=when, user_id=user_id, force=True) == 1
    return db.query(models.Notification).filter_by(user_id=user_id).order_by(models.Notification.id.desc()).first()


def _feedback(client, user_id, notif_id, payload):
    return client.post(
        f"/notifications/{notif_id}/feedback",
        headers=_auth(user_id),
        json=payload,
    )


def test_scenario_id():
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"


def test_a_happy_path_done_completes_exact_action(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _plan, action, when = _seed_routine_action(db, fam.son.id, when=when)
    notif = _deliver(db, fam.son.id, when)
    assert notif is not None
    r = _feedback(client, fam.son.id, notif.id, {"reaction": "interact", "action_id": "done"})
    assert r.status_code == 200, r.text
    db.refresh(action)
    assert action.status == CANONICAL_TERMINAL_ACTION_STATUS
    fb = db.query(models.NotificationFeedback).filter_by(notification_id=notif.id).one()
    assert fb.action == "done"
    ev = (
        db.query(models.InteractionEvent)
        .filter_by(source_notification_id=notif.id, event_type="notification_done")
        .one()
    )
    assert ev.user_id == fam.son.id


def test_b_repeated_done_idempotent(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when)
    notif = _deliver(db, fam.son.id, when)
    assert _feedback(client, fam.son.id, notif.id, {"reaction": "interact", "action_id": "done"}).status_code == 200
    assert _feedback(client, fam.son.id, notif.id, {"reaction": "interact", "action_id": "done"}).status_code == 200
    db.refresh(action)
    assert action.status == "COMPLETED"
    assert db.query(models.NotificationFeedback).filter_by(notification_id=notif.id, action="done").count() == 2


def test_c_completed_not_redelivered(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when)
    notif = _deliver(db, fam.son.id, when)
    _feedback(client, fam.son.id, notif.id, {"reaction": "interact", "action_id": "done"})
    db.refresh(action)
    assert action.status == "COMPLETED"
    assert process_i8_coaching_followups(db, now=when, user_id=fam.son.id, force=True) == 0
    assert db.query(models.Notification).filter_by(user_id=fam.son.id).count() == 1


def test_d_future_same_domain_action_not_suppressed(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, a1, when = _seed_routine_action(db, fam.son.id, when=when, key="walk-1")
    n1 = _deliver(db, fam.son.id, when)
    _feedback(client, fam.son.id, n1.id, {"reaction": "interact", "action_id": "done"})
    _, a2, when = _seed_routine_action(db, fam.son.id, when=when, key="walk-2", summary="Evening walk")
    assert process_i8_coaching_followups(db, now=when, user_id=fam.son.id, force=True) == 1
    db.refresh(a2)
    assert a2.status == "ACTIVE"
    assert a1.id != a2.id


def test_e_cross_user_blocked(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when)
    notif = _deliver(db, fam.son.id, when)
    r = _feedback(client, fam.stranger.id, notif.id, {"reaction": "interact", "action_id": "done"})
    assert r.status_code == 403
    db.refresh(action)
    assert action.status == "ACTIVE"


def test_f_wrong_client_action_id_redirect_blocked(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, a1, when = _seed_routine_action(db, fam.son.id, when=when, key="a1")
    _, a2, when = _seed_routine_action(db, fam.son.id, when=when, key="a2", summary="Other")
    n1 = _deliver(db, fam.son.id, when)  # delivers lowest id first (a1)
    # Force another delivery for a2
    assert process_i8_coaching_followups(db, now=when, user_id=fam.son.id, force=True) == 1
    r = _feedback(
        client,
        fam.son.id,
        n1.id,
        {"reaction": "interact", "action_id": "done", "i8_action_id": a2.id},
    )
    assert r.status_code == 422
    db.refresh(a1)
    db.refresh(a2)
    assert a1.status == "ACTIVE"
    assert a2.status == "ACTIVE"


def test_g_unrelated_notification_cannot_complete(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when)
    _deliver(db, fam.son.id, when)
    unrelated = models.Notification(
        user_id=fam.son.id,
        type="connection_ping",
        title="Other",
        body="Unrelated",
        priority="normal",
        channel="push",
        status="queued",
    )
    db.add(unrelated)
    db.flush()
    r = _feedback(client, fam.son.id, unrelated.id, {"reaction": "interact", "action_id": "done"})
    assert r.status_code == 422
    db.refresh(action)
    assert action.status == "ACTIVE"


def test_h_provenance_mismatch_fail_closed(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, a1, when = _seed_routine_action(db, fam.son.id, when=when, key="p1")
    _, a2, when = _seed_routine_action(db, fam.son.id, when=when, key="p2", summary="B")
    n1 = _deliver(db, fam.son.id, when)
    # Tamper notification.source_id to other action while decision still points at a1
    n1.source_id = str(a2.id)
    db.flush()
    r = _feedback(client, fam.son.id, n1.id, {"reaction": "interact", "action_id": "done"})
    assert r.status_code == 422
    db.refresh(a1)
    assert a1.status == "ACTIVE"


def test_i_invalid_lifecycle_fail_closed(db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when)
    action.status = "SUPERSEDED"
    db.flush()
    from backend.app.services.i8.action_completion import I8ActionCompletionError

    with pytest.raises(I8ActionCompletionError) as ei:
        complete_exact_operational_action(db, actor_user_id=fam.son.id, action_id=action.id, now=when)
    assert ei.value.code == "ACTION_NOT_COMPLETABLE"


@pytest.mark.parametrize(
    "payload,expect_active",
    [
        ({"reaction": "interact", "action_id": "NOT_NOW"}, True),
        ({"reaction": "interact", "action_id": "TALK_LATER"}, True),
        ({"reaction": "dislike"}, True),
        ({"reaction": "dislike", "reason": "too_frequent"}, True),
        ({"reaction": "like"}, True),
        ({"reaction": "interact", "action_id": "ACK_THANKS"}, True),
        ({"reaction": "seen"}, True),
        ({"reaction": "interact", "action_id": "OPEN_CHAT"}, True),
    ],
)
def test_j_q_non_done_verbs_do_not_mutate_i8(client, db, patches, payload, expect_active):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when, key=f"v-{hash(str(payload)) % 10000}")
    notif = _deliver(db, fam.son.id, when)
    r = _feedback(client, fam.son.id, notif.id, payload)
    assert r.status_code == 200, r.text
    db.refresh(action)
    assert (action.status == "ACTIVE") is expect_active


def test_r_mother_isolation(client, db, patches):
    fam = seed_stage_b_family(db, with_device=False, with_i10_grants=False)
    assert fam.mother_hs.linked_user_id is None
    assert fam.mother_hs.subject_kind == "managed"
    when = datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    _prefs(db, fam.son.id)
    _, action, when = _seed_routine_action(db, fam.son.id, when=when)
    notif = _deliver(db, fam.son.id, when)
    _feedback(client, fam.son.id, notif.id, {"reaction": "interact", "action_id": "done"})
    db.refresh(action)
    assert action.user_id == fam.son.id
    assert action.user_id != fam.mother_hs.id
    assert db.query(models.UserLifelongProfile).filter_by(user_id=fam.mother_hs.id).count() == 0


def test_s_no_score_semantics_in_completion_module():
    from pathlib import Path

    src = Path("backend/app/services/i8/action_completion.py").read_text(encoding="utf-8")
    for bad in ("adherence", "disruption", "improvement_score", "missed_habit", "diagnosis"):
        assert bad not in src.lower()
    assert CanonicalInteractionVerb.DONE.value == "DONE"
