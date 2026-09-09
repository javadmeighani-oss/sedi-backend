"""Context Resolver — deterministic WHO / ABOUT WHOM / PURPOSE / AUTHORITY / CONTEXT.

Fail-closed for cross-family, revoked, wrong subject, wrong account.
SON_SELF != MOTHER_MANAGED. NO_FAKE_MOTHER_ACCOUNT. NO_*_SUBSTITUTION.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import ConsentDenied, has_permission, PERM_READ
from backend.app.services.i9.device_reported_vital_status import (
    get_effective_device_reported_vital_status,
)
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    require_account_subject_access,
)
from backend.app.services.scis.sedi_retrieval_context import (
    BoundedContextRef,
    DEFAULT_ALLOWED_KNOWLEDGE_CLASSES,
    SediRetrievalContext,
    SubjectMode,
)


class ContextResolutionDenied(PermissionError):
    """Fail-closed context resolution (access / consent / identity)."""


PURPOSE_GOVERNED_RETRIEVAL = "GOVERNED_KNOWLEDGE_RETRIEVAL"
PURPOSE_PERSONAL_CONTEXT_RELEVANCE = "PERSONAL_CONTEXT_RELEVANCE"
PURPOSE_CARE_SUPPORT = "CARE_SUPPORT"

_PERSONAL_PURPOSES = frozenset({PURPOSE_PERSONAL_CONTEXT_RELEVANCE, PURPOSE_CARE_SUPPORT})


def _active_access_row(
    db: Session, *, account_user_id: int, health_subject_id: int
) -> Optional[models.AccountHealthSubjectAccess]:
    return (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == int(account_user_id),
            models.AccountHealthSubjectAccess.health_subject_id == int(health_subject_id),
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )


def resolve_sedi_retrieval_context(
    db: Session,
    *,
    requester_account_id: int,
    target_health_subject_id: int,
    purpose: str = PURPOSE_GOVERNED_RETRIEVAL,
    language: str = "en",
    intent: Optional[str] = None,
    domain: Optional[str] = None,
    safety_classification: Optional[str] = None,
    allowed_knowledge_classes: Sequence[str] = DEFAULT_ALLOWED_KNOWLEDGE_CLASSES,
    include_personal_context: bool = False,
    include_device_status: bool = False,
    governed_action_ref_id: Optional[int] = None,
    trace_id: Optional[str] = None,
) -> SediRetrievalContext:
    """Resolve bounded authorized retrieval context.

    Answers: WHO, ABOUT WHOM, FOR WHAT PURPOSE, WITH WHAT AUTHORITY,
    USING WHICH CONTEXT, FROM WHICH KNOWLEDGE CLASS.
    """
    try:
        subject = require_account_subject_access(
            db, int(requester_account_id), int(target_health_subject_id)
        )
    except HealthSubjectAccessDenied as exc:
        raise ContextResolutionDenied("CROSS_FAMILY_OR_ACCESS_DENIED") from exc

    access = _active_access_row(
        db,
        account_user_id=int(requester_account_id),
        health_subject_id=int(subject.id),
    )
    if access is None:
        raise ContextResolutionDenied("REVOKED_OR_INACTIVE_ACCESS")

    kind = str(subject.subject_kind or "").strip().lower()
    if kind == "self":
        mode = SubjectMode.SELF
        if subject.linked_user_id is None:
            raise ContextResolutionDenied("SELF_SUBJECT_MISSING_LINKED_USER")
        if int(subject.linked_user_id) != int(requester_account_id):
            # Never substitute another account's SELF for the requester.
            raise ContextResolutionDenied("NO_ACCOUNT_OR_HEALTHSUBJECT_SUBSTITUTION")
        relationship = "SELF"
    elif kind == "managed":
        mode = SubjectMode.MANAGED
        if subject.linked_user_id is not None:
            # Managed Mother ALS contract: no fake mother account.
            raise ContextResolutionDenied("NO_FAKE_MOTHER_ACCOUNT")
        relationship = str(access.access_role or "CAREGIVER")
    else:
        raise ContextResolutionDenied(f"UNSUPPORTED_SUBJECT_KIND:{kind}")

    scopes: list[str] = ["ACCOUNT_HEALTH_SUBJECT_ACCESS", f"ROLE:{access.access_role}"]
    personal_ref: Optional[BoundedContextRef] = None
    device_ref: Optional[BoundedContextRef] = None
    action_ref: Optional[BoundedContextRef] = None

    if include_personal_context or purpose in _PERSONAL_PURPOSES:
        # I6 consent: personal/memory relevance requires active read permission
        # on the requester account (actor). Fail closed if revoked/absent.
        if not has_permission(db, int(requester_account_id), PERM_READ):
            raise ContextResolutionDenied("CONSENT_ACCESS_DENIED") from ConsentDenied(
                "CONSENT_DENIED:memory.read"
            )
        scopes.append("I6_MEMORY_READ")
        personal_ref = BoundedContextRef(
            ref_type="personal_context_scope",
            authority="I7",
            ref_id=int(subject.id),
            label="BOUNDED_RELEVANCE_ONLY",
        )
        scopes.append("I7_PERSONAL_RELEVANCE_REF")

    if include_device_status:
        # I9 status context as REF only — never raw measurements / diagnosis.
        status = get_effective_device_reported_vital_status(
            db, health_subject_id=int(subject.id)
        )
        if status is not None:
            device_ref = BoundedContextRef(
                ref_type="device_reported_vital_status",
                authority="I9",
                ref_id=int(status.row_id),
                label=str(status.status),  # STABLE|UNSTABLE label only
            )
            scopes.append("I9_DEVICE_STATUS_REF")

    if governed_action_ref_id is not None:
        # Opaque I8 action plan reference — Smart-RAG never mints actions.
        action_ref = BoundedContextRef(
            ref_type="governed_action",
            authority="I8",
            ref_id=int(governed_action_ref_id),
            label="EXISTING_ACTION_REF_ONLY",
        )
        scopes.append("I8_ACTION_REF")

    scopes.append("I5_GOVERNED_KNOWLEDGE")
    if safety_classification:
        scopes.append("I4_SAFETY_CLASSIFICATION_ROUTE")

    return SediRetrievalContext(
        requester_account_id=int(requester_account_id),
        target_health_subject_id=int(subject.id),
        subject_mode=mode,
        relationship=relationship,
        authorization_scope=tuple(scopes),
        purpose=str(purpose),
        language=str(language or "en"),
        intent=intent,
        domain=domain,
        safety_classification=safety_classification,
        allowed_knowledge_classes=tuple(allowed_knowledge_classes)
        or DEFAULT_ALLOWED_KNOWLEDGE_CLASSES,
        personal_context_ref=personal_ref,
        governed_action_ref=action_ref,
        device_status_ref=device_ref,
        trace_id=trace_id or f"srca-{uuid4().hex[:16]}",
        access_role=str(access.access_role) if access.access_role else None,
        linked_user_id=int(subject.linked_user_id) if subject.linked_user_id is not None else None,
    )


def revoke_account_subject_access(
    db: Session,
    *,
    account_user_id: int,
    health_subject_id: int,
    commit: bool = False,
) -> None:
    """Test/ops helper — mark AHSA revoked (fail-closed thereafter)."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == int(account_user_id),
            models.AccountHealthSubjectAccess.health_subject_id == int(health_subject_id),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.is_active = False
        row.revoked_at = now
    if commit:
        db.commit()
    else:
        db.flush()
