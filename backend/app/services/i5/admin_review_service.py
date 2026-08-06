"""I5-IMPL-W2-P03 — deterministic admin review operations over W2-P02 queues.

No live crawler / activation. Surfaces SafetyReviewQueueItem, KnowledgeConflict,
and KnowledgeGap for human-in-the-loop review. Reuses W2-P02 transition guards.
Does not extend GovernanceEntityType.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Union

from sqlalchemy.orm import Session

from backend.app.schemas.i5_core import (
    MANAGEMENT_ALIAS,
    PACKAGE_ID,
    PACKAGE_TITLE,
    ConflictListItem,
    KnowledgeGapListItem,
    SafetyReviewListItem,
)
from backend.app.services.i5.conflict_service import assert_allowed_conflict_transition
from backend.app.services.i5.enums import (
    ConflictState,
    KnowledgeGapStatus,
    MedicalSafetyState,
    SafetyReviewQueueStatus,
)
from backend.app.services.i5.medical_safety_gate import assert_allowed_medical_safety_transition

_CLOSED_STATUSES: frozenset[SafetyReviewQueueStatus] = frozenset(
    {
        SafetyReviewQueueStatus.CLOSED_CLEARED,
        SafetyReviewQueueStatus.CLOSED_RESTRICTED,
        SafetyReviewQueueStatus.CLOSED_BLOCKED,
        SafetyReviewQueueStatus.CLOSED_REJECTED,
    }
)

_ALLOWED_QUEUE_TRANSITIONS: frozenset[
    tuple[SafetyReviewQueueStatus, SafetyReviewQueueStatus]
] = frozenset(
    {
        (SafetyReviewQueueStatus.OPEN, SafetyReviewQueueStatus.OPEN),
        (SafetyReviewQueueStatus.OPEN, SafetyReviewQueueStatus.IN_REVIEW),
        (SafetyReviewQueueStatus.IN_REVIEW, SafetyReviewQueueStatus.IN_REVIEW),
        (SafetyReviewQueueStatus.IN_REVIEW, SafetyReviewQueueStatus.CLOSED_CLEARED),
        (SafetyReviewQueueStatus.IN_REVIEW, SafetyReviewQueueStatus.CLOSED_RESTRICTED),
        (SafetyReviewQueueStatus.IN_REVIEW, SafetyReviewQueueStatus.CLOSED_BLOCKED),
        (SafetyReviewQueueStatus.IN_REVIEW, SafetyReviewQueueStatus.CLOSED_REJECTED),
    }
)

_CLOSED_TO_MEDICAL: dict[SafetyReviewQueueStatus, MedicalSafetyState] = {
    SafetyReviewQueueStatus.CLOSED_CLEARED: MedicalSafetyState.CLEARED,
    SafetyReviewQueueStatus.CLOSED_RESTRICTED: MedicalSafetyState.RESTRICTED,
    SafetyReviewQueueStatus.CLOSED_BLOCKED: MedicalSafetyState.BLOCKED,
    SafetyReviewQueueStatus.CLOSED_REJECTED: MedicalSafetyState.BLOCKED,
}

_ALLOWED_GAP_TRIAGE: frozenset[tuple[KnowledgeGapStatus, KnowledgeGapStatus]] = frozenset(
    {
        (KnowledgeGapStatus.OPEN, KnowledgeGapStatus.TRIAGED),
        (KnowledgeGapStatus.TRIAGED, KnowledgeGapStatus.PLANNED),
        (KnowledgeGapStatus.TRIAGED, KnowledgeGapStatus.IN_PROGRESS),
        (KnowledgeGapStatus.PLANNED, KnowledgeGapStatus.IN_PROGRESS),
        (KnowledgeGapStatus.IN_PROGRESS, KnowledgeGapStatus.BLOCKED),
        (KnowledgeGapStatus.IN_PROGRESS, KnowledgeGapStatus.RESOLVED),
        (KnowledgeGapStatus.OPEN, KnowledgeGapStatus.REJECTED),
        (KnowledgeGapStatus.TRIAGED, KnowledgeGapStatus.REJECTED),
        (KnowledgeGapStatus.BLOCKED, KnowledgeGapStatus.IN_PROGRESS),
        (KnowledgeGapStatus.RESOLVED, KnowledgeGapStatus.REOPENED),
        (KnowledgeGapStatus.REOPENED, KnowledgeGapStatus.IN_PROGRESS),
    }
)


class AdminReviewServiceError(ValueError):
    """Fail-closed admin review validation error."""


def package_identity() -> dict[str, str]:
    return {
        "package_id": PACKAGE_ID,
        "management_alias": MANAGEMENT_ALIAS,
        "title": PACKAGE_TITLE,
    }


def _coerce_queue_status(value: Union[str, SafetyReviewQueueStatus]) -> SafetyReviewQueueStatus:
    if isinstance(value, SafetyReviewQueueStatus):
        return value
    try:
        return SafetyReviewQueueStatus(str(value))
    except ValueError as exc:
        raise AdminReviewServiceError(f"QUEUE_STATUS_INVALID:{value}") from exc


def _coerce_gap_status(value: Union[str, KnowledgeGapStatus]) -> KnowledgeGapStatus:
    if isinstance(value, KnowledgeGapStatus):
        return value
    try:
        return KnowledgeGapStatus(str(value))
    except ValueError as exc:
        raise AdminReviewServiceError(f"GAP_STATUS_INVALID:{value}") from exc


def assert_allowed_queue_transition(
    old: Union[str, SafetyReviewQueueStatus],
    new: Union[str, SafetyReviewQueueStatus],
) -> None:
    old_s = _coerce_queue_status(old)
    new_s = _coerce_queue_status(new)
    if (old_s, new_s) not in _ALLOWED_QUEUE_TRANSITIONS:
        raise AdminReviewServiceError(
            f"ILLEGAL_QUEUE_TRANSITION:{old_s.value}->{new_s.value}"
        )


def assert_allowed_gap_triage(
    old: Union[str, KnowledgeGapStatus],
    new: Union[str, KnowledgeGapStatus],
) -> None:
    old_s = _coerce_gap_status(old)
    new_s = _coerce_gap_status(new)
    if (old_s, new_s) not in _ALLOWED_GAP_TRIAGE:
        raise AdminReviewServiceError(
            f"ILLEGAL_GAP_TRIAGE:{old_s.value}->{new_s.value}"
        )


def _to_safety_item(row) -> SafetyReviewListItem:
    return SafetyReviewListItem(
        queue_item_id=row.queue_item_id,
        knowledge_unit_id=int(row.knowledge_unit_id),
        queue_status=str(row.queue_status),
        medical_safety_state=str(row.medical_safety_state),
        high_risk_domain=bool(row.high_risk_domain),
        reason=row.reason,
        decision_id=row.decision_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_conflict_item(row) -> ConflictListItem:
    return ConflictListItem(
        conflict_key=row.conflict_key,
        knowledge_unit_id_a=int(row.knowledge_unit_id_a),
        knowledge_unit_id_b=int(row.knowledge_unit_id_b),
        conflict_state=str(row.conflict_state),
        conflict_summary=row.conflict_summary,
        resolution_note=row.resolution_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_gap_item(row) -> KnowledgeGapListItem:
    return KnowledgeGapListItem(
        id=int(row.id),
        canonical_gap_key=row.canonical_gap_key,
        title=row.title,
        domain=row.domain,
        status=str(row.status),
        priority=str(row.priority),
        severity=str(row.severity),
        urgency=str(row.urgency),
        next_review_at=row.next_review_at,
    )


def list_safety_reviews(
    db: Session,
    *,
    status: Optional[str] = None,
    knowledge_unit_id: Optional[int] = None,
) -> list[SafetyReviewListItem]:
    from backend.app.models import SafetyReviewQueueItem

    q = db.query(SafetyReviewQueueItem)
    if status is not None:
        _coerce_queue_status(status)
        q = q.filter(SafetyReviewQueueItem.queue_status == status)
    if knowledge_unit_id is not None:
        q = q.filter(SafetyReviewQueueItem.knowledge_unit_id == int(knowledge_unit_id))
    rows = q.order_by(SafetyReviewQueueItem.id.asc()).all()
    return [_to_safety_item(row) for row in rows]


def list_conflicts(
    db: Session,
    *,
    conflict_state: Optional[str] = None,
) -> list[ConflictListItem]:
    from backend.app.models import KnowledgeConflict

    q = db.query(KnowledgeConflict)
    if conflict_state is not None:
        try:
            ConflictState(str(conflict_state))
        except ValueError as exc:
            raise AdminReviewServiceError(f"CONFLICT_STATE_INVALID:{conflict_state}") from exc
        q = q.filter(KnowledgeConflict.conflict_state == conflict_state)
    rows = q.order_by(KnowledgeConflict.id.asc()).all()
    return [_to_conflict_item(row) for row in rows]


def list_knowledge_gaps(
    db: Session,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
) -> list[KnowledgeGapListItem]:
    from backend.app.models import KnowledgeGap

    q = db.query(KnowledgeGap)
    if status is not None:
        _coerce_gap_status(status)
        q = q.filter(KnowledgeGap.status == status)
    if priority is not None:
        q = q.filter(KnowledgeGap.priority == priority)
    rows = q.order_by(KnowledgeGap.id.asc()).all()
    return [_to_gap_item(row) for row in rows]


def start_safety_review(
    db: Session,
    *,
    queue_item_id: str,
    actor_reference: str,
) -> SafetyReviewListItem:
    from backend.app.models import SafetyReviewQueueItem

    if not (actor_reference or "").strip():
        raise AdminReviewServiceError("ACTOR_REFERENCE_REQUIRED")
    row = (
        db.query(SafetyReviewQueueItem)
        .filter(SafetyReviewQueueItem.queue_item_id == queue_item_id)
        .one_or_none()
    )
    if row is None:
        raise AdminReviewServiceError(f"QUEUE_ITEM_NOT_FOUND:{queue_item_id}")
    assert_allowed_queue_transition(row.queue_status, SafetyReviewQueueStatus.IN_REVIEW)
    row.queue_status = SafetyReviewQueueStatus.IN_REVIEW.value
    note = f"started_by:{actor_reference.strip()}"
    row.reason = f"{row.reason}|{note}" if row.reason else note
    db.flush()
    return _to_safety_item(row)


def close_safety_review(
    db: Session,
    *,
    queue_item_id: str,
    closed_status: str,
    decision_id: int,
    reason: str,
    actor_reference: str,
) -> SafetyReviewListItem:
    from backend.app.models import I5GovernanceDecision, KnowledgeUnit, SafetyReviewQueueItem

    if not (actor_reference or "").strip():
        raise AdminReviewServiceError("ACTOR_REFERENCE_REQUIRED")
    if not (reason or "").strip():
        raise AdminReviewServiceError("CLOSE_REASON_REQUIRED")
    if decision_id is None:
        raise AdminReviewServiceError("DECISION_ID_REQUIRED")
    target = _coerce_queue_status(closed_status)
    if target not in _CLOSED_STATUSES:
        raise AdminReviewServiceError(f"CLOSE_STATUS_NOT_TERMINAL:{closed_status}")

    row = (
        db.query(SafetyReviewQueueItem)
        .filter(SafetyReviewQueueItem.queue_item_id == queue_item_id)
        .one_or_none()
    )
    if row is None:
        raise AdminReviewServiceError(f"QUEUE_ITEM_NOT_FOUND:{queue_item_id}")
    assert_allowed_queue_transition(row.queue_status, target)

    decision = (
        db.query(I5GovernanceDecision)
        .filter(I5GovernanceDecision.id == int(decision_id))
        .one_or_none()
    )
    if decision is None:
        raise AdminReviewServiceError(f"DECISION_NOT_FOUND:{decision_id}")

    ku = (
        db.query(KnowledgeUnit)
        .filter(KnowledgeUnit.id == int(row.knowledge_unit_id))
        .one_or_none()
    )
    if ku is None:
        raise AdminReviewServiceError(f"KNOWLEDGE_UNIT_NOT_FOUND:{row.knowledge_unit_id}")

    new_medical = _CLOSED_TO_MEDICAL[target]
    assert_allowed_medical_safety_transition(ku.medical_safety_state, new_medical)

    row.queue_status = target.value
    row.decision_id = int(decision_id)
    row.medical_safety_state = new_medical.value
    row.reason = reason.strip()
    ku.medical_safety_state = new_medical.value
    db.flush()
    return _to_safety_item(row)


def resolve_conflict_review(
    db: Session,
    *,
    conflict_key: str,
    resolution_note: str,
    actor_reference: str,
) -> ConflictListItem:
    from backend.app.models import KnowledgeConflict, KnowledgeUnit

    if not (resolution_note or "").strip():
        raise AdminReviewServiceError("RESOLUTION_NOTE_REQUIRED")
    if not (actor_reference or "").strip():
        raise AdminReviewServiceError("ACTOR_REFERENCE_REQUIRED")

    row = (
        db.query(KnowledgeConflict)
        .filter(KnowledgeConflict.conflict_key == conflict_key)
        .one_or_none()
    )
    if row is None:
        raise AdminReviewServiceError(f"CONFLICT_NOT_FOUND:{conflict_key}")

    assert_allowed_conflict_transition(row.conflict_state, ConflictState.RESOLVED)
    # Preserve both sides: do not mutate/delete linked knowledge units.
    left = db.query(KnowledgeUnit).filter(KnowledgeUnit.id == row.knowledge_unit_id_a).one()
    right = db.query(KnowledgeUnit).filter(KnowledgeUnit.id == row.knowledge_unit_id_b).one()
    left_id, right_id = left.id, right.id

    row.conflict_state = ConflictState.RESOLVED.value
    row.resolution_note = (
        f"{resolution_note.strip()} | resolved_by:{actor_reference.strip()}"
    )
    db.flush()

    # Fail-closed: both unit ids must remain present after resolve.
    assert left_id == row.knowledge_unit_id_a and right_id == row.knowledge_unit_id_b
    return _to_conflict_item(row)


def triage_knowledge_gap(
    db: Session,
    *,
    gap_id: int,
    new_status: str,
    reviewer_reference: str,
    reason: Optional[str] = None,
) -> KnowledgeGapListItem:
    from backend.app.models import KnowledgeGap

    if not (reviewer_reference or "").strip():
        raise AdminReviewServiceError("REVIEWER_REFERENCE_REQUIRED")
    row = db.query(KnowledgeGap).filter(KnowledgeGap.id == int(gap_id)).one_or_none()
    if row is None:
        raise AdminReviewServiceError(f"GAP_NOT_FOUND:{gap_id}")
    target = _coerce_gap_status(new_status)
    assert_allowed_gap_triage(row.status, target)
    row.status = target.value
    row.reviewer_reference = reviewer_reference.strip()
    if reason:
        row.next_action = reason.strip()
    db.flush()
    return _to_gap_item(row)


def pending_review_blocks_eligibility(queue_status: Union[str, SafetyReviewQueueStatus]) -> bool:
    """Human-in-the-loop fail-closed: OPEN / IN_REVIEW are not runtime-clearing."""
    status = _coerce_queue_status(queue_status)
    return status in (
        SafetyReviewQueueStatus.OPEN,
        SafetyReviewQueueStatus.IN_REVIEW,
    )


def closed_rejected_or_blocked(queue_status: Union[str, SafetyReviewQueueStatus]) -> bool:
    status = _coerce_queue_status(queue_status)
    return status in (
        SafetyReviewQueueStatus.CLOSED_BLOCKED,
        SafetyReviewQueueStatus.CLOSED_REJECTED,
        SafetyReviewQueueStatus.CLOSED_RESTRICTED,
    )


def allowed_queue_transition_pairs() -> Sequence[tuple[str, str]]:
    return tuple(sorted((a.value, b.value) for a, b in _ALLOWED_QUEUE_TRANSITIONS))


def closed_status_literals() -> Iterable[str]:
    return tuple(sorted(s.value for s in _CLOSED_STATUSES))
