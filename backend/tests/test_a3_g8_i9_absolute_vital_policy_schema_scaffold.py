"""A3 G8 — I9 absolute vital policy schema scaffold (migration + constraints only).

SCHEMA_FOUNDATION_ONLY. No interpreter, I10 producer, numeric seeds, or activation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app import models
from backend.tests.helpers.i10_postgresql_harness import (
    ALEMBIC_HEAD,
    I10IsolatedPgDb,
    _REV_084,
    _REV_085,
    pg_table_exists,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_FORBIDDEN_NUMERIC_TOKENS = (
    "100",
    "60",
    "95",
    "37.5",
    "50",
    "120",
    "38",
    "39.5",
)

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "085_i9_absolute_vital_policy_schema_scaffold.py"
)


def test_g8_static_alembic_single_head_and_ancestry():
    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == [_REV_085]
    assert ALEMBIC_HEAD == _REV_085
    assert script.get_revision(_REV_085).down_revision == _REV_084


def test_g8_static_migration_has_no_seeds_or_forbidden_numerics():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert "INSERT INTO" not in src.upper()
    assert "i9_absolute_vital_policies" in src
    assert "i9_absolute_vital_policy_rules" in src
    assert "i9_absolute_vital_alert_results" in src
    assert "confirmation_windows" not in src
    # Forbid standalone clinical cutoff literals as seed/payload values (not revision ids).
    for token in ("37.5", "39.5"):
        assert token not in src
    # BPM/%/C band literals must not appear as SQL values / defaults.
    assert not re.search(r"(?i)values\s*\([^)]*\b(100|60|95|50|120|38)\b", src)
    assert "server_default='100'" not in src
    assert "server_default=\"100\"" not in src


def test_g8_static_orm_models_importable_without_evaluator():
    assert models.I9AbsoluteVitalPolicy.__tablename__ == "i9_absolute_vital_policies"
    assert models.I9AbsoluteVitalPolicyRule.__tablename__ == "i9_absolute_vital_policy_rules"
    assert models.I9AbsoluteVitalAlertResult.__tablename__ == "i9_absolute_vital_alert_results"
    # No G8 runtime consumer modules.
    import importlib

    for mod in (
        "backend.app.services.i9.absolute_vital_interpreter",
        "backend.app.services.i10.absolute_vital_alert_producer",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod)


def test_g8_static_no_runtime_consumer_of_new_tables():
    root = Path(__file__).resolve().parents[1] / "app"
    hits = []
    for path in root.rglob("*.py"):
        if path.name == "models.py":
            continue
        text_src = path.read_text(encoding="utf-8")
        if "i9_absolute_vital_" in text_src or "I9AbsoluteVital" in text_src:
            hits.append(str(path.relative_to(root.parent)))
    assert hits == [], f"unexpected runtime consumers: {hits}"


def _create_subject(session) -> models.HealthSubject:
    user = models.User(
        name="G8User",
        secret_key="k-g8-scaffold",
        preferred_language="en",
        phone="+989191800001",
    )
    session.add(user)
    session.flush()
    from backend.app.services.i9.health_subject_service import create_managed_subject_without_account

    return create_managed_subject_without_account(
        session,
        account_user_id=user.id,
        display_name="G8 Subject",
        commit=True,
    )


def test_g8_01_migration_upgrade_downgrade_reupgrade():
    isolated = I10IsolatedPgDb.create(suffix="g8mig085", revision=_REV_084)
    try:
        assert isolated.head() == _REV_084
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "i9_absolute_vital_policies")
            assert not pg_table_exists(conn, "i9_absolute_vital_policy_rules")
            assert not pg_table_exists(conn, "i9_absolute_vital_alert_results")

        command.upgrade(isolated.cfg, _REV_085)
        assert isolated.head() == _REV_085
        with isolated.engine.connect() as conn:
            for t in (
                "i9_absolute_vital_policies",
                "i9_absolute_vital_policy_rules",
                "i9_absolute_vital_alert_results",
            ):
                assert pg_table_exists(conn, t)
            assert not pg_table_exists(conn, "confirmation_windows")
            assert conn.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_policies")).scalar_one() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_policy_rules")).scalar_one() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_alert_results")).scalar_one() == 0
            cols = {
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name='i9_absolute_vital_policies'
                        """
                    )
                )
            }
            for required in (
                "policy_key",
                "version",
                "status",
                "evidence_refs_json",
                "governance_approval_ref",
                "source_applicability_json",
                "effective_from",
                "effective_until",
                "created_at",
                "updated_at",
            ):
                assert required in cols

        command.downgrade(isolated.cfg, _REV_084)
        assert isolated.head() == _REV_084
        with isolated.engine.connect() as conn:
            assert not pg_table_exists(conn, "i9_absolute_vital_policies")
            assert not pg_table_exists(conn, "i9_absolute_vital_policy_rules")
            assert not pg_table_exists(conn, "i9_absolute_vital_alert_results")

        command.upgrade(isolated.cfg, _REV_085)
        assert isolated.head() == _REV_085
        with isolated.engine.connect() as conn:
            assert pg_table_exists(conn, "i9_absolute_vital_policies")
    finally:
        isolated.close()


