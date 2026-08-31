"""I10 profile contact → Sedi account resolution (explicit linkage only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.care_network_actor import (
    CareNetworkAuthorizationError,
    require_owner_caregiver,
)
from backend.app.utils.phone_normalization import validate_contact_phone


class CareNetworkIdentityError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_link_status(caregiver: models.UserCaregiver) -> str:
    if caregiver.linked_account_user_id is not None:
        return "LINKED"
    return "UNLINKED"


def lookup_account_candidate_by_phone(
    db: Session,
    *,
    owner_user_id: int,
    user_caregiver_id: int,
    phone: Optional[str] = None,
) -> dict:
    """Phone may locate a candidate account; phone match alone must not finalize linkage."""
    caregiver = require_owner_caregiver(
        db,
        owner_user_id=owner_user_id,
        user_caregiver_id=user_caregiver_id,
    )
    lookup_phone = phone or caregiver.phone
    if not lookup_phone:
        return {
            "user_caregiver_id": caregiver.id,
            "link_status": resolve_link_status(caregiver),
            "candidate_found": False,
            "candidate_account_user_id": None,
            "phone_match_authorizes": False,
        }
    valid, normalized = validate_contact_phone(lookup_phone)
    if not valid:
        raise CareNetworkIdentityError("INVALID_PHONE")
    candidate = db.query(models.User).filter(models.User.phone == normalized).first()
    return {
        "user_caregiver_id": caregiver.id,
        "link_status": "CANDIDATE_FOUND" if candidate is not None else resolve_link_status(caregiver),
        "candidate_found": candidate is not None,
        "candidate_account_user_id": candidate.id if candidate else None,
        "normalized_phone": normalized,
        "phone_match_authorizes": False,
        "linked_account_user_id": caregiver.linked_account_user_id,
    }


def link_caregiver_to_account(
    db: Session,
    *,
    owner_user_id: int,
    user_caregiver_id: int,
    recipient_account_user_id: int,
    link_provenance: str = "EXPLICIT_ACCOUNT_ID",
    replace_existing: bool = False,
    commit: bool = True,
) -> models.UserCaregiver:
    """Explicit authenticated association — no health access or grants created."""
    caregiver = require_owner_caregiver(
        db,
        owner_user_id=owner_user_id,
        user_caregiver_id=user_caregiver_id,
    )
    recipient = db.query(models.User).filter(models.User.id == recipient_account_user_id).first()
    if recipient is None:
        raise CareNetworkIdentityError("RECIPIENT_ACCOUNT_NOT_FOUND")
    if caregiver.linked_account_user_id is not None:
        if caregiver.linked_account_user_id == recipient_account_user_id:
            return caregiver
        if not replace_existing:
            raise CareNetworkIdentityError("CAREGIVER_ALREADY_LINKED")
    now = _utc_now()
    caregiver.linked_account_user_id = recipient_account_user_id
    caregiver.linked_at = now
    caregiver.link_provenance = link_provenance
    caregiver.updated_at = now.replace(tzinfo=None)
    if commit:
        db.commit()
        db.refresh(caregiver)
    else:
        db.flush()
    return caregiver


def confirm_phone_candidate_link(
    db: Session,
    *,
    owner_user_id: int,
    user_caregiver_id: int,
    recipient_account_user_id: int,
    commit: bool = True,
) -> models.UserCaregiver:
    """Explicit confirmation after phone candidate discovery — still not authorization."""
    caregiver = require_owner_caregiver(
        db,
        owner_user_id=owner_user_id,
        user_caregiver_id=user_caregiver_id,
    )
    if not caregiver.phone:
        raise CareNetworkIdentityError("CAREGIVER_PHONE_REQUIRED")
    valid, normalized = validate_contact_phone(caregiver.phone)
    if not valid:
        raise CareNetworkIdentityError("INVALID_PHONE")
    candidate = db.query(models.User).filter(models.User.phone == normalized).first()
    if candidate is None or candidate.id != recipient_account_user_id:
        raise CareNetworkIdentityError("PHONE_CANDIDATE_MISMATCH")
    return link_caregiver_to_account(
        db,
        owner_user_id=owner_user_id,
        user_caregiver_id=user_caregiver_id,
        recipient_account_user_id=recipient_account_user_id,
        link_provenance="PHONE_CANDIDATE_CONFIRMED",
        commit=commit,
    )


def unlink_caregiver_account(
    db: Session,
    *,
    owner_user_id: int,
    user_caregiver_id: int,
    commit: bool = True,
) -> models.UserCaregiver:
    """Revoke profile→account linkage only; does not cascade access/grant revocation."""
    caregiver = require_owner_caregiver(
        db,
        owner_user_id=owner_user_id,
        user_caregiver_id=user_caregiver_id,
    )
    if caregiver.linked_account_user_id is None:
        return caregiver
    now = _utc_now()
    caregiver.linked_account_user_id = None
    caregiver.linked_at = None
    caregiver.link_provenance = "UNLINKED"
    caregiver.updated_at = now.replace(tzinfo=None)
    if commit:
        db.commit()
        db.refresh(caregiver)
    else:
        db.flush()
    return caregiver


def associate_caregiver_health_subject(
    db: Session,
    *,
    owner_user_id: int,
    user_caregiver_id: int,
    health_subject_id: int,
    commit: bool = True,
) -> models.UserCaregiver:
    """Profile→subject association metadata only — not authorization."""
    from backend.app.services.i10.care_network_actor import actor_can_manage_subject_care_network

    caregiver = require_owner_caregiver(
        db,
        owner_user_id=owner_user_id,
        user_caregiver_id=user_caregiver_id,
    )
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is None:
        raise CareNetworkIdentityError("HEALTH_SUBJECT_NOT_FOUND")
    if not actor_can_manage_subject_care_network(
        db,
        actor_user_id=owner_user_id,
        health_subject_id=health_subject_id,
    ):
        raise CareNetworkAuthorizationError("ACTOR_CANNOT_MANAGE_SUBJECT_CARE_NETWORK")
    caregiver.health_subject_id = health_subject_id
    caregiver.updated_at = _utc_now().replace(tzinfo=None)
    if commit:
        db.commit()
        db.refresh(caregiver)
    else:
        db.flush()
    return caregiver
