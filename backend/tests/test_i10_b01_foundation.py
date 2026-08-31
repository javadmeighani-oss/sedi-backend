"""I10-B01 domain + persistence foundation tests (PostgreSQL runtime via B04 harness)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from backend.app import models
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
    I10_RAG_IMPORT_BLOCKLIST,
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

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]


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
    assert notif.user_id != owner.id


def test_caregiver_never_substituted_as_target_subject(db):
    caregiver = _user(db, "caregiver")
    self_subject = ensure_self_subject_for_account(db, caregiver.id)
    managed = create_managed_subject_without_account(db, account_user_id=caregiver.id, display_name="Mother")
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


def test_different_scopes_same_subject_recipient_allowed(db):
    owner = _user(db, "owner-scopes")
    caregiver = _user(db, "cg-scopes")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="ScopePatient")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=caregiver.id,
            health_subject_id=subject.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    g1 = create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        authorization_source="MANUAL",
    )
    g2 = create_notification_grant(
        db,
        health_subject_id=subject.id,
        recipient_user_id=caregiver.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
        authorization_source="MANUAL",
    )
    assert g1.id != g2.id


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


def test_grant_without_access_rejected(db):
    owner = _user(db, "owner-gonly")
    stranger = _user(db, "stranger-gonly")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="GrantOnly")
    db.add(
        models.HealthSubjectNotificationGrant(
            health_subject_id=subject.id,
            recipient_user_id=stranger.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS.value,
            is_active=True,
            authorization_source="MANUAL",
        )
    )
    db.commit()
    with pytest.raises(I10AuthorizationError) as exc:
        validate_recipient_notification_authorization(
            db,
            health_subject_id=subject.id,
            recipient_user_id=stranger.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    assert exc.value.code == "RECIPIENT_LACKS_SUBJECT_ACCESS"


def test_no_access_no_grant_rejected(db):
    owner = _user(db, "owner-none")
    stranger = _user(db, "stranger-none")
    subject = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="NoAccessNoGrant")
    with pytest.raises(I10AuthorizationError) as exc:
        validate_recipient_notification_authorization(
            db,
            health_subject_id=subject.id,
            recipient_user_id=stranger.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    assert exc.value.code == "RECIPIENT_LACKS_SUBJECT_ACCESS"


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
    forbidden = ("raw_packet", "rag_chunk", "transcript", "packet_body")
    for token in forbidden:
        assert token not in (row.provenance_refs_json or "")


def test_decision_ledger_all_states_persist(db):
    owner = _user(db, "owner-ledger-all")
    subject = ensure_self_subject_for_account(db, owner.id)
    states = (
        I10DecisionValue.SEND,
        I10DecisionValue.DEFER,
        I10DecisionValue.SUPPRESS,
        I10DecisionValue.BUNDLE,
        I10DecisionValue.ESCALATE,
        I10DecisionValue.EXPIRE,
    )
    for state in states:
        row = record_notification_decision(
            db,
            candidate=_candidate(subject_id=subject.id, recipient_id=owner.id, key=f"ledger-{state.value}"),
            decision=state,
            reason_code=f"TEST_{state.value}",
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
        )
        assert row.decision == state.value
        assert row.health_subject_id == subject.id
        assert row.recipient_user_id == owner.id
        assert row.semantic_family == I10SemanticFamily.GENERAL_STATUS.value
        assert row.privacy_class == I10PrivacyClass.HEALTH_SENSITIVE.value
        assert row.notification_id is None


def test_same_occurrence_duplicate_blocked(db):
    owner = _user(db, "owner-occ-dup")
    subject = ensure_self_subject_for_account(db, owner.id)
    key = "daily-care:2026-08-30"
    candidate = _candidate(subject_id=subject.id, recipient_id=owner.id, key=key)
    first = record_notification_decision(
        db,
        candidate=candidate,
        decision=I10DecisionValue.SEND,
        reason_code="FIRST",
    )
    second = record_notification_decision(
        db,
        candidate=candidate,
        decision=I10DecisionValue.DEFER,
        reason_code="SECOND",
    )
    assert first.id == second.id
    assert second.decision == "DEFER"
    count = (
        db.query(models.I10NotificationDecision)
        .filter(
            models.I10NotificationDecision.candidate_key == key,
            models.I10NotificationDecision.recipient_user_id == owner.id,
            models.I10NotificationDecision.health_subject_id == subject.id,
        )
        .count()
    )
    assert count == 1


def test_new_occurrence_allowed_same_semantic_family(db):
    owner = _user(db, "owner-occ-new")
    subject = ensure_self_subject_for_account(db, owner.id)
    first = record_notification_decision(
        db,
        candidate=_candidate(subject_id=subject.id, recipient_id=owner.id, key="daily-care:2026-08-30"),
        decision=I10DecisionValue.SEND,
        reason_code="DAY_ONE",
    )
    second = record_notification_decision(
        db,
        candidate=_candidate(subject_id=subject.id, recipient_id=owner.id, key="daily-care:2026-08-31"),
        decision=I10DecisionValue.SEND,
        reason_code="DAY_TWO",
    )
    assert first.id != second.id


def test_db_constraint_blocks_duplicate_occurrence_insert(db):
    owner = _user(db, "owner-occ-db")
    subject = ensure_self_subject_for_account(db, owner.id)
    key = "daily-care:2026-08-30-db"
    row1 = models.I10NotificationDecision(
        candidate_key=key,
        health_subject_id=subject.id,
        recipient_user_id=owner.id,
        source_owner="I10_TEST",
        source_type="foundation",
        source_id="1",
        semantic_family=I10SemanticFamily.GENERAL_STATUS.value,
        decision="SEND",
        reason_code="ONE",
        privacy_class=I10PrivacyClass.PRIVATE.value,
    )
    db.add(row1)
    db.commit()
    row2 = models.I10NotificationDecision(
        candidate_key=key,
        health_subject_id=subject.id,
        recipient_user_id=owner.id,
        source_owner="I10_TEST",
        source_type="foundation",
        source_id="2",
        semantic_family=I10SemanticFamily.GENERAL_STATUS.value,
        decision="DEFER",
        reason_code="TWO",
        privacy_class=I10PrivacyClass.PRIVATE.value,
    )
    db.add(row2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_candidate_rejects_forbidden_fields():
    with pytest.raises(ValueError):
        reject_forbidden_candidate_fields({"raw_packet": "x"})
    with pytest.raises(ValueError):
        reject_forbidden_candidate_fields({"rag_chunk": "x"})


def test_i10_package_has_no_live_rag_imports():
    i10_dir = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for blocked in I10_RAG_IMPORT_BLOCKLIST:
        with pytest.raises(ImportError):
            assert_no_live_rag_import(blocked)
    for path in i10_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in I10_RAG_IMPORT_BLOCKLIST
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in I10_RAG_IMPORT_BLOCKLIST
                for blocked in I10_RAG_IMPORT_BLOCKLIST:
                    assert not mod.startswith(f"{blocked}.")


def test_i10_has_no_physiological_measurement_dependency():
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
