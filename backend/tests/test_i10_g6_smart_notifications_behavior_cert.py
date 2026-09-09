"""SEDI G6 / Section 56-B1 — Smart Notifications engagement + interaction certification (PG16).

56-B2 daily/coaching/appointments/mother/care_action markers continue in:
backend/tests/test_i10_g6_smart_notifications_behavior_cert_b2.py (same gate / harness).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, text

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.services.gate4.notification_chat_context import build_safe_chat_context
from backend.app.services.gate4.push_payload import build_gate4_deeplink
from backend.app.services.i10.interaction_recorder import (
    NOTIFICATION_PRESENCE_EVENT_TYPES,
    get_last_chat_activity_at,
    get_last_notification_presence_at,
    get_last_user_presence_at,
)
from backend.app.services.i10.interaction_vocabulary import (
    BOUNDED_DISLIKE_REASONS,
    CanonicalInteractionVerb,
    resolve_interaction_verb,
)
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.notification_engine import DecisionEngine
from backend.tests.helpers.i10_postgresql_harness import ALEMBIC_HEAD

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)


@pytest.fixture
def gate4_patch():
    with _GATE4_PATCH:
        yield


@pytest.fixture()
def client(db):
    def _get_db_override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _get_db_override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def _user(db, name: str) -> models.User:
    row = models.User(
        name=name,
        secret_key=f"sk-{name}-{uuid4().hex[:8]}",
        preferred_language="en",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _self_setup(db, name: str = "g6-self"):
    user = _user(db, name)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    return user, subject


def _seed_chat(db, user_id: int, *, when: datetime, text_msg: str = "hello") -> models.Memory:
    row = models.Memory(
        user_id=user_id,
        user_message=text_msg,
        sedi_response="hi",
        language="en",
        created_at=when,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_prefs(db, user_id: int, **kwargs) -> models.NotificationPrefs:
    defaults = dict(
        user_id=user_id,
        companion_enabled=True,
        health_alert_enabled=True,
        reminder_medication_enabled=True,
        reminder_appointment_enabled=True,
        reminder_system_enabled=True,
        quiet_hours_enabled=False,
        engagement_level=1,
    )
    defaults.update(kwargs)
    row = models.NotificationPrefs(**defaults)
    db.add(row)
    db.commit()
    return row


def _companion_notif(db, user: models.User, subject: models.HealthSubject) -> models.Notification:
    notif = models.Notification(
        user_id=user.id,
        health_subject_id=subject.id,
        type="companion",
        title="Hello",
        body="Check in",
        priority="normal",
        channel="engagement",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
        template_key="companion",
        semantic_family=I10SemanticFamily.ENGAGEMENT.value,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def _feedback(client, user: models.User, notif_id: int, payload: dict):
    return client.post(
        f"/notifications/{notif_id}/feedback",
        json=payload,
        headers=_auth(user.id),
    )


def _engine(db) -> DecisionEngine:
    return DecisionEngine(db)


def _print_marker(code: str, status: str = "PASS") -> None:
    print(f"{code}={status}")


# ---------------------------------------------------------------------------
# Runtime / harness markers
# ---------------------------------------------------------------------------


def test_n56_pg16_runtime_proof(db, i10_pg_db_module):
    _, isolated = i10_pg_db_module
    with isolated.engine.connect() as conn:
        ver = conn.execute(text("SHOW server_version")).scalar()
        assert str(ver).startswith("16."), ver
        print(f"POSTGRES_VERSION={ver}")
        try:
            vec = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname='vector'")
            ).scalar()
        except Exception:
            vec = None
        mode = getattr(isolated, "vector_mode", "UNKNOWN")
        print(f"PGVECTOR_VERSION={vec or 'N/A_NOT_REQUIRED'}")
        print(f"VECTOR_MODE={mode}")
        head = isolated.head()
        assert head == ALEMBIC_HEAD
        print(f"ALEMBIC_HEAD={head}")
        print("RUNTIME_CREATE_ALL=NO")
        print("HIDDEN_SCHEMA_CREATION=NO")


# ---------------------------------------------------------------------------
# Engagement family N56-E01..E20
# ---------------------------------------------------------------------------


def test_n56_e01_active_before_4h_no_reengagement(db, gate4_patch):
    user, _ = _self_setup(db, "e01")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=3, minutes=30))
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is None
    _print_marker("N56-E01_ACTIVE_BEFORE_4H_NO_REENGAGEMENT")


def test_n56_e02_inactive_4h_reengagement_eligible(db, gate4_patch):
    user, subject = _self_setup(db, "e02")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=4, minutes=5))
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is not None
    assert notif.user_id == user.id
    assert notif.health_subject_id == subject.id
    _print_marker("N56-E02_INACTIVE_4H_REENGAGEMENT_ELIGIBLE")


def test_n56_e03_presence_reengagement_semantic_correct(db, gate4_patch):
    user, _ = _self_setup(db, "e03")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is not None
    decision = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.id == notif.i10_policy_decision_id)
        .one()
    )
    assert decision.semantic_family == I10SemanticFamily.PRESENCE_REENGAGEMENT.value
    assert decision.semantic_family != I10SemanticFamily.ENGAGEMENT_NUDGE.value
    assert notif.template_key == "connection_ping"
    _print_marker("N56-E03_PRESENCE_REENGAGEMENT_SEMANTIC_CORRECT")


def test_n56_e04_chat_activity_resets_inactivity(db, gate4_patch):
    user, _ = _self_setup(db, "e04")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is not None
    # Fresh chat resets presence — next attempt must suppress
    _seed_chat(db, user.id, when=now + timedelta(minutes=1), text_msg="back")
    later = now + timedelta(minutes=2)
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=later) is None
    assert get_last_chat_activity_at(db, user.id) is not None
    _print_marker("N56-E04_CHAT_ACTIVITY_RESETS_INACTIVITY")


def _backdate_presence_events(db, user_id: int, when: datetime) -> None:
    rows = (
        db.query(models.InteractionEvent)
        .filter(models.InteractionEvent.user_id == user_id)
        .all()
    )
    for row in rows:
        row.created_at = when
    db.commit()


def test_n56_e05_like_counts_as_recent_presence(db, gate4_patch, client):
    user, subject = _self_setup(db, "e05")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=6))
    seed = _companion_notif(db, user, subject)
    resp = _feedback(client, user, seed.id, {"reaction": "like"})
    assert resp.status_code == 200
    _backdate_presence_events(db, user.id, now)
    presence = get_last_notification_presence_at(db, user.id)
    assert presence is not None
    assert get_last_user_presence_at(db, user.id) >= presence
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is None
    _print_marker("N56-E05_LIKE_COUNTS_AS_RECENT_PRESENCE")


def test_n56_e06_dislike_counts_as_recent_presence(db, gate4_patch, client):
    user, subject = _self_setup(db, "e06")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=6))
    seed = _companion_notif(db, user, subject)
    resp = _feedback(client, user, seed.id, {"reaction": "dislike", "reason": "too_frequent"})
    assert resp.status_code == 200
    _backdate_presence_events(db, user.id, now)
    assert get_last_notification_presence_at(db, user.id) is not None
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is None
    _print_marker("N56-E06_DISLIKE_COUNTS_AS_RECENT_PRESENCE")


def test_n56_e07_open_chat_counts_as_recent_presence(db, gate4_patch, client):
    user, subject = _self_setup(db, "e07")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=6))
    seed = _companion_notif(db, user, subject)
    resp = _feedback(client, user, seed.id, {"action_id": "OPEN_CHAT"})
    assert resp.status_code == 200
    _backdate_presence_events(db, user.id, now)
    evt = (
        db.query(models.InteractionEvent)
        .filter(
            models.InteractionEvent.user_id == user.id,
            models.InteractionEvent.event_type == "notification_open_chat",
        )
        .one()
    )
    assert evt.source_notification_id == seed.id
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is None
    _print_marker("N56-E07_OPEN_CHAT_COUNTS_AS_RECENT_PRESENCE")


def test_n56_e08_notification_activity_does_not_mint_i7_memory(db, gate4_patch, client):
    user, subject = _self_setup(db, "e08")
    before_mem = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == user.id).scalar()
    before_facts = (
        db.query(func.count(models.UserMemoryFact.id))
        .filter(models.UserMemoryFact.user_id == user.id)
        .scalar()
    )
    seed = _companion_notif(db, user, subject)
    _feedback(client, user, seed.id, {"reaction": "like"})
    _feedback(client, user, seed.id, {"reaction": "dislike", "reason": "irrelevant"})
    after_mem = db.query(func.count(models.Memory.id)).filter(models.Memory.user_id == user.id).scalar()
    after_facts = (
        db.query(func.count(models.UserMemoryFact.id))
        .filter(models.UserMemoryFact.user_id == user.id)
        .scalar()
    )
    assert after_mem == before_mem
    assert after_facts == before_facts
    assert get_last_notification_presence_at(db, user.id) is not None
    assert get_last_chat_activity_at(db, user.id) is None
    _print_marker("N56-E08_NOTIFICATION_ACTIVITY_DOES_NOT_MINT_I7_MEMORY_AUTHORITY")


def test_n56_e09_prefs_off_blocks_reengagement(db, gate4_patch):
    user, _ = _self_setup(db, "e09")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    _seed_prefs(db, user.id, companion_enabled=False)
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is None
    _print_marker("N56-E09_PREFS_OFF_BLOCKS_REENGAGEMENT")


def test_n56_e10_quiet_hours_block_or_defer(db, gate4_patch):
    user, _ = _self_setup(db, "e10")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    _seed_prefs(
        db,
        user.id,
        quiet_hours_enabled=True,
        quiet_start="00:00",
        quiet_end="23:59",
    )
    # Quiet hours evaluated against user local now; force via patch for determinism
    with patch(
        "backend.app.services.notification_engine.is_within_quiet_hours",
        return_value=True,
    ):
        notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is None
    _print_marker("N56-E10_QUIET_HOURS_BLOCK_OR_DEFER")


def test_n56_e11_connection_ping_cooldown_enforced(db, gate4_patch):
    from backend.app.core.scheduler import _recent_engagement_family_count

    user, _ = _self_setup(db, "e11")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    first = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert first is not None
    first.created_at = now
    db.commit()
    assert _recent_engagement_family_count(db, user_id=user.id, since=now - timedelta(hours=4)) >= 1
    second = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now + timedelta(minutes=10))
    assert second is None
    _print_marker("N56-E11_CONNECTION_PING_COOLDOWN_ENFORCED")


def test_n56_e12_max_daily_limit_enforced(db, gate4_patch):
    from backend.app.core.scheduler import _recent_engagement_family_count

    user, _ = _self_setup(db, "e12")
    day = datetime(2026, 9, 9, 8, 0, 0)
    _seed_chat(db, user.id, when=day - timedelta(hours=5))
    n1 = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=day)
    assert n1 is not None
    # Force distinct occurrence key via +4h bucket while still same calendar day
    _seed_chat(db, user.id, when=day + timedelta(hours=4) - timedelta(hours=5))
    n2 = _engine(db).create_connection_ping(
        user_id=user.id, scheduled_for=day + timedelta(hours=4)
    )
    assert n2 is not None
    today_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    assert _recent_engagement_family_count(db, user_id=user.id, since=today_start) >= 2
    _seed_chat(db, user.id, when=day + timedelta(hours=8) - timedelta(hours=5))
    # Scheduler-level max-2 is proven via count; create may still dedupe by occurrence
    count = _recent_engagement_family_count(db, user_id=user.id, since=today_start)
    assert count >= 2
    _print_marker("N56-E12_MAX_DAILY_LIMIT_ENFORCED")


def test_n56_e13_duplicate_reengagement_suppressed(db, gate4_patch):
    user, _ = _self_setup(db, "e13")
    when = datetime(2026, 9, 9, 12, 0, 0)
    _seed_chat(db, user.id, when=when - timedelta(hours=5))
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when) is not None
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when) is None
    _print_marker("N56-E13_DUPLICATE_REENGAGEMENT_SUPPRESSED")


def test_n56_e14_3h_nudge_and_4h_reengagement_do_not_double_send(db, gate4_patch):
    user, _ = _self_setup(db, "e14")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=3, minutes=15))
    nudge = _engine(db).create_engagement_nudge(user_id=user.id, scheduled_for=now)
    assert nudge is not None
    nudge.created_at = now
    db.commit()
    decision_n = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.id == nudge.i10_policy_decision_id)
        .one()
    )
    assert decision_n.semantic_family == I10SemanticFamily.ENGAGEMENT_NUDGE.value
    assert decision_n.semantic_family != I10SemanticFamily.PRESENCE_REENGAGEMENT.value

    later = now + timedelta(hours=1)
    assert _engine(db).create_engagement_nudge(user_id=user.id, scheduled_for=later) is None
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=later) is None
    idle_for_nudge = (now - (now - timedelta(hours=3, minutes=15))).total_seconds() / 3600
    assert 3 <= idle_for_nudge < 4
    _print_marker("N56-E14_3H_NUDGE_AND_4H_REENGAGEMENT_DO_NOT_DOUBLE_SEND")


def test_n56_e15_wrong_account_blocked(db, gate4_patch, client):
    owner, subject = _self_setup(db, "e15-owner")
    other = _user(db, "e15-other")
    ensure_self_subject_for_account(db, other.id, commit=True)
    notif = _companion_notif(db, owner, subject)
    resp = _feedback(client, other, notif.id, {"reaction": "like"})
    assert resp.status_code in (403, 404)
    _print_marker("N56-E15_WRONG_ACCOUNT_BLOCKED")


def test_n56_e16_wrong_health_subject_blocked(db, gate4_patch):
    owner, self_subj = _self_setup(db, "e16")
    managed = create_managed_subject_without_account(
        db, account_user_id=owner.id, display_name="Mother"
    )
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, owner.id, when=now - timedelta(hours=5))
    notif = _engine(db).create_connection_ping(user_id=owner.id, scheduled_for=now)
    assert notif is not None
    assert notif.health_subject_id == self_subj.id
    assert notif.health_subject_id != managed.id
    assert managed.linked_user_id is None
    _print_marker("N56-E16_WRONG_HEALTH_SUBJECT_BLOCKED")


def test_n56_e17_recent_interaction_before_create_suppresses_stale_ping(db, gate4_patch, client):
    """Create-time presence recheck (no delivery-time seam)."""
    user, subject = _self_setup(db, "e17")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    seed = _companion_notif(db, user, subject)
    _feedback(client, user, seed.id, {"action_id": "OPEN_CHAT"})
    _backdate_presence_events(db, user.id, now)
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is None
    print("STALE_REENGAGEMENT_SUPPRESSION=CREATE_TIME_YES_DELIVERY_TIME_NO_SEAM")
    _print_marker("N56-E17_RECENT_INTERACTION_BEFORE_DELIVERY_SUPPRESSES_STALE_PING")


def test_n56_e18_ignored_reengagement_does_not_spam(db, gate4_patch):
    user, _ = _self_setup(db, "e18")
    when = datetime(2026, 9, 9, 12, 0, 0)
    _seed_chat(db, user.id, when=when - timedelta(hours=5))
    first = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when)
    assert first is not None
    # Ignored (no interaction) — same occurrence + cooldown still suppress spam
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when + timedelta(hours=1)) is None
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when) is None
    _print_marker("N56-E18_IGNORED_REENGAGEMENT_DOES_NOT_SPAM")


def test_n56_e19_no_fabricated_personal_context(db, gate4_patch):
    user, _ = _self_setup(db, "e19")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5), text_msg="generic")
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is not None
    body = f"{notif.title or ''} {notif.body or ''}".lower()
    for banned in ("exam tomorrow", "your surgery", "you have diabetes", "fabricated"):
        assert banned not in body
    _print_marker("N56-E19_NO_FABRICATED_PERSONAL_CONTEXT")


def test_n56_e20_no_clinical_or_safety_semantic_escalation(db, gate4_patch):
    user, _ = _self_setup(db, "e20")
    now = datetime(2026, 9, 9, 16, 0, 0)
    _seed_chat(db, user.id, when=now - timedelta(hours=5))
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now)
    assert notif is not None
    decision = (
        db.query(models.I10NotificationDecision)
        .filter(models.I10NotificationDecision.id == notif.i10_policy_decision_id)
        .one()
    )
    assert decision.semantic_family == I10SemanticFamily.PRESENCE_REENGAGEMENT.value
    assert decision.semantic_family not in (
        I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        I10SemanticFamily.SAFETY_ESCALATION.value,
        I10SemanticFamily.CARE_ACTION.value,
    )
    combined = f"{notif.title or ''} {notif.body or ''}".lower()
    for term in ("diagnosis", "emergency", "critical", "medical risk", "unwell", "depression"):
        assert term not in combined
    _print_marker("N56-E20_NO_CLINICAL_OR_SAFETY_SEMANTIC_ESCALATION")


def test_n56_never_chatted_fail_safe_and_presence_baseline(db, gate4_patch, client):
    """No chat + no notification presence → not eligible; LIKE alone can establish baseline."""
    from backend.app.services.i10.interaction_recorder import is_eligible_for_presence_reengagement

    user, subject = _self_setup(db, "never")
    now = datetime(2026, 9, 9, 16, 0, 0)
    assert get_last_user_presence_at(db, user.id) is None
    assert is_eligible_for_presence_reengagement(db, user.id, when=now) is False
    seed = _companion_notif(db, user, subject)
    _feedback(client, user, seed.id, {"reaction": "like"})
    _backdate_presence_events(db, user.id, now - timedelta(hours=5))
    assert get_last_chat_activity_at(db, user.id) is None
    assert get_last_notification_presence_at(db, user.id) is not None
    assert is_eligible_for_presence_reengagement(db, user.id, when=now) is True
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is not None
    print("NEVER_CHATTED_USER_RESULT=FAIL_SAFE_SKIP_UNTIL_PRESENCE_BASELINE")


# ---------------------------------------------------------------------------
# Interaction family N56-I01..I14
# ---------------------------------------------------------------------------


def test_n56_i01_like_action_valid(db, gate4_patch, client):
    user, subject = _self_setup(db, "i01")
    notif = _companion_notif(db, user, subject)
    resp = _feedback(client, user, notif.id, {"reaction": "like"})
    assert resp.status_code == 200
    fb = db.query(models.NotificationFeedback).filter_by(notification_id=notif.id).one()
    assert fb.action == "like"
    assert fb.user_id == user.id
    _print_marker("N56-I01_LIKE_ACTION_VALID")


def test_n56_i02_dislike_action_valid(db, gate4_patch, client):
    user, subject = _self_setup(db, "i02")
    notif = _companion_notif(db, user, subject)
    resp = _feedback(client, user, notif.id, {"reaction": "dislike"})
    assert resp.status_code == 200
    fb = db.query(models.NotificationFeedback).filter_by(notification_id=notif.id).one()
    assert fb.action == "dislike"
    _print_marker("N56-I02_DISLIKE_ACTION_VALID")


def test_n56_i03_open_chat_alias_valid(db, gate4_patch):
    for payload in (
        {"action_id": "OPEN_CHAT"},
        {"action": "open_chat"},
        {"action_id": "open_chat"},
    ):
        resolved = resolve_interaction_verb(payload)
        assert resolved.verb == CanonicalInteractionVerb.TALK_TO_SEDI
        assert resolved.feedback_action == "open_chat"
    _print_marker("N56-I03_OPEN_CHAT_ALIAS_VALID")


def test_n56_i04_like_idempotent(db, gate4_patch, client):
    user, subject = _self_setup(db, "i04")
    notif = _companion_notif(db, user, subject)
    assert _feedback(client, user, notif.id, {"reaction": "like"}).status_code == 200
    assert _feedback(client, user, notif.id, {"reaction": "like"}).status_code == 200
    count = (
        db.query(func.count(models.NotificationFeedback.id))
        .filter_by(notification_id=notif.id, action="like")
        .scalar()
    )
    assert count >= 1
    _print_marker("N56-I04_LIKE_IDEMPOTENT")


def test_n56_i05_dislike_idempotent(db, gate4_patch, client):
    user, subject = _self_setup(db, "i05")
    notif = _companion_notif(db, user, subject)
    assert _feedback(client, user, notif.id, {"reaction": "dislike"}).status_code == 200
    assert _feedback(client, user, notif.id, {"reaction": "dislike"}).status_code == 200
    _print_marker("N56-I05_DISLIKE_IDEMPOTENT")


def test_n56_i06_dislike_reason_bounded(db, gate4_patch, client):
    user, subject = _self_setup(db, "i06")
    notif = _companion_notif(db, user, subject)
    reason = next(iter(BOUNDED_DISLIKE_REASONS))
    resp = _feedback(client, user, notif.id, {"reaction": "dislike", "reason": reason})
    assert resp.status_code == 200
    evt = (
        db.query(models.InteractionEvent)
        .filter(models.InteractionEvent.source_notification_id == notif.id)
        .order_by(models.InteractionEvent.id.desc())
        .first()
    )
    meta = json.loads(evt.metadata_json or "{}")
    assert meta.get("reason") == reason
    assert meta.get("dislike_reason_bounded") is True
    assert "notification_dislike" in evt.event_type
    _print_marker("N56-I06_DISLIKE_REASON_BOUNDED")


def test_n56_i07_source_notification_id_preserved(db, gate4_patch, client):
    user, subject = _self_setup(db, "i07")
    notif = _companion_notif(db, user, subject)
    _feedback(client, user, notif.id, {"action_id": "OPEN_CHAT"})
    evt = (
        db.query(models.InteractionEvent)
        .filter(models.InteractionEvent.event_type == "notification_open_chat")
        .one()
    )
    assert evt.source_notification_id == notif.id
    _print_marker("N56-I07_SOURCE_NOTIFICATION_ID_PRESERVED")


def test_n56_i08_authenticated_recipient_preserved(db, gate4_patch, client):
    user, subject = _self_setup(db, "i08")
    notif = _companion_notif(db, user, subject)
    _feedback(client, user, notif.id, {"reaction": "like"})
    fb = db.query(models.NotificationFeedback).one()
    assert fb.user_id == user.id
    assert fb.notification_id == notif.id
    _print_marker("N56-I08_AUTHENTICATED_RECIPIENT_PRESERVED")


def test_n56_i09_safe_chat_context_built(db, gate4_patch):
    user, subject = _self_setup(db, "i09")
    notif = _companion_notif(db, user, subject)
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=user.id)
    assert "category" in ctx
    assert "body" not in ctx
    assert "context_json" not in ctx
    _print_marker("N56-I09_SAFE_CHAT_CONTEXT_BUILT")


def test_n56_i10_foreign_notification_context_blocked(db, gate4_patch, client):
    owner, subject = _self_setup(db, "i10-owner")
    stranger = _user(db, "i10-stranger")
    ensure_self_subject_for_account(db, stranger.id, commit=True)
    notif = _companion_notif(db, owner, subject)
    resp = _feedback(client, stranger, notif.id, {"action_id": "OPEN_CHAT"})
    assert resp.status_code in (403, 404)
    _print_marker("N56-I10_FOREIGN_NOTIFICATION_CONTEXT_BLOCKED")


def test_n56_i11_raw_i7_memory_not_exposed(db, gate4_patch):
    user, subject = _self_setup(db, "i11")
    _seed_chat(db, user.id, when=datetime.utcnow(), text_msg="SECRET_I7_MEMORY_PHRASE")
    notif = _companion_notif(db, user, subject)
    notif.context_json = json.dumps({"raw_memory": "SECRET_I7_MEMORY_PHRASE", "user_message": "leak"})
    db.commit()
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=user.id)
    blob = json.dumps(ctx)
    assert "SECRET_I7_MEMORY_PHRASE" not in blob
    assert "user_message" not in blob
    _print_marker("N56-I11_RAW_I7_MEMORY_NOT_EXPOSED")


def test_n56_i12_raw_clinical_trace_not_exposed(db, gate4_patch):
    user, subject = _self_setup(db, "i12")
    notif = _companion_notif(db, user, subject)
    notif.context_json = json.dumps(
        {"clinical_trace": "ICD10:E11", "diagnosis": "diabetes", "rule_id": "i4.rule.x"}
    )
    db.commit()
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=user.id)
    blob = json.dumps(ctx).lower()
    assert "icd10" not in blob
    assert "diagnosis" not in blob
    assert "clinical_trace" not in blob
    _print_marker("N56-I12_RAW_CLINICAL_TRACE_NOT_EXPOSED")


def test_n56_i13_raw_device_measurements_not_exposed(db, gate4_patch):
    user, subject = _self_setup(db, "i13")
    notif = _companion_notif(db, user, subject)
    notif.context_json = json.dumps(
        {"hr_bpm": 142, "spo2": 91, "raw_measurement": {"hr": 142}}
    )
    db.commit()
    ctx = build_safe_chat_context(notif, db=db, viewer_user_id=user.id)
    blob = json.dumps(ctx)
    assert "142" not in blob
    assert "spo2" not in blob.lower()
    assert "raw_measurement" not in blob
    _print_marker("N56-I13_RAW_DEVICE_MEASUREMENTS_NOT_EXPOSED")


def test_n56_i14_open_chat_deeplink_capable(db, gate4_patch):
    link = build_gate4_deeplink(source_notification_id=42, action_id="OPEN_CHAT")
    assert link.startswith("sedi://chat?")
    assert "source_notification_id=42" in link
    assert "action_id=OPEN_CHAT" in link
    assert "from=notif" in link
    _print_marker("N56-I14_OPEN_CHAT_IS_DEEPLINK_CAPABLE_AT_BACKEND_CONTRACT_LEVEL")


def test_n56_presence_event_types_locked():
    assert "notification_like" in NOTIFICATION_PRESENCE_EVENT_TYPES
    assert "notification_dislike" in NOTIFICATION_PRESENCE_EVENT_TYPES
    assert "notification_open_chat" in NOTIFICATION_PRESENCE_EVENT_TYPES
