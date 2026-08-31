"""Section45 067 lifelong memory foundation — sqlite service contracts. No Production."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.database import Base
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i6.legacy_fact_freeze import LegacyFactStackFrozen, assert_legacy_write_allowed
from backend.app.services.i6.memory_writes import correct_fact, delete_fact, write_fact
from backend.app.services.i7.export_jobs import create_export_job, materialize_export_job
from backend.app.services.i7.fact_reconciliation import census_legacy_stacks, reconcile_legacy_facts
from backend.app.services.i7.lifelong_profile import rebuild_lifelong_profile
from backend.app.services.i7.period_summaries import period_bounds, resolve_week_start
from backend.app.services.i7.timeline import list_lifelong_timeline
from backend.app.services.knowledge.service import accept_candidate


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            models.User.__table__,
            models.UserConsent.__table__,
            models.UserConsentScope.__table__,
            models.UserMemoryFact.__table__,
            models.UserPeriodSummary.__table__,
            models.UserLifelongProfile.__table__,
            models.UserMemoryExportJob.__table__,
            models.Memory.__table__,
            models.UserFact.__table__,
            models.KcFactCandidate.__table__,
            models.KcUserFact.__table__,
            models.UserProfileFact.__table__,
            models.UserLifestyleEvent.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db, name: str, lang: str = "en") -> models.User:
    row = models.User(name=name, secret_key="s45", preferred_language=lang)
    db.add(row)
    db.flush()
    return row


def test_no_066_migration_file():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    assert list(versions.glob("066*.py")) == []
    assert (versions / "067_i7_lifelong_memory_foundation.py").is_file()
    assert (versions / "068_i7_wave2_governed_memory_lifecycle.py").is_file()


def test_alembic_head_is_071():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["074_i10_notification_domain_foundation"]
    rev074 = script.get_revision("074_i10_notification_domain_foundation")
    assert rev074.down_revision == "073_i9_subject_native_rollup_baseline"
    rev073 = script.get_revision("073_i9_subject_native_rollup_baseline")
    assert rev073.down_revision == "072_i9_device_claim_gateway_lifecycle_foundation"
    rev072 = script.get_revision("072_i9_device_claim_gateway_lifecycle_foundation")
    assert rev072.down_revision == "071_i9_health_subject_device_packet_foundation"
    rev071 = script.get_revision("071_i9_health_subject_device_packet_foundation")
    assert rev071.down_revision == "070_i8_proactive_evaluation_ledger"
    rev = script.get_revision("070_i8_proactive_evaluation_ledger")
    assert rev.down_revision == "069_i8_operational_plan_state_foundation"
    rev = script.get_revision("069_i8_operational_plan_state_foundation")
    assert rev.down_revision == "068_i7_wave2_governed_memory_lifecycle"
    rev = script.get_revision("068_i7_wave2_governed_memory_lifecycle")
    assert rev.down_revision == "067_i7_lifelong_memory_foundation"
    rev = script.get_revision("067_i7_lifelong_memory_foundation")
    assert rev.down_revision == "065_i5_know04_connectors_change_intelligence"


def test_week_semantics_fa_saturday_en_monday():
    assert resolve_week_start("fa-IR") == 5
    assert resolve_week_start("en") == 0
    now = datetime(2026, 8, 13, 12, 0, 0)
    mon0, mon1 = period_bounds("WEEKLY", now=now, week_start=0)
    sat0, sat1 = period_bounds("WEEKLY", now=now, week_start=5)
    assert (mon1 - mon0).days == 7
    assert (sat1 - sat0).days == 7
    import pytz

    tz = pytz.timezone("Asia/Tehran")
    assert mon0.astimezone(tz).weekday() == 0
    assert sat0.astimezone(tz).weekday() == 5


def test_legacy_writes_frozen_by_default(monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    with pytest.raises(LegacyFactStackFrozen):
        assert_legacy_write_allowed("user_facts")
    with pytest.raises(LegacyFactStackFrozen):
        assert_legacy_write_allowed("kc_user_facts")
    with pytest.raises(LegacyFactStackFrozen):
        assert_legacy_write_allowed("user_profile_facts")


def test_profile_export_isolation_and_not_diagnosis(db):
    a = _user(db, "s45-a")
    b = _user(db, "s45-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    write_fact(db, a.id, "lifestyle", "diet_notes", "vegetarian", commit=True)
    write_fact(db, b.id, "lifestyle", "diet_notes", "pescatarian", commit=True)
    pa = rebuild_lifelong_profile(db, a.id, commit=True)
    assert "not_diagnosis" in pa.structured_profile_json
    assert "I6_FACTS_ARE_SOT" in pa.structured_profile_json
    assert "pescatarian" not in (pa.structured_profile_json or "")
    job = create_export_job(db, a.id, actor_user_id=a.id, commit=True)
    ready = materialize_export_job(db, job.id, a.id, commit=True)
    assert ready.status == "ready"
    assert ready.content_class == "MEMORY_BUNDLE"
    with pytest.raises(Exception):
        materialize_export_job(db, job.id, b.id, commit=True)


def test_correction_invalidates_profile(db):
    user = _user(db, "s45-inv")
    grant_memory_consent(db, user.id, commit=True)
    write_fact(db, user.id, "lifestyle", "diet_notes", "vegetarian", commit=True)
    profile = rebuild_lifelong_profile(db, user.id, commit=True)
    correct_fact(db, user.id, "lifestyle", "diet_notes", "pescatarian", commit=True)
    db.refresh(profile)
    assert profile.status == "stale"
    rebuilt = rebuild_lifelong_profile(db, user.id, commit=True)
    assert rebuilt.status == "active"
    assert rebuilt.version == profile.version + 1
    assert rebuilt.id != profile.id
    delete_fact(db, user.id, "lifestyle", "diet_notes", commit=True)


def test_reconciliation_requires_consent_and_is_nondestructive(db):
    user = _user(db, "s45-rec")
    db.add(models.UserFact(user_id=user.id, key="diet", value_json='"veg"', source="manual", confidence=0.9))
    db.commit()
    census = {c.source_table: c for c in census_legacy_stacks(db)}
    assert census["user_facts"].total_rows == 1
    assert census["user_facts"].rows_unmappable == 1
    dry = reconcile_legacy_facts(db, dry_run=True, persist=False)
    assert dry.unmappable_no_consent == 1
    assert db.query(models.UserFact).count() == 1
    assert db.query(models.UserMemoryFact).count() == 0
    grant_memory_consent(db, user.id, commit=True)
    first = reconcile_legacy_facts(db, dry_run=False, persist=True)
    assert first.mapped == 1
    assert db.query(models.UserFact).count() == 1
    umf = db.query(models.UserMemoryFact).one()
    assert umf.consent_id is not None
    assert umf.provenance.startswith("s45_reconcile:user_facts:")
    second = reconcile_legacy_facts(db, dry_run=False, persist=True)
    assert second.skipped_existing == 1
    assert db.query(models.UserMemoryFact).count() == 1


def test_valid_time_two_periods_not_flattened(db):
    user = _user(db, "s45-vt")
    grant_memory_consent(db, user.id, commit=True)
    t0 = datetime(2026, 1, 1)
    t1 = datetime(2032, 1, 1)
    db.add(
        models.KcUserFact(
            user_id=user.id,
            fact_type="vegetarian",
            value_json="false",
            verified_by="user",
            valid_from=t0,
            valid_to=t1,
        )
    )
    db.add(
        models.KcUserFact(
            user_id=user.id,
            fact_type="vegetarian",
            value_json="true",
            verified_by="user",
            valid_from=t1,
            valid_to=None,
        )
    )
    db.commit()
    reconcile_legacy_facts(db, dry_run=False, persist=True)
    rows = db.query(models.UserMemoryFact).filter_by(user_id=user.id, key="vegetarian").all()
    assert len(rows) == 2
    values = {r.value_json for r in rows}
    assert "false" in values and "true" in values


def test_timeline_user_isolation(db):
    a = _user(db, "s45-tl-a")
    b = _user(db, "s45-tl-b")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    db.add(
        models.UserLifestyleEvent(
            user_id=a.id,
            event_type="walk",
            occurred_at=datetime(2026, 8, 1),
            source="manual",
        )
    )
    db.add(
        models.UserLifestyleEvent(
            user_id=b.id,
            event_type="secret",
            occurred_at=datetime(2026, 8, 1),
            source="manual",
        )
    )
    db.commit()
    rows = list_lifelong_timeline(db, a.id)
    assert any(r["event_type"] == "walk" for r in rows)
    assert all(r["user_id"] == a.id for r in rows)
    assert all("secret" not in str(r) for r in rows)


def test_memory_retain_until_set_on_orm_insert(db):
    user = _user(db, "s45-mem")
    row = models.Memory(user_id=user.id, user_message="hello", sedi_response="hi")
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.retain_until is not None
    assert row.retain_until > datetime.utcnow() + timedelta(days=20)


def test_accept_candidate_frozen(db, monkeypatch):
    monkeypatch.delenv("SEDI_LEGACY_FACT_WRITES_ENABLED", raising=False)
    user = _user(db, "s45-kc")
    from backend.app.services.knowledge.service import create_candidate

    cand = create_candidate(
        db=db,
        user_id=user.id,
        source="chat_extraction_v1",
        fact_type="sleep_quality",
        value_json='"poor"',
        confidence=0.9,
    )
    with pytest.raises(LegacyFactStackFrozen):
        accept_candidate(db, cand.id, verified_by="system")
    assert db.query(models.KcUserFact).count() == 0
