"""I10-B11 daily wellness digest — bounded I9 facts, truthful status, canonical I10."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.daily_wellness_digest import (
    DailyWellnessDataStatus,
    assemble_daily_wellness_digest_facts,
    build_daily_digest_occurrence_key,
    enqueue_daily_wellness_digest,
    render_digest_body,
)
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.i8_projection_service import get_i8_governed_context_projection
from backend.app.services.notification_engine import DecisionEngine, NotificationBuilder

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)


@pytest.fixture
def gate4_patch():
    with _GATE4_PATCH:
        yield


def _user(db, name: str = "digest-user", *, lang: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language=lang)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _self_setup(db, name: str = "digest-user") -> tuple[models.User, models.HealthSubject]:
    user = _user(db, name)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    return user, subject


def _engine(db) -> DecisionEngine:
    return DecisionEngine(db)


def _when(day: str = "2026-08-31", hour: int = 9) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00+00:00")


def _period_start(when: datetime) -> datetime:
    day = when.date()
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _rollup(
    db,
    user: models.User,
    subject: models.HealthSubject,
    when: datetime,
    *,
    sample_count: int = 12,
    coverage: float = 0.85,
    avg_value: float = 78.0,
    hours_before_end: float = 2.0,
) -> models.PhysiologicalMeasurementRollup:
    start = _period_start(when)
    end = start + timedelta(days=1)
    bucket_end = when - timedelta(hours=hours_before_end)
    row = models.PhysiologicalMeasurementRollup(
        user_id=user.id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        bucket_kind="daily",
        bucket_start=start,
        bucket_end=bucket_end,
        sample_count=sample_count,
        avg_value=avg_value,
        min_value=avg_value - 5,
        max_value=avg_value + 5,
        coverage=coverage,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _baseline(
    db,
    user: models.User,
    subject: models.HealthSubject,
    when: datetime,
    *,
    baseline_value: float = 72.0,
) -> models.PhysiologicalBaseline:
    start = _period_start(when) - timedelta(days=14)
    end = _period_start(when)
    row = models.PhysiologicalBaseline(
        user_id=user.id,
        health_subject_id=subject.id,
        measurement_type="heart_rate",
        baseline_method="PERSONAL_OBSERVED_BASELINE_V1",
        baseline_value=baseline_value,
        window_start=start,
        window_end=end,
        derived_at=when,
        coverage=0.8,
        valid_day_count=10,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _facts_and_enqueue(db, user: models.User, when: datetime):
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    key = build_daily_digest_occurrence_key(user_id=user.id, period_date=facts.observation_period_start.date())
    return facts, enqueue_daily_wellness_digest(db, facts=facts, occurrence_key=key)


# --- I9 bounded inputs ---


def test_digest_uses_bounded_i9_projection(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    projection = get_i8_governed_context_projection(db, account_user_id=user.id)
    assert facts.health_subject_id == projection.health_subject_id == subject.id
    assert len(facts.provenance_refs) >= 1


def test_no_raw_measurement_access_in_b11_module():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "daily_wellness_digest.py"
    text = root.read_text(encoding="utf-8")
    assert "models.PhysiologicalMeasurement" not in text
    assert "PhysiologicalMeasurementRollup" not in text
    assert "PhysiologicalBaseline" not in text


def test_self_health_subject_attribution(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert notif.health_subject_id == subject.id
    assert notif.user_id == user.id


def test_provenance_refs_preserved(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    facts, notif = _facts_and_enqueue(db, user, when)
    assert notif is not None
    assert len(facts.provenance_refs) >= 1
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.notification_id == notif.id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.DAILY_WELLNESS_DIGEST.value


# --- Data status ---


def test_sufficient_observed_data_status(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, sample_count=20, coverage=0.9)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.data_status == DailyWellnessDataStatus.SUFFICIENT_OBSERVED_DATA


def test_partial_data_status(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, coverage=0.2)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.data_status == DailyWellnessDataStatus.PARTIAL_DATA


def test_stale_data_status(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, hours_before_end=60.0)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.data_status == DailyWellnessDataStatus.STALE_DATA


def test_no_data_status(db):
    user, _ = _self_setup(db)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=_when())
    assert facts.data_status == DailyWellnessDataStatus.NO_DATA


def test_no_data_does_not_say_normal(db):
    user, _ = _self_setup(db)
    body = render_digest_body(assemble_daily_wellness_digest_facts(db, user_id=user.id, when=_when()))
    lowered = body.lower()
    for term in ("normal", "healthy", "safe", "nothing to worry"):
        assert term not in lowered


def test_partial_data_does_not_say_healthy(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, coverage=0.2)
    body = render_digest_body(assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when))
    assert "healthy" not in body.lower()


# --- Alert semantics ---


def test_no_qualifying_alert_is_factual_not_healthy(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert "No qualifying alert was recorded" in facts.alert_summary
    assert "healthy" not in facts.alert_summary.lower()
    assert "normal" not in facts.alert_summary.lower()


def test_no_false_reassurance_in_rendered_body(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    body = render_digest_body(assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when))
    for term in ("everything looks", "you are safe", "nothing to worry", "all good"):
        assert term not in body.lower()


# --- Baseline ---


def test_personal_observed_baseline_phrase_not_clinical_normal(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, avg_value=85.0)
    _baseline(db, user, subject, when, baseline_value=70.0)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.baseline_comparison is not None
    assert "personal observed baseline" in facts.baseline_comparison.lower()
    assert "clinical normal" in facts.baseline_comparison.lower()


def test_baseline_not_labeled_clinical_normal_in_body(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, avg_value=85.0)
    _baseline(db, user, subject, when, baseline_value=70.0)
    body = render_digest_body(assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when))
    assert "clinical normal range" in body.lower() or "not a clinical" in body.lower()


# --- I7 ---


def test_i7_daily_context_flag_when_available(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    start = _period_start(when)
    end = start + timedelta(days=1)
    db.add(
        models.UserPeriodSummary(
            user_id=user.id,
            summary_type="DAILY",
            period_start=start,
            period_end=end,
            generated_at=when,
            finalized_at=when,
            status="active",
            structured_summary_json=json.dumps({"headline": "bounded"}),
        )
    )
    db.commit()
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.i7_continuity_available is True


def test_b11_truthful_without_i7(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.i7_continuity_available is False
    assert facts.data_status == DailyWellnessDataStatus.SUFFICIENT_OBSERVED_DATA


def test_no_raw_i7_narrative_in_digest_body(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    start = _period_start(when)
    db.add(
        models.UserPeriodSummary(
            user_id=user.id,
            summary_type="DAILY",
            period_start=start,
            period_end=start + timedelta(days=1),
            generated_at=when,
            finalized_at=when,
            status="active",
            narrative_summary="SECRET TRANSCRIPT SHOULD NOT APPEAR",
        )
    )
    db.commit()
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert "SECRET TRANSCRIPT" not in (notif.body or "")


# --- I10 canonical path ---


def test_digest_routes_through_i10_intake(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert notif.i10_policy_decision_id is not None


def test_decision_ledger_created(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    row = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.notification_id == notif.id
    ).one()
    assert row.health_subject_id == subject.id
    assert row.recipient_user_id == user.id


def test_exactly_one_notification_per_daily_occurrence(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    count = db.query(func.count(models.Notification.id)).filter(models.Notification.user_id == user.id).scalar()
    assert count == 1


def test_no_parallel_legacy_persist(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    engine = _engine(db)
    with patch.object(engine.builder, "persist") as mock_legacy:
        engine.create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    mock_legacy.assert_not_called()


def test_no_direct_fcm_in_b11_module():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "daily_wellness_digest.py"
    text = root.read_text(encoding="utf-8").lower()
    assert "fcm" not in text
    assert "firebase" not in text


# --- Dedupe ---


def test_same_daily_period_duplicate_blocked(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    first = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    second = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert first is not None
    assert second is None


def test_next_day_allowed(db, gate4_patch):
    user, subject = _self_setup(db)
    _rollup(db, user, subject, _when("2026-08-31"))
    _rollup(db, user, subject, _when("2026-09-01"))
    d1 = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=_when("2026-08-31"))
    d2 = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=_when("2026-09-01"))
    assert d1 is not None and d2 is not None
    assert d1.id != d2.id


def test_occurrence_key_not_forever_dedupe(db):
    user, _ = _self_setup(db)
    k1 = build_daily_digest_occurrence_key(user_id=user.id, period_date=_when("2026-08-31").date())
    k2 = build_daily_digest_occurrence_key(user_id=user.id, period_date=_when("2026-09-01").date())
    assert k1 != k2


# --- Privacy ---


def test_health_sensitive_privacy(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif.privacy_class == I10PrivacyClass.HEALTH_SENSITIVE.value


def test_no_raw_measurement_in_public_body(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when, avg_value=123.456)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert "123.456" not in (notif.body or "")


# --- Chat continuity ---


def test_source_notification_id_compatible(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif.id is not None
    assert notif.user_id == user.id


def test_talk_to_sedi_metadata_bounded(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif.template_key == "daily_wellness_digest"
    assert notif.id is not None
    assert notif.source_id == when.date().isoformat()


# --- Boundaries ---


def test_no_direct_rag_in_b11_module():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "daily_wellness_digest.py"
    text = root.read_text(encoding="utf-8")
    for term in ("rag_service", "RAGService", "retrieve_augmented", "knowledge_retrieval"):
        assert term not in text


def test_no_diagnosis_language(db):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    body = render_digest_body(assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when))
    for term in ("diagnosis", "diagnosed", "disease", "disorder"):
        assert term not in body.lower()


def test_no_caregiver_delivery(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    grants = db.query(models.HealthSubjectNotificationGrant).count()
    assert grants == 0
    assert notif.user_id == user.id


def test_managed_subject_not_substituted(db, gate4_patch):
    owner = _user(db, "owner-digest")
    managed = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Parent")
    self_subj = ensure_self_subject_for_account(db, owner.id, commit=True)
    when = _when()
    _rollup(db, owner, self_subj, when)
    notif = _engine(db).create_daily_wellness_digest(user_id=owner.id, scheduled_for=when)
    assert notif.health_subject_id == self_subj.id
    assert notif.health_subject_id != managed.id


# --- Morning compatibility ---


def test_morning_check_in_regression_preserved(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    morning = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    assert morning is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == morning.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.MORNING_CHECK_IN.value


def test_morning_and_digest_distinct_occurrences_no_collision(db, gate4_patch):
    user, subject = _self_setup(db)
    when = _when()
    _rollup(db, user, subject, when)
    morning = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    digest = _engine(db).create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert morning is not None and digest is not None
    assert morning.id != digest.id
    families = {
        row.semantic_family
        for row in db.query(models.I10NotificationDecision).filter(
            models.I10NotificationDecision.recipient_user_id == user.id
        )
    }
    assert I10SemanticFamily.MORNING_CHECK_IN.value in families
    assert I10SemanticFamily.DAILY_WELLNESS_DIGEST.value in families
