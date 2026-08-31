"""I10-B01 domain + persistence foundation tests (authored; runtime not executed in B01)."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.database import Base
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.i10.authorization import (
    I10AuthorizationError,
    caregiver_profile_link_without_grant_is_insufficient,
    create_notification_grant,
    phone_match_does_not_authorize,
    validate_recipient_notification_authorization,
)
from backend.app.services.i10.contracts import (
    I10NotificationCandidate,
    assert_no_live_rag_import,
    reject_forbidden_candidate_fields,
)
from backend.app.services.i10.decision_ledger import record_notification_decision
from backend.app.services.i10.intake import enqueue_i10_notification, future_i8_semantic_envelope_to_candidate
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    tables = [
        models.User.__table__,
        models.HealthSubject.__table__,
        models.AccountHealthSubjectAccess.__table__,
        models.UserCaregiver.__table__,
        models.Notification.__table__,
        models.I10NotificationDecision.__table__,
        models.HealthSubjectNotificationGrant.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _candidate(
    *,
    subject_id: int,
    recipient_id: int,
    key: str = "occ-1",
    scope: I10NotificationScope = I10NotificationScope.GENERAL_STATUS,
) -> I10NotificationCandidate:
    return I10NotificationCandidate(
        candidate_key=key,
        health_subject_id=subject_id,
        recipient_user_id=recipient_id,
        notification_scope=scope,
        source_owner="I10_TEST",
        source_type="foundation",
        source_id="1",
        semantic_family=I10SemanticFamily.GENERAL_STATUS,
        privacy_hint=I10PrivacyClass.PRIVATE,
    )


def test_legacy_notification_without_health_subject_id(db):
    owner = _user(db, "legacy-owner")
    notif = models.Notification(
        user_id=owner.id,
        type="morning_brief",
        body="legacy body",
        priority="normal",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    assert notif.health_subject_id is None
    assert notif.i10_policy_decision_id is None


def test_subject_attributed_notification_preserves_subject_not_recipient(db):
    owner = _user(db, "owner")
    caregiver = _user(db, "caregiver-account")
    managed = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Father")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=managed.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    create_notification_grant(
        db,
        health_subject_id=managed.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        authorization_source="MANUAL",
    )
    candidate = _candidate(subject_id=managed.id, recipient_id=caregiver.id)
    payload = NotificationPayload(
        user_id=caregiver.id,
        type="health_alert",
        body="status update",
        dedupe_key=f"i10:test:{managed.id}:{caregiver.id}:1",
    )
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=False)
    assert result.notification_id is not None
    notif = db.query(models.Notification).filter(models.Notification.id == result.notification_id).one()
    assert notif.health_subject_id == managed.id
    assert notif.user_id == caregiver.id
    assert notif.health_subject_id != notif.user_id


def test_caregiver_never_substituted_as_target_subject(db):
    caregiver = _user(db, "caregiver")
    self_subject = ensure_self_subject_for_account(db, caregiver.id)
    managed = create_managed_subject_without_account(db, account_user_id=caregiver.id, display_name="Mother")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=managed.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    create_notification_grant(
        db,
        health_subject_id=managed.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        authorization_source="MANUAL",
    )
    candidate = _candidate(subject_id=managed.id, recipient_id=caregiver.id, key="occ-subst")
    payload = NotificationPayload(
        user_id=caregiver.id,
        type="health_alert",
        body="managed status",
        dedupe_key="i10:test:subst:1",
    )
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=False)
    notif = db.query(models.Notification).order_by(models.Notification.id.desc()).first()
    assert notif.health_subject_id == managed.id
    assert notif.health_subject_id != self_subject.id


def test_multiple_caregiver_grants_same_subject(db):
    owner = _user(db, "owner-multi")
    cg1 = _user(db, "cg1")
    cg2 = _user(db, "cg2")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Patient")
    for cg in (cg1, cg2):
        db.add(
            models.AccountHealthSubjectAccess(
                account_user_id=cg.id,
                health_subject_id=subject.id,
                access_role="CAREGIVER",
                is_active=True,
            )
        )
    db.commit()
    g1 = create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        authorization_source="MANUAL",
    )
    g2 = create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg2.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        authorization_source="MANUAL",
    )
    assert g1.id != g2.id
    assert g1.recipient_user_id != g2.recipient_user_id


def test_duplicate_active_grant_returns_existing(db):
    owner = _user(db, "owner-dup")
    caregiver = _user(db, "cg-dup")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Dup")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=subject.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    first = create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        authorization_source="MANUAL",
    )
    second = create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
        authorization_source="MANUAL",
    )
    assert first.id == second.id


def test_user_caregiver_link_does_not_authorize_without_grant(db):
    owner = _user(db, "owner-profile")
    caregiver = _user(db, "cg-profile")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Linked")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=subject.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    profile = models.UserCaregiver(
        owner_user_id=owner.id,
        name="Caregiver Contact",
        phone="+10000000001",
        is_active=True,
    )
    db.add(profile)
    db.commit()
    with pytest.raises(I10AuthorizationError) as exc:
        caregiver_profile_link_without_grant_is_insufficient(
            db,
            user_caregiver_id=profile.id,
            health_subject_id=subject.id,
            recipient_user_id=caregiver.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    assert exc.value.code == "PROFILE_LINK_WITHOUT_GRANT"


def test_phone_match_alone_cannot_authorize():
    with pytest.raises(I10AuthorizationError) as exc:
        phone_match_does_not_authorize()
    assert exc.value.code == "PHONE_MATCH_NOT_AUTHORIZATION"


def test_recipient_lacking_subject_access_rejected(db):
    owner = _user(db, "owner-noaccess")
    stranger = _user(db, "stranger")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Protected")
    with pytest.raises(I10AuthorizationError) as exc:
        validate_recipient_notification_authorization(
            db,
            health_subject_id=subject.id,
            recipient_user_id=stranger.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    assert exc.value.code == "RECIPIENT_LACKS_SUBJECT_ACCESS"


def test_access_without_notification_grant_rejected(db):
    owner = _user(db, "owner-nogrant")
    caregiver = _user(db, "cg-nogrant")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="NoGrant")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=subject.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    with pytest.raises(I10AuthorizationError) as exc:
        validate_recipient_notification_authorization(
            db,
            health_subject_id=subject.id,
            recipient_user_id=caregiver.id,
            notification_scope=I10NotificationScope.CARE_ACTION,
        )
    assert exc.value.code == "RECIPIENT_LACKS_NOTIFICATION_GRANT"


def test_grant_plus_access_passes_authorization(db):
    owner = _user(db, "owner-ok")
    caregiver = _user(db, "cg-ok")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Granted")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=subject.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
        authorization_source="MANUAL",
    )
    kind = validate_recipient_notification_authorization(
        db,
        health_subject_id=subject.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    assert kind.value == "CAREGIVER"


def test_decision_ledger_records_without_raw_content(db):
    owner = _user(db, "owner-ledger")
    subject = ensure_self_subject_for_account(db, owner.id)
    candidate = _candidate(subject_id=subject.id, recipient_id=owner.id, key="ledger-1")
    row = record_notification_decision(
        db,
        candidate=candidate,
        decision=I10DecisionValue.DEFER,
        reason_code="QUIET_HOURS",
    )
    assert row.decision == "DEFER"
    assert row.reason_code == "QUIET_HOURS"
    assert row.provenance_refs_json is not None
    assert "numeric_value" not in (row.provenance_refs_json or "")
    for value in (I10DecisionValue.SEND, I10DecisionValue.SUPPRESS, I10DecisionValue.EXPIRE):
        record_notification_decision(
            db,
            candidate=_candidate(subject_id=subject.id, recipient_id=owner.id, key=f"ledger-{value.value}"),
            decision=value,
            reason_code=f"TEST_{value.value}",
        )


def test_candidate_rejects_forbidden_fields():
    with pytest.raises(ValueError):
        reject_forbidden_candidate_fields({"raw_packet": "x"})
    with pytest.raises(ValueError):
        reject_forbidden_candidate_fields({"rag_chunk": "x"})


def test_i10_package_has_no_live_rag_imports():
    i10_dir = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    forbidden_tokens = ("rag_provider", "runtime_knowledge_retrieval", "RAGService", "scis.retrieval")
    for path in i10_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "rag_provider" not in alias.name
                    with pytest.raises(ImportError):
                        assert_no_live_rag_import(alias.name)
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for token in forbidden_tokens:
                    assert token not in mod
        for token in forbidden_tokens:
            assert token not in source


def test_i10_has_no_physiological_measurement_dependency():
    from backend.app.services import i10 as i10_pkg

    for mod_name in ("authorization", "contracts", "decision_ledger", "intake", "policy_types"):
        mod = __import__(f"backend.app.services.i10.{mod_name}", fromlist=["*"])
        src = inspect.getsource(mod)
        assert "PhysiologicalMeasurement" not in src


def test_migration_074_metadata_static():
    migration = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "074_i10_notification_domain_foundation.py"
    text = migration.read_text(encoding="utf-8")
    assert 'revision: str = "074_i10_notification_domain_foundation"' in text
    assert 'down_revision: Union[str, None] = "073_i9_subject_native_rollup_baseline"' in text
    assert "DROP TABLE IF EXISTS i10_notification_decisions" in text
    assert "uq_i10_decision_occurrence" in text
    assert "uq_hsng_active_subject_recipient_scope" in text


def test_orm_alignment_notification_i10_columns(db):
    mapper = sa_inspect(models.Notification)
    col_names = {c.key for c in mapper.columns}
    for required in (
        "health_subject_id",
        "semantic_family",
        "recipient_kind",
        "privacy_class",
        "i10_policy_decision_id",
    ):
        assert required in col_names


def test_i8_envelope_forbidden_notification_copy_fields():
    with pytest.raises(ValueError):
        future_i8_semantic_envelope_to_candidate({"notification_body": "x"})


def test_self_notification_does_not_require_grant_row(db):
    owner = _user(db, "self-user")
    subject = ensure_self_subject_for_account(db, owner.id)
    kind = validate_recipient_notification_authorization(
        db,
        health_subject_id=subject.id,
        recipient_user_id=owner.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert kind.value == "SELF"