def test_g8_02_constraints_uniqueness_fks_restrict_and_no_numeric_payload():
    isolated = I10IsolatedPgDb.create(suffix="g8fk085", revision=_REV_085)
    Session = isolated.session_factory()
    db = Session()
    try:
        now = datetime.now(timezone.utc)
        p1 = models.I9AbsoluteVitalPolicy(
            policy_key="SEDI-I9-ABSOLUTE-VITAL-ADULT",
            version="DRAFT_SCAFFOLD",
            status="draft",
            effective_from=now,
        )
        db.add(p1)
        db.commit()
        db.refresh(p1)

        # Policy version uniqueness
        db.add(
            models.I9AbsoluteVitalPolicy(
                policy_key="SEDI-I9-ABSOLUTE-VITAL-ADULT",
                version="DRAFT_SCAFFOLD",
                status="draft",
                effective_from=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Rule FK required
        db.add(
            models.I9AbsoluteVitalPolicyRule(
                policy_id=9_999_999,
                metric="heart_rate",
                rule_kind="structural_placeholder",
                context_gates_json='{"quality":true,"repeat":true}',
                rule_payload_json=None,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        rule = models.I9AbsoluteVitalPolicyRule(
            policy_id=p1.id,
            metric="spo2",
            rule_kind="structural_placeholder",
            context_gates_json='{"quality":true,"repeat":true,"symptoms":true}',
            rule_payload_json=None,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        assert rule.rule_payload_json is None

        subject = _create_subject(db)

        # Result missing subject
        db.add(
            models.I9AbsoluteVitalAlertResult(
                health_subject_id=9_999_999,
                policy_id=p1.id,
                metric="temperature",
                observation_at=now,
                governed_outcome="OBSERVE_OR_RECHECK",
                occurrence_key="g8:test:missing-subject",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Result missing policy
        db.add(
            models.I9AbsoluteVitalAlertResult(
                health_subject_id=subject.id,
                policy_id=9_999_999,
                metric="temperature",
                observation_at=now,
                governed_outcome="OBSERVE_OR_RECHECK",
                occurrence_key="g8:test:missing-policy",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        r1 = models.I9AbsoluteVitalAlertResult(
            health_subject_id=subject.id,
            policy_id=p1.id,
            policy_rule_id=rule.id,
            metric="heart_rate",
            observation_at=now,
            quality_context_state="STRUCTURAL_ONLY",
            confirmation_state="NOT_CONFIRMED",
            governed_outcome="OBSERVE_OR_RECHECK",
            occurrence_key="g8:test:occ-1",
        )
        db.add(r1)
        db.commit()

        # Occurrence idempotency
        db.add(
            models.I9AbsoluteVitalAlertResult(
                health_subject_id=subject.id,
                policy_id=p1.id,
                metric="heart_rate",
                observation_at=now,
                governed_outcome="OBSERVE_OR_RECHECK",
                occurrence_key="g8:test:occ-1",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Policy referenced by result cannot be silently deleted (RESTRICT)
        db.delete(p1)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # Cascade: deleting policy after removing results should cascade rules
        db.execute(text("DELETE FROM i9_absolute_vital_alert_results WHERE policy_id = :p"), {"p": p1.id})
        db.commit()
        db.delete(db.get(models.I9AbsoluteVitalPolicy, p1.id))
        db.commit()
        leftover_rules = db.execute(
            text("SELECT COUNT(*) FROM i9_absolute_vital_policy_rules WHERE policy_id = :p"),
            {"p": p1.id},
        ).scalar_one()
        assert leftover_rules == 0

        # No forbidden numeric payloads left in scaffold tables
        for table in (
            "i9_absolute_vital_policies",
            "i9_absolute_vital_policy_rules",
            "i9_absolute_vital_alert_results",
        ):
            assert db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() == 0
    finally:
        db.close()
        isolated.close()


def test_g8_03_related_imports_unaffected():
    from backend.app.services.notifications import inbox_projection, retention
    from backend.app.services import notification_engine
    from backend.app.services.i10 import self_producer_adapter

    assert callable(inbox_projection.fetch_sent_history_page)
    assert callable(retention.prune_expired_notification_content)
    assert hasattr(notification_engine, "DecisionEngine")
    assert hasattr(self_producer_adapter, "enqueue_self_scheduler_notification")


def test_g8_static_forbidden_tokens_not_in_payload_defaults():
    """Ensure structural scaffold does not encode legacy/device clinical cutoffs."""
    src = _MIGRATION.read_text(encoding="utf-8")
    for token in _FORBIDDEN_NUMERIC_TOKENS:
        # Allow digits inside identifiers/lengths (VARCHAR(64)) but not as freestanding clinical values.
        if token in ("37.5", "39.5"):
            assert token not in src
        else:
            assert f" {token} " not in src
            assert f"'{token}'" not in src
            assert f'"{token}"' not in src
