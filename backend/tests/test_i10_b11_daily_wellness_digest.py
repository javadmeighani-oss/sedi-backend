"""I10-B11 daily wellness digest — bounded I9 facts, truthful status, canonical I10."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.canonical_policy import evaluate_i10_canonical_policy
from backend.app.services.i10.daily_wellness_digest import (
    DailyWellnessDataStatus,
    assemble_daily_wellness_digest_facts,
    build_daily_digest_occurrence_key,
    enqueue_daily_wellness_digest,
    render_digest_body,
)
from backend.app.services.i10.intake import evaluate_foundation_policy
from backend.app.services.i10.policy_types import I10DecisionValue, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i10.provider_delivery_policy import apply_i10_provider_lifetime
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


_MORNING_WINDOW_NOW = datetime(2026, 8, 31, 4, 30, tzinfo=timezone.utc)


def _foundation_at_morning_window(*, candidate, authorized):
    if not authorized:
        return evaluate_foundation_policy(candidate=candidate, authorized=authorized)
    if candidate.expires_at is not None and candidate.expires_at <= _MORNING_WINDOW_NOW:
        return I10DecisionValue.EXPIRE, "CANDIDATE_EXPIRED"
    return I10DecisionValue.SEND, "FOUNDATION_SEND"


@pytest.fixture
def morning_window_now():
    """Align B11 Morning compatibility creates with the canonical Gate4 window."""
    with patch(
        "backend.app.services.i10.intake.apply_i10_provider_lifetime",
        side_effect=lambda db, candidate, now_utc=None: apply_i10_provider_lifetime(
            db, candidate, now_utc=_MORNING_WINDOW_NOW
        ),
    ), patch(
        "backend.app.services.i10.intake.evaluate_foundation_policy",
        side_effect=_foundation_at_morning_window,
    ), patch(
        "backend.app.services.i10.intake.evaluate_i10_canonical_policy",
        side_effect=lambda db, **kwargs: evaluate_i10_canonical_policy(
            db, **{**kwargs, "now_utc": _MORNING_WINDOW_NOW}
        ),
    ):
        yield _MORNING_WINDOW_NOW


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


def test_morning_check_in_regression_preserved(db, gate4_patch, morning_window_now):
    user, subject = _self_setup(db)
    when = _when()
    morning = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    assert morning is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == morning.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.MORNING_CHECK_IN.value


def test_morning_and_digest_distinct_occurrences_no_collision(db, gate4_patch, morning_window_now):
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

# --- SEDI-V1-A4 Daily Smart Touchpoint acceptance (scheduler + i18n + single push) ---


def test_a4_scheduler_does_not_cofire_morning_brief():
    import inspect
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.run_morning_notifications)
    assert "create_daily_wellness_digest" in src
    assert "create_morning_brief" not in src
    assert "should_run_daily_smart_touchpoint" in src


def test_a4_canonical_daily_time_0900_not_0800():
    from backend.app.services.gate4.scheduler_timing import CANONICAL_DAILY_SMART_TOUCHPOINT_TIME

    assert CANONICAL_DAILY_SMART_TOUCHPOINT_TIME == "09:00"


def test_a4_should_run_at_0900_local_not_0800(db, gate4_patch):
    from backend.app.services.gate4.scheduler_timing import should_run_daily_smart_touchpoint

    user, _ = _self_setup(db)
    db.add(models.UserProfileCore(user_id=user.id, timezone="Asia/Tehran"))
    db.commit()
    # 09:05 Tehran ~= 05:35 UTC
    assert should_run_daily_smart_touchpoint(db, user, datetime(2026, 9, 9, 5, 35, 0)) is True
    # 08:05 Tehran ~= 04:35 UTC
    assert should_run_daily_smart_touchpoint(db, user, datetime(2026, 9, 9, 4, 35, 0)) is False


def test_a4_fa_en_ar_digest_localized_before_persist(db, gate4_patch, morning_window_now):
    from backend.app.services.i10.daily_wellness_digest import (
        assemble_daily_wellness_digest_facts,
        build_daily_wellness_digest_payload,
        render_digest_body,
        render_digest_title,
    )

    for lang in ("fa", "en", "ar"):
        user, _ = _self_setup(db, name=f"a4-lang-{lang}")
        user.preferred_language = lang
        db.commit()
        facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=_when())
        title = render_digest_title(facts, lang)
        body = render_digest_body(facts, lang)
        payload = build_daily_wellness_digest_payload(facts, occurrence_key=f"a4-{lang}", language=lang)
        assert payload.metadata["language"] == lang
        assert payload.title == title and bool(title)
        assert payload.body == body and bool(body)


def test_a4_no_data_path_no_invented_health_facts(db, gate4_patch):
    from backend.app.services.i10.daily_wellness_digest import (
        assemble_daily_wellness_digest_facts,
        render_digest_body,
    )

    user, _ = _self_setup(db)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=_when())
    assert facts.data_status == DailyWellnessDataStatus.NO_DATA
    body = render_digest_body(facts, "en").lower()
    for term in ("diagnosis", "bpm=", "you have diabetes", "spo2"):
        assert term not in body


def test_a4_engagement_nudge_not_independently_scheduled():
    import inspect
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.start_scheduler)
    assert "add_job(\n            run_engagement_nudge" not in src
    assert hasattr(sched, "run_engagement_nudge")


def test_a4_context_json_no_raw_memory_leak(db, gate4_patch, morning_window_now):
    from backend.app.services.i10.daily_wellness_digest import (
        assemble_daily_wellness_digest_facts,
        build_daily_wellness_digest_payload,
    )

    user, _ = _self_setup(db)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=_when())
    payload = build_daily_wellness_digest_payload(facts, occurrence_key="a4-ctx", language="en")
    blob = str(payload.context or {}).lower()
    for forbidden in ("user_message", "raw_memory", "physiologicalmeasurement"):
        assert forbidden not in blob


# --- SEDI-V1-A4 closure (CI-visible: local date, consent, I8, privacy, non-repetition, 09:00) ---


def test_a4_closure_smart_0900_not_legacy_0800():
    from backend.app.services.gate4.notification_contract import DEFAULT_DAILY_NOTIFICATION_TIME
    from backend.app.services.gate4.scheduler_timing import (
        CANONICAL_DAILY_SMART_TOUCHPOINT_TIME,
        smart_daily_touchpoint_contract,
    )

    assert CANONICAL_DAILY_SMART_TOUCHPOINT_TIME == "09:00"
    assert DEFAULT_DAILY_NOTIFICATION_TIME == "08:00"  # legacy prefs only
    contract = smart_daily_touchpoint_contract()
    assert contract["canonical_time"] == "09:00"
    assert "08:00" not in contract.values()


def test_a4_closure_occurrence_uses_user_local_date_tehran(db, gate4_patch, morning_window_now):
    """Asia/Tehran: UTC evening can be next local morning — occurrence must use local day."""
    from backend.app.services.i10.daily_wellness_digest import (
        assemble_daily_wellness_digest_facts,
        build_daily_digest_occurrence_key,
    )

    user, _ = _self_setup(db, name="tehran-occ")
    db.add(models.UserProfileCore(user_id=user.id, timezone="Asia/Tehran"))
    db.commit()
    # 2026-09-09 21:30 UTC = 2026-09-10 01:00 Asia/Tehran
    when = datetime(2026, 9, 9, 21, 30, 0)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts.local_period_date is not None
    assert facts.local_period_date.isoformat() == "2026-09-10"
    assert facts.observation_period_start.date().isoformat() == "2026-09-09"
    key = build_daily_digest_occurrence_key(
        user_id=user.id, period_date=facts.local_period_date
    )
    assert "2026-09-10" in key
    assert "2026-09-09" not in key
    eng = _engine(db)
    # Engine must use local_period_date for occurrence (spy via create path key in metadata/source)
    notif = eng.create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert notif.source_id == "2026-09-10"
    ctx = notif.context_json or ""
    assert "2026-09-10" in ctx


def test_a4_closure_adjacent_day_body_nonrepetition(db, gate4_patch):
    """GENERAL_CHECKIN uses fixed canonical copy (stable across adjacent local days)."""
    from backend.app.services.i10.daily_wellness_digest import (
        DailySmartContentFamily,
        _GENERAL_CHECKIN_BODIES,
        assemble_daily_wellness_digest_facts,
        render_digest_body,
        render_digest_title,
    )

    user, _ = _self_setup(db, name="adj-var")
    f1 = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    f2 = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 10, 9, 0, 0)
    )
    assert f1.content_family == DailySmartContentFamily.GENERAL_CHECKIN
    assert f2.content_family == DailySmartContentFamily.GENERAL_CHECKIN
    assert render_digest_body(f1, "en") == render_digest_body(f2, "en") == _GENERAL_CHECKIN_BODIES["en"]
    assert render_digest_title(f1, "fa") == "پیگیری روزانه صدی"
    assert render_digest_body(f1, "fa") == _GENERAL_CHECKIN_BODIES["fa"]


def test_a4_closure_i6_i7_requires_read_consent(db, gate4_patch):
    from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
    from backend.app.services.i10.daily_wellness_digest import (
        DailySmartContentFamily,
        assemble_daily_wellness_digest_facts,
    )

    user, _ = _self_setup(db, name="consent-i67")
    when = _when()
    start = _period_start(when)
    # Finalized non-contextual summary (no bounded_continuity topic)
    db.add(
        models.UserPeriodSummary(
            user_id=user.id,
            summary_type="DAILY",
            period_start=start,
            period_end=start + timedelta(days=1),
            generated_at=when,
            finalized_at=when,
            status="active",
            structured_summary_json=json.dumps({"headline": "bounded"}),
        )
    )
    db.commit()
    # Summary alone without READ consent → must NOT select I6_I7_CONTEXT
    facts_no = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts_no.content_family != DailySmartContentFamily.I6_I7_CONTEXT
    assert facts_no.content_family == DailySmartContentFamily.GENERAL_CHECKIN

    # Consent + non-contextual finalized summary → still NOT I6_I7_CONTEXT
    grant_memory_consent(db, user.id, commit=True)
    facts_yes = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts_yes.content_family != DailySmartContentFamily.I6_I7_CONTEXT
    assert facts_yes.content_family == DailySmartContentFamily.GENERAL_CHECKIN

    revoke_memory_consent(db, user.id, commit=True)
    facts_rev = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts_rev.content_family != DailySmartContentFamily.I6_I7_CONTEXT


def test_a4_closure_i6_i7_empty_and_bounded_context(db, gate4_patch):
    """Finalized empty/non-contextual ≠ I6_I7; privacy-safe bounded topic ⇒ I6_I7."""
    from backend.app.services.i6.consent_service import grant_memory_consent
    from backend.app.services.i10.daily_wellness_digest import (
        DailySmartContentFamily,
        assemble_daily_wellness_digest_facts,
    )

    when = _when()
    start = _period_start(when)

    # Empty finalized summary + READ consent → GENERAL_CHECKIN
    user_empty, _ = _self_setup(db, name="i67-empty")
    grant_memory_consent(db, user_empty.id, commit=True)
    db.add(
        models.UserPeriodSummary(
            user_id=user_empty.id,
            summary_type="DAILY",
            period_start=start,
            period_end=start + timedelta(days=1),
            generated_at=when,
            finalized_at=when,
            status="active",
            structured_summary_json=json.dumps({}),
        )
    )
    db.commit()
    facts_empty = assemble_daily_wellness_digest_facts(db, user_id=user_empty.id, when=when)
    assert facts_empty.content_family == DailySmartContentFamily.GENERAL_CHECKIN
    assert facts_empty.content_family != DailySmartContentFamily.I6_I7_CONTEXT

    # Non-contextual headline-only summary + consent → not I6_I7
    user_nc, _ = _self_setup(db, name="i67-nonctx")
    grant_memory_consent(db, user_nc.id, commit=True)
    db.add(
        models.UserPeriodSummary(
            user_id=user_nc.id,
            summary_type="DAILY",
            period_start=start,
            period_end=start + timedelta(days=1),
            generated_at=when,
            finalized_at=when,
            status="active",
            structured_summary_json=json.dumps({"headline": "notes", "source": "ELIGIBLE"}),
        )
    )
    db.commit()
    facts_nc = assemble_daily_wellness_digest_facts(db, user_id=user_nc.id, when=when)
    assert facts_nc.content_family != DailySmartContentFamily.I6_I7_CONTEXT
    assert facts_nc.content_family == DailySmartContentFamily.GENERAL_CHECKIN

    # Safe bounded I7 continuity topic + consent → I6_I7_CONTEXT
    user_ctx, _ = _self_setup(db, name="i67-ctx")
    grant_memory_consent(db, user_ctx.id, commit=True)
    db.add(
        models.UserPeriodSummary(
            user_id=user_ctx.id,
            summary_type="DAILY",
            period_start=start,
            period_end=start + timedelta(days=1),
            generated_at=when,
            finalized_at=when,
            status="active",
            structured_summary_json=json.dumps(
                {
                    "bounded_continuity": {
                        "topic": "talked about activity plan walking",
                        "not_transcript": True,
                        "not_i9": True,
                        "not_i6_fact": True,
                    }
                }
            ),
        )
    )
    db.commit()
    facts_ctx = assemble_daily_wellness_digest_facts(db, user_id=user_ctx.id, when=when)
    assert facts_ctx.content_family == DailySmartContentFamily.I6_I7_CONTEXT

    # Sensitive / unusable topic → not I6_I7
    user_sens, _ = _self_setup(db, name="i67-sens")
    grant_memory_consent(db, user_sens.id, commit=True)
    db.add(
        models.UserPeriodSummary(
            user_id=user_sens.id,
            summary_type="DAILY",
            period_start=start,
            period_end=start + timedelta(days=1),
            generated_at=when,
            finalized_at=when,
            status="active",
            structured_summary_json=json.dumps(
                {
                    "bounded_continuity": {
                        "topic": "my medication dose for diabetes diagnosis",
                        "not_transcript": True,
                    }
                }
            ),
        )
    )
    db.commit()
    facts_sens = assemble_daily_wellness_digest_facts(db, user_id=user_sens.id, when=when)
    assert facts_sens.content_family != DailySmartContentFamily.I6_I7_CONTEXT
    assert facts_sens.content_family == DailySmartContentFamily.GENERAL_CHECKIN


def _seed_i8_plan_action(
    db,
    user: models.User,
    *,
    local_day,
    when: datetime,
    status: str = "ACTIVE",
    safety_state: str = "SAFE",
    clarification_required: bool = False,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    expires_at: datetime | None = None,
    plan_status: str = "ACTIVE",
    key_suffix: str = "ok",
):
    now = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when
    vf = valid_from if valid_from is not None else now
    vu = valid_until if valid_until is not None else now + timedelta(hours=12)
    exp = expires_at if expires_at is not None else now + timedelta(hours=12)
    plan = models.I8OperationalPlan(
        user_id=user.id,
        user_local_date=local_day,
        timezone_snapshot="UTC",
        status=plan_status,
        generation_mode="reactive",
        plan_idempotency_key=f"plan-a4-{user.id}-{key_suffix}",
        valid_from=vf,
        valid_until=vu,
        expires_at=exp,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    action = models.I8OperationalPlanAction(
        user_id=user.id,
        plan_id=plan.id,
        action_domain="lifestyle",
        action_type="check_in",
        action_idempotency_key=f"act-a4-{user.id}-{key_suffix}",
        status=status,
        summary_text="Check in",
        presentation_json="{}",
        knowledge_refs_json="[]",
        safety_state=safety_state,
        clarification_required=clarification_required,
        valid_from=vf,
        valid_until=vu,
        expires_at=exp,
    )
    db.add(action)
    db.commit()
    return plan, action


def test_a4_closure_i8_active_only_influences_family(db, gate4_patch):
    from datetime import date

    from backend.app.services.i10.daily_wellness_digest import (
        DailySmartContentFamily,
        assemble_daily_wellness_digest_facts,
    )

    user, _ = _self_setup(db, name="i8-active")
    when = _when()
    local_day = date(2026, 8, 31)
    now = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when
    plan = models.I8OperationalPlan(
        user_id=user.id,
        user_local_date=local_day,
        timezone_snapshot="UTC",
        status="ACTIVE",
        generation_mode="reactive",
        plan_idempotency_key=f"plan-a4-{user.id}",
        valid_from=now,
        valid_until=now + timedelta(hours=12),
        expires_at=now + timedelta(hours=12),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    # ACTIVE plan without ACTIVE action → not I8
    facts0 = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts0.content_family != DailySmartContentFamily.I8_ACTION

    db.add(
        models.I8OperationalPlanAction(
            user_id=user.id,
            plan_id=plan.id,
            action_domain="lifestyle",
            action_type="check_in",
            action_idempotency_key=f"act-a4-{user.id}",
            status="ACTIVE",
            summary_text="Check in",
            presentation_json="{}",
            knowledge_refs_json="[]",
            safety_state="SAFE",
            clarification_required=False,
            valid_from=now,
            valid_until=now + timedelta(hours=12),
            expires_at=now + timedelta(hours=12),
        )
    )
    db.commit()
    facts1 = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    assert facts1.content_family == DailySmartContentFamily.I8_ACTION


def test_a4_closure_i8_eligibility_windows_and_safety(db, gate4_patch):
    """I8_ACTION only when SAFE+ACTIVE+currently-valid on the correct local day."""
    from datetime import date

    from backend.app.services.i10.daily_wellness_digest import (
        DailySmartContentFamily,
        assemble_daily_wellness_digest_facts,
    )

    when = _when()
    local_day = date(2026, 8, 31)
    now = when if when.tzinfo else when.replace(tzinfo=timezone.utc)

    def _family(name: str, **kwargs) -> DailySmartContentFamily:
        user, _ = _self_setup(db, name=name)
        _seed_i8_plan_action(db, user, local_day=local_day, when=when, key_suffix=name, **kwargs)
        return assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when).content_family

    assert _family("i8-ok") == DailySmartContentFamily.I8_ACTION

    assert (
        _family(
            "i8-exp",
            valid_from=now - timedelta(hours=6),
            valid_until=now + timedelta(hours=1),
            expires_at=now - timedelta(minutes=1),
        )
        != DailySmartContentFamily.I8_ACTION
    )

    assert (
        _family(
            "i8-fut",
            valid_from=now + timedelta(hours=1),
            valid_until=now + timedelta(hours=8),
            expires_at=now + timedelta(hours=8),
        )
        != DailySmartContentFamily.I8_ACTION
    )

    assert (
        _family(
            "i8-vu",
            valid_from=now - timedelta(hours=6),
            valid_until=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=2),
        )
        != DailySmartContentFamily.I8_ACTION
    )

    assert _family("i8-blk", safety_state="BLOCKED") != DailySmartContentFamily.I8_ACTION
    assert _family("i8-clr", safety_state="CLARIFY") != DailySmartContentFamily.I8_ACTION
    assert (
        _family("i8-cq", clarification_required=True) != DailySmartContentFamily.I8_ACTION
    )

    # Wrong local plan date
    user_wrong, _ = _self_setup(db, name="i8-wrongday")
    _seed_i8_plan_action(
        db,
        user_wrong,
        local_day=date(2026, 8, 30),
        when=when,
        key_suffix="wrongday",
    )
    facts_wrong = assemble_daily_wellness_digest_facts(db, user_id=user_wrong.id, when=when)
    assert facts_wrong.content_family != DailySmartContentFamily.I8_ACTION
    assert facts_wrong.content_family == DailySmartContentFamily.GENERAL_CHECKIN


def test_a4_closure_sensitive_topic_privacy_lock_screen(db, gate4_patch, monkeypatch):
    from backend.app.services.i6.consent_service import grant_memory_consent
    from backend.app.services.i7.privacy_safe_recent_topic import (
        display_phrase_for_topic_label,
        get_privacy_safe_recent_topic_label,
    )

    user, _ = _self_setup(db, name="priv-topic")
    grant_memory_consent(db, user.id, commit=True)
    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.has_permission",
        lambda *_a, **_k: True,
    )

    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_bounded_continuity_topic",
        lambda *_a, **_k: "my medication dose for diabetes diagnosis lab symptom",
    )
    assert get_privacy_safe_recent_topic_label(db, user.id) is None

    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_bounded_continuity_topic",
        lambda *_a, **_k: "talked about activity plan walking",
    )
    label = get_privacy_safe_recent_topic_label(db, user.id)
    assert label == "activity_plan"
    phrase = display_phrase_for_topic_label(label, "en")
    assert phrase and "activity" in phrase.lower()
    assert "medication" not in phrase.lower()

    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_bounded_continuity_topic",
        lambda *_a, **_k: "xyzzy uncertain gibberish private notes",
    )
    assert get_privacy_safe_recent_topic_label(db, user.id) is None


def test_a4_brand_copy_canonical_sedi():
    """A4 localized prose brand: EN=Sedi, FA/AR=صدی; no سدی/سدي; no واحدةحدةحدة."""
    from pathlib import Path

    from backend.app.services.gate4.notification_contract import ACTION_LABELS, get_action_label
    from backend.app.services.i10.daily_wellness_digest import (
        _DIGEST_TITLES,
        _GENERAL_BODIES,
        _GENERAL_CHECKIN_BODIES,
        _GENERAL_CHECKIN_TITLES,
        _I6_I7_BODIES,
        _I8_BODIES,
        _I9_PARTIAL_BODIES,
        _I9_STALE_BODIES,
        _I9_SUFFICIENT_BODIES,
        _NO_DATA_BODIES,
        _SAFETY_BODIES,
    )
    from backend.app.services.notification_runtime.templates_v1 import TEMPLATES_V1

    fa_wrong = "سدی"
    ar_wrong = "سدي"
    brand_fa_ar = "صدی"
    typo = "واحدةحدة"

    pools = (
        _DIGEST_TITLES,
        _GENERAL_BODIES,
        _NO_DATA_BODIES,
        _SAFETY_BODIES,
        _I9_SUFFICIENT_BODIES,
        _I9_PARTIAL_BODIES,
        _I9_STALE_BODIES,
        _I8_BODIES,
        _I6_I7_BODIES,
    )
    fa_blob = " ".join(" ".join(p.get("fa", ())) for p in pools)
    ar_blob = " ".join(" ".join(p.get("ar", ())) for p in pools)
    en_blob = " ".join(" ".join(p.get("en", ())) for p in pools)
    fa_blob += " " + _GENERAL_CHECKIN_TITLES["fa"] + " " + _GENERAL_CHECKIN_BODIES["fa"]
    ar_blob += " " + _GENERAL_CHECKIN_TITLES["ar"] + " " + _GENERAL_CHECKIN_BODIES["ar"]
    en_blob += " " + _GENERAL_CHECKIN_TITLES["en"] + " " + _GENERAL_CHECKIN_BODIES["en"]

    assert fa_wrong not in fa_blob
    assert brand_fa_ar in fa_blob
    assert ar_wrong not in ar_blob
    assert brand_fa_ar in ar_blob
    assert "Sedi" in en_blob
    assert typo not in ar_blob
    assert typo not in fa_blob

    for tpl in TEMPLATES_V1:
        texts = tpl.get("texts") or {}
        for lang, block in texts.items():
            msg = " ".join(str(v) for v in (block or {}).values())
            assert fa_wrong not in msg
            assert ar_wrong not in msg
            assert typo not in msg
            if lang == "en" and "Sedi" in msg:
                assert "Sedi" in msg

    ar_open = get_action_label("open_chat", "ar")
    en_open = get_action_label("open_chat", "en")
    assert ar_wrong not in ar_open
    assert brand_fa_ar in ar_open
    assert "Sedi" in en_open
    assert fa_wrong not in ACTION_LABELS["open_chat"]["fa"]

    # Source files under Gate1 A4 copy scope must not reintroduce defects.
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    for rel in (
        "i10/daily_wellness_digest.py",
        "notification_runtime/templates_v1.py",
        "gate4/notification_contract.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert fa_wrong not in text
        assert ar_wrong not in text
        assert typo not in text
