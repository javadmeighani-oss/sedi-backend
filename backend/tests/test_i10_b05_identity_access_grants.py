"""I10-B05 care network identity/access/grant foundation tests (PostgreSQL)."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.authorization import phone_match_does_not_authorize
from backend.app.services.i10.care_network_access import (
    CareNetworkAccessError,
    grant_caregiver_subject_access,
    list_subject_caregiver_access,
    revoke_caregiver_subject_access,
)
from backend.app.services.i10.care_network_actor import CareNetworkAuthorizationError
from backend.app.services.i10.care_network_grants import (
    CareNetworkGrantError,
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.care_network_identity import (
    CareNetworkIdentityError,
    associate_caregiver_health_subject,
    link_caregiver_to_account,
    lookup_account_candidate_by_phone,
    unlink_caregiver_account,
)
from backend.app.services.i10.policy_types import I10NotificationScope
from backend.app.services.i10.recipient_eligibility import evaluate_recipient_eligibility
from backend.app.services.i9.health_subject_service import create_managed_subject_without_account
from backend.app.services.user_caregiver_service import create_caregiver, deactivate_caregiver
from backend.app.schemas.gate1 import CaregiverCreateIn

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]


def _user(db, name: str, *, phone: str | None = None) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en", phone=phone)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _profile(db, owner_id: int, name: str, phone: str | None = None) -> dict:
    return create_caregiver(
        db,
        owner_id,
        CaregiverCreateIn(name=name, phone=phone, relationship="relative"),
    )


def _managed(db, owner_id: int, *, role: str = "MANAGER") -> models.HealthSubject:
    return create_managed_subject_without_account(
        db,
        account_user_id=owner_id,
        display_name="Managed Parent",
        access_role=role,
    )


# A. Profile/account link


def test_profile_caregiver_valid_without_linked_account(db):
    owner = _user(db, "owner-a")
    profile = _profile(db, owner.id, "Ali")
    assert profile["linked_account_user_id"] is None
    assert profile["link_status"] == "UNLINKED"


def test_phone_match_alone_does_not_authorize_or_link(db):
    owner = _user(db, "owner-b")
    candidate = _user(db, "candidate-b", phone="+989120000099")
    profile = _profile(db, owner.id, "Sara", phone="+989120000099")
    with pytest.raises(Exception):
        phone_match_does_not_authorize()
    result = lookup_account_candidate_by_phone(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=profile["id"],
    )
    assert result["candidate_found"] is True
    assert result["candidate_account_user_id"] == candidate.id
    assert result["phone_match_authorizes"] is False
    refreshed = db.query(models.UserCaregiver).filter(models.UserCaregiver.id == profile["id"]).one()
    assert refreshed.linked_account_user_id is None


def test_explicit_link_to_existing_account_succeeds(db):
    owner = _user(db, "owner-c")
    recipient = _user(db, "recipient-c", phone="+989120000100")
    profile = _profile(db, owner.id, "Mom")
    row = link_caregiver_to_account(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=profile["id"],
        recipient_account_user_id=recipient.id,
    )
    assert row.linked_account_user_id == recipient.id
    assert row.link_provenance == "EXPLICIT_ACCOUNT_ID"


def test_owner_cannot_link_another_users_profile(db):
    owner_a = _user(db, "owner-d1")
    owner_b = _user(db, "owner-d2")
    recipient = _user(db, "recipient-d")
    profile = _profile(db, owner_a.id, "Relative")
    with pytest.raises(CareNetworkAuthorizationError) as exc:
        link_caregiver_to_account(
            db,
            owner_user_id=owner_b.id,
            user_caregiver_id=profile["id"],
            recipient_account_user_id=recipient.id,
        )
    assert exc.value.code == "USER_CAREGIVER_NOT_FOUND"


def test_conflicting_relink_rejected_without_replace(db):
    owner = _user(db, "owner-e")
    first = _user(db, "first-e")
    second = _user(db, "second-e")
    profile = _profile(db, owner.id, "Brother")
    link_caregiver_to_account(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=profile["id"],
        recipient_account_user_id=first.id,
    )
    with pytest.raises(CareNetworkIdentityError) as exc:
        link_caregiver_to_account(
            db,
            owner_user_id=owner.id,
            user_caregiver_id=profile["id"],
            recipient_account_user_id=second.id,
        )
    assert exc.value.code == "CAREGIVER_ALREADY_LINKED"


# B. HealthSubject access


def test_authorized_actor_can_add_caregiver_access(db):
    owner = _user(db, "owner-f")
    caregiver = _user(db, "cg-f")
    subject = _managed(db, owner.id)
    row = grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=caregiver.id,
    )
    assert row.access_role == "CAREGIVER"
    assert row.is_active is True


def test_unauthorized_actor_cannot_add_access(db):
    owner = _user(db, "owner-g")
    intruder = _user(db, "intruder-g")
    caregiver = _user(db, "cg-g")
    subject = _managed(db, owner.id)
    with pytest.raises(CareNetworkAuthorizationError):
        grant_caregiver_subject_access(
            db,
            actor_user_id=intruder.id,
            health_subject_id=subject.id,
            recipient_account_user_id=caregiver.id,
        )


def test_multiple_caregiver_accounts_access_one_subject(db):
    owner = _user(db, "owner-h")
    cg1 = _user(db, "cg-h1")
    cg2 = _user(db, "cg-h2")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg1.id)
    grant_caregiver_subject_access(db, actor_user_id=owner.id, health_subject_id=subject.id, recipient_account_user_id=cg2.id)
    items = list_subject_caregiver_access(db, actor_user_id=owner.id, health_subject_id=subject.id)
    assert len(items) == 2


def test_duplicate_caregiver_access_idempotent(db):
    owner = _user(db, "owner-i")
    caregiver = _user(db, "cg-i")
    subject = _managed(db, owner.id)
    first = grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=caregiver.id,
    )
    second = grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=caregiver.id,
    )
    assert first.id == second.id


def test_revocation_semantics_work(db):
    owner = _user(db, "owner-j")
    caregiver = _user(db, "cg-j")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=caregiver.id,
    )
    revoked = revoke_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=caregiver.id,
    )
    assert revoked is not None
    assert revoked.is_active is False
    assert revoked.revoked_at is not None
    again = revoke_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=caregiver.id,
    )
    assert again is None


# C. Notification grants


def test_grant_without_subject_access_rejected(db):
    owner = _user(db, "owner-k")
    recipient = _user(db, "cg-k")
    subject = _managed(db, owner.id)
    with pytest.raises(CareNetworkGrantError) as exc:
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=recipient.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    assert exc.value.code == "RECIPIENT_LACKS_SUBJECT_ACCESS"


def test_access_without_grant_ineligible(db):
    owner = _user(db, "owner-l")
    recipient = _user(db, "cg-l")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    result = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert result.eligible is False
    assert result.reason_code == "RECIPIENT_LACKS_NOTIFICATION_GRANT"


def test_access_plus_grant_eligible(db):
    owner = _user(db, "owner-m")
    recipient = _user(db, "cg-m")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    result = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert result.eligible is True


def test_different_scopes_independent(db):
    owner = _user(db, "owner-n")
    recipient = _user(db, "cg-n")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    result = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.SAFETY_ESCALATION,
    )
    assert result.eligible is False


def test_multiple_caregiver_grants_independent(db):
    owner = _user(db, "owner-o")
    cg1 = _user(db, "cg-o1")
    cg2 = _user(db, "cg-o2")
    subject = _managed(db, owner.id)
    for cg in (cg1, cg2):
        grant_caregiver_subject_access(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_account_user_id=cg.id,
        )
        create_subject_notification_grant(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_user_id=cg.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
    r1 = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg1.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    r2 = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=cg2.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    assert r1.eligible and r2.eligible


def test_duplicate_active_grant_idempotent(db):
    owner = _user(db, "owner-p")
    recipient = _user(db, "cg-p")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    first = create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    second = create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.DEVICE_STATUS,
    )
    assert first.id == second.id


def test_revocation_disables_eligibility(db):
    owner = _user(db, "owner-q")
    recipient = _user(db, "cg-q")
    subject = _managed(db, owner.id)
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    result = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.CARE_ACTION,
    )
    assert result.eligible is False


# D. Profile association


def test_user_caregiver_metadata_alone_insufficient(db):
    owner = _user(db, "owner-r")
    recipient = _user(db, "cg-r")
    subject = _managed(db, owner.id)
    profile = _profile(db, owner.id, "Relative")
    associate_caregiver_health_subject(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=profile["id"],
        health_subject_id=subject.id,
    )
    result = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        user_caregiver_id=profile["id"],
    )
    assert result.eligible is False


def test_linked_account_alone_insufficient(db):
    owner = _user(db, "owner-s")
    recipient = _user(db, "cg-s")
    subject = _managed(db, owner.id)
    profile = _profile(db, owner.id, "Relative")
    link_caregiver_to_account(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=profile["id"],
        recipient_account_user_id=recipient.id,
    )
    result = evaluate_recipient_eligibility(
        db,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        user_caregiver_id=profile["id"],
    )
    assert result.eligible is False


def test_deactivating_profile_does_not_delete_subject_authority(db):
    owner = _user(db, "owner-t")
    recipient = _user(db, "cg-t")
    subject = _managed(db, owner.id)
    profile = _profile(db, owner.id, "Relative")
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    deactivate_caregiver(db, owner.id, profile["id"])
    access_count = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == subject.id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
        )
        .count()
    )
    grant_count = (
        db.query(models.HealthSubjectNotificationGrant)
        .filter(
            models.HealthSubjectNotificationGrant.health_subject_id == subject.id,
            models.HealthSubjectNotificationGrant.is_active.is_(True),
        )
        .count()
    )
    assert access_count >= 1
    assert grant_count >= 1


# E. Cross-user isolation


def test_account_a_cannot_manage_account_b_profiles(db):
    owner_a = _user(db, "owner-u1")
    owner_b = _user(db, "owner-u2")
    recipient = _user(db, "recipient-u")
    profile = _profile(db, owner_a.id, "Relative")
    with pytest.raises(CareNetworkAuthorizationError):
        link_caregiver_to_account(
            db,
            owner_user_id=owner_b.id,
            user_caregiver_id=profile["id"],
            recipient_account_user_id=recipient.id,
        )


def test_unrelated_account_cannot_grant_itself_subject_access(db):
    owner = _user(db, "owner-v")
    intruder = _user(db, "intruder-v")
    subject = _managed(db, owner.id)
    with pytest.raises(CareNetworkAuthorizationError):
        grant_caregiver_subject_access(
            db,
            actor_user_id=intruder.id,
            health_subject_id=subject.id,
            recipient_account_user_id=intruder.id,
        )


def test_caregiver_cannot_become_health_subject_by_substitution(db):
    owner = _user(db, "owner-w")
    caregiver = _user(db, "cg-w")
    subject = _managed(db, owner.id)
    subject.linked_user_id = caregiver.id
    db.commit()
    with pytest.raises(CareNetworkAccessError) as exc:
        grant_caregiver_subject_access(
            db,
            actor_user_id=owner.id,
            health_subject_id=subject.id,
            recipient_account_user_id=caregiver.id,
        )
    assert exc.value.code == "CAREGIVER_SUBSTITUTION_BLOCKED"


def test_caregiver_role_cannot_manage_other_caregivers(db):
    owner = _user(db, "owner-x")
    cg_only = _user(db, "cg-only-x")
    new_cg = _user(db, "new-cg-x")
    subject = _managed(db, owner.id, role="CAREGIVER")
    db.add(
        models.AccountHealthSubjectAccess(
            account_user_id=cg_only.id,
            health_subject_id=subject.id,
            access_role="CAREGIVER",
            is_active=True,
        )
    )
    db.commit()
    with pytest.raises(CareNetworkAuthorizationError):
        grant_caregiver_subject_access(
            db,
            actor_user_id=cg_only.id,
            health_subject_id=subject.id,
            recipient_account_user_id=new_cg.id,
        )


# F. Boundaries


def test_b05_services_have_no_raw_i9_measurement_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    forbidden = ("PhysiologicalMeasurement", "longitudinal_read_service")
    for path in root.glob("care_network*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = ast.dump(tree)
        for token in forbidden:
            assert token not in imports, f"{path.name} must not import {token}"


def test_b05_services_have_no_direct_rag_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
    for path in list(root.glob("care_network*.py")) + [root / "recipient_eligibility.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        dumped = ast.dump(tree).lower()
        assert "rag" not in dumped


def test_b05_does_not_create_notifications(db):
    owner = _user(db, "owner-y")
    recipient = _user(db, "cg-y")
    subject = _managed(db, owner.id)
    before = db.query(func.count(models.Notification.id)).scalar()
    grant_caregiver_subject_access(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_account_user_id=recipient.id,
    )
    create_subject_notification_grant(
        db,
        actor_user_id=owner.id,
        health_subject_id=subject.id,
        recipient_user_id=recipient.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
    )
    link_caregiver_to_account(
        db,
        owner_user_id=owner.id,
        user_caregiver_id=_profile(db, owner.id, "Rel")["id"],
        recipient_account_user_id=recipient.id,
    )
    after = db.query(func.count(models.Notification.id)).scalar()
    assert after == before
    with patch("backend.app.services.i10.intake.enqueue_i10_notification") as mock_enqueue:
        evaluate_recipient_eligibility(
            db,
            health_subject_id=subject.id,
            recipient_user_id=recipient.id,
            notification_scope=I10NotificationScope.GENERAL_STATUS,
        )
        mock_enqueue.assert_not_called()
