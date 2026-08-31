"""I8 operational plan state migration rehearsal (069) — isolated PostgreSQL only."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DataError, IntegrityError


ROOT = Path(__file__).resolve().parents[1]


def _url() -> str | None:
    return os.environ.get("DB03_REHEARSAL_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")


def _alembic_cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def test_migration_069_static_audit():
    versions = ROOT / "alembic" / "versions"
    files = list(versions.glob("069*.py"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "069_i8_operational_plan_state_foundation" in body
    assert re.search(r"down_revision.*068_i7_wave2_governed_memory_lifecycle", body)
    assert "i8_operational_plans" in body
    assert "i8_operational_plan_actions" in body
    assert "uq_i8_plan_id_user" in body
    assert "fk_i8_action_plan_user" in body
    assert "notifications" not in body
    assert "user_care_plan_items" not in body
    assert not re.search(r"(?i)create\s+extension\s+.*vector", body)
    assert "USING ivfflat" not in body.lower()
    assert "USING hnsw" not in body.lower()


def test_alembic_single_head_is_070():
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory

    cfg = AlembicConfig(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["077_i10_medication_adherence_foundation"]
    rev076 = script.get_revision("077_i10_medication_adherence_foundation")
    assert rev076.down_revision == "075_i10_care_network_identity_grants"
    rev075 = script.get_revision("075_i10_care_network_identity_grants")
    assert rev075.down_revision == "074_i10_notification_domain_foundation"
    rev074 = script.get_revision("074_i10_notification_domain_foundation")
    assert rev074.down_revision == "073_i9_subject_native_rollup_baseline"
    rev073 = script.get_revision("073_i9_subject_native_rollup_baseline")
    assert rev073.down_revision == "072_i9_device_claim_gateway_lifecycle_foundation"
    rev072 = script.get_revision("072_i9_device_claim_gateway_lifecycle_foundation")
    assert rev072.down_revision == "071_i9_health_subject_device_packet_foundation"
    rev071 = script.get_revision("071_i9_health_subject_device_packet_foundation")
    assert rev071.down_revision == "070_i8_proactive_evaluation_ledger"
    rev070 = script.get_revision("070_i8_proactive_evaluation_ledger")
    assert rev070.down_revision == "069_i8_operational_plan_state_foundation"
    rev = script.get_revision("069_i8_operational_plan_state_foundation")
    assert rev.down_revision == "068_i7_wave2_governed_memory_lifecycle"


def _seed_user(conn) -> int:
    row = conn.execute(
        text(
            "INSERT INTO users (name, secret_key, preferred_language, created_at) "
            "VALUES ('i8_test', 'k', 'en', now()) RETURNING id"
        )
    ).one()
    return int(row[0])


def _plan_row(
    user_id: int,
    *,
    local_date: date,
    tz: str = "America/New_York",
    status: str = "ACTIVE",
    idem: str = "plan-k1",
    valid_until: datetime | None = None,
    expires_at: datetime | None = None,
    superseded_by: int | None = None,
    proactive_key: str | None = None,
) -> dict:
    vf = datetime(2026, 8, 21, 4, 0, tzinfo=timezone.utc)
    vu = valid_until or datetime(2026, 8, 22, 3, 59, 59, tzinfo=timezone.utc)
    exp = expires_at or (vu + timedelta(hours=36))
    return {
        "user_id": user_id,
        "user_local_date": local_date,
        "timezone_snapshot": tz,
        "status": status,
        "generation_mode": "reactive",
        "plan_idempotency_key": idem,
        "proactive_evaluation_key": proactive_key,
        "valid_from": vf,
        "valid_until": vu,
        "expires_at": exp,
        "superseded_by_plan_id": superseded_by,
    }


def _insert_plan(conn, row: dict) -> int:
    result = conn.execute(
        text(
            """
            INSERT INTO i8_operational_plans (
                user_id, user_local_date, timezone_snapshot, status, generation_mode,
                plan_idempotency_key, proactive_evaluation_key,
                valid_from, valid_until, expires_at, superseded_by_plan_id
            ) VALUES (
                :user_id, :user_local_date, :timezone_snapshot, :status, :generation_mode,
                :plan_idempotency_key, :proactive_evaluation_key,
                :valid_from, :valid_until, :expires_at, :superseded_by_plan_id
            ) RETURNING id
            """
        ),
        row,
    ).one()
    return int(result[0])


def _insert_action(conn, *, plan_id: int, user_id: int, idem: str = "act-k1") -> int:
    vf = datetime(2026, 8, 21, 4, 0, tzinfo=timezone.utc)
    vu = datetime(2026, 8, 22, 3, 59, 59, tzinfo=timezone.utc)
    exp = vu + timedelta(hours=36)
    result = conn.execute(
        text(
            """
            INSERT INTO i8_operational_plan_actions (
                plan_id, user_id, action_domain, action_type, status,
                action_idempotency_key, summary_text, presentation_json,
                safety_state, clarification_required, knowledge_refs_json,
                valid_from, valid_until, expires_at
            ) VALUES (
                :plan_id, :user_id, 'nutrition', 'meal_suggestion', 'ACTIVE',
                :action_idempotency_key, :summary_text, :presentation_json,
                'SAFE', false, :knowledge_refs_json,
                :valid_from, :valid_until, :expires_at
            ) RETURNING id
            """
        ),
        {
            "plan_id": plan_id,
            "user_id": user_id,
            "action_idempotency_key": idem,
            "summary_text": "Eat a balanced lunch",
            "presentation_json": json.dumps({"title": "Lunch", "items": []}),
            "knowledge_refs_json": json.dumps([{"knowledge_unit_id": 1}]),
            "valid_from": vf,
            "valid_until": vu,
            "expires_at": exp,
        },
    ).one()
    return int(result[0])


@pytest.mark.skipif(not _url(), reason="No TEST_DATABASE_URL / DB03_REHEARSAL_DATABASE_URL")
def test_i8_068_069_rehearsal():
    url = _url()
    assert url
    if os.environ.get("DB03_ALLOW_DESTRUCTIVE_REHEARSAL") != "YES":
        pytest.skip("Set DB03_ALLOW_DESTRUCTIVE_REHEARSAL=YES")
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    cfg = _alembic_cfg(url)
    command.upgrade(cfg, "068_i7_wave2_governed_memory_lifecycle")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "068_i7_wave2_governed_memory_lifecycle"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert "i8_operational_plans" not in tables

    command.upgrade(cfg, "069_i8_operational_plan_state_foundation")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "069_i8_operational_plan_state_foundation"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert {"i8_operational_plans", "i8_operational_plan_actions"} <= tables
        idx = {
            r[0]
            for r in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename='i8_operational_plans'")
            )
        }
        assert "uq_i8_plan_user_local_active" in idx
        plan_constraints = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'i8_operational_plans'::regclass"
                )
            )
        }
        assert "uq_i8_plan_id_user" in plan_constraints
        assert "uq_i8_plan_user_idempotency" in plan_constraints

        user_id = _seed_user(conn)
        conn.commit()
        local = date(2026, 8, 21)
        plan_id = _insert_plan(conn, _plan_row(user_id, local_date=local))
        action_id = _insert_action(conn, plan_id=plan_id, user_id=user_id)
        conn.commit()
        assert plan_id > 0 and action_id > 0

        # duplicate plan idempotency
        with pytest.raises(IntegrityError):
            _insert_plan(conn, _plan_row(user_id, local_date=local, idem="plan-k1"))
            conn.commit()
        conn.rollback()

        # forbidden second ACTIVE same day
        with pytest.raises(IntegrityError):
            _insert_plan(conn, _plan_row(user_id, local_date=local, idem="plan-k2"))
            conn.commit()
        conn.rollback()

        # duplicate action idempotency
        with pytest.raises(IntegrityError):
            _insert_action(conn, plan_id=plan_id, user_id=user_id, idem="act-k1")
            conn.commit()
        conn.rollback()

        # invalid status
        with pytest.raises(IntegrityError):
            _insert_plan(
                conn,
                _plan_row(user_id, local_date=date(2026, 8, 22), idem="plan-bad", status="BOGUS"),
            )
            conn.commit()
        conn.rollback()

        # invalid FK plan
        with pytest.raises(IntegrityError):
            _insert_action(conn, plan_id=999999, user_id=user_id, idem="act-orphan")
            conn.commit()
        conn.rollback()

        # cross-user plan/action mismatch must be rejected (composite FK)
        user_b = _seed_user(conn)
        conn.commit()
        with pytest.raises(IntegrityError):
            _insert_action(conn, plan_id=plan_id, user_id=user_b, idem="act-cross-user")
            conn.commit()
        conn.rollback()

        # summary_text DB bound (512) — PostgreSQL raises DataError on truncation
        long_summary = "x" * 513
        with pytest.raises(DataError):
            conn.execute(
                text(
                    """
                    INSERT INTO i8_operational_plan_actions (
                        plan_id, user_id, action_domain, action_type, status,
                        action_idempotency_key, summary_text, presentation_json,
                        safety_state, clarification_required, knowledge_refs_json,
                        valid_from, valid_until, expires_at
                    ) VALUES (
                        :plan_id, :user_id, 'nutrition', 'meal_suggestion', 'ACTIVE',
                        'act-long', :summary_text, '{}', 'SAFE', false, '[]',
                        now(), now(), now() + interval '36 hours'
                    )
                    """
                ),
                {"plan_id": plan_id, "user_id": user_id, "summary_text": long_summary},
            )
            conn.commit()
        conn.rollback()

        # presentation_json: no DB byte cap (large insert allowed)
        big_json = json.dumps({"payload": "y" * 9000})
        big_id = conn.execute(
            text(
                """
                INSERT INTO i8_operational_plan_actions (
                    plan_id, user_id, action_domain, action_type, status,
                    action_idempotency_key, summary_text, presentation_json,
                    safety_state, clarification_required, knowledge_refs_json,
                    valid_from, valid_until, expires_at
                ) VALUES (
                    :plan_id, :user_id, 'nutrition', 'meal_suggestion', 'ACTIVE',
                    'act-big-json', 'ok', :presentation_json,
                    'SAFE', false, '[]', now(), now(), now() + interval '36 hours'
                ) RETURNING id
                """
            ),
            {"plan_id": plan_id, "user_id": user_id, "presentation_json": big_json},
        ).scalar()
        conn.commit()
        assert big_id is not None

        # cascade: user delete removes plans/actions
        uid2 = _seed_user(conn)
        pid2 = _insert_plan(conn, _plan_row(uid2, local_date=date(2026, 8, 23), idem="p2"))
        _insert_action(conn, plan_id=pid2, user_id=uid2, idem="a2")
        conn.commit()
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid2})
        conn.commit()
        assert conn.execute(
            text("SELECT count(*) FROM i8_operational_plans WHERE user_id = :uid"),
            {"uid": uid2},
        ).scalar() == 0

        # timezone edge: snapshot immutable; SUPERSEDED allows new ACTIVE same day
        uid3 = _seed_user(conn)
        old_tz = "America/New_York"
        p_old = _insert_plan(
            conn,
            _plan_row(uid3, local_date=local, tz=old_tz, idem="tz-old", status="ACTIVE"),
        )
        conn.execute(
            text("UPDATE i8_operational_plans SET status = 'SUPERSEDED' WHERE id = :id"),
            {"id": p_old},
        )
        p_new = _insert_plan(
            conn,
            _plan_row(
                uid3,
                local_date=local,
                tz="Europe/London",
                idem="tz-new",
                status="ACTIVE",
                superseded_by=None,
            ),
        )
        conn.execute(
            text(
                "UPDATE i8_operational_plans SET superseded_by_plan_id = :new_id WHERE id = :old_id"
            ),
            {"new_id": p_new, "old_id": p_old},
        )
        conn.commit()
        snap = conn.execute(
            text(
                "SELECT timezone_snapshot, user_local_date FROM i8_operational_plans WHERE id = :id"
            ),
            {"id": p_old},
        ).one()
        assert snap[0] == old_tz
        assert snap[1] == local

    command.downgrade(cfg, "068_i7_wave2_governed_memory_lifecycle")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "068_i7_wave2_governed_memory_lifecycle"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert "i8_operational_plans" not in tables
        assert "i8_operational_plan_actions" not in tables

    command.upgrade(cfg, "069_i8_operational_plan_state_foundation")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == (
            "069_i8_operational_plan_state_foundation"
        )
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert "i8_operational_plans" in tables
