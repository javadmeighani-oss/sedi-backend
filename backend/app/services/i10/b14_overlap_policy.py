"""I10-B18 B14 overlap — bounded status digest vs data-gap deconfliction (policy only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.caregiver_data_gap import DATA_GAP_TRIGGER_STATES
from backend.app.services.i10.policy_types import I10SemanticFamily

B14_OVERLAP_REASON_STATUS_REDUNDANT = "B14_STATUS_REDUNDANT_WITH_GAP"
B14_OVERLAP_REASON_KEEP_BOTH = "B14_KEEP_BOTH"
B14_OVERLAP_REASON_NOT_APPLICABLE = "B14_NOT_APPLICABLE"


@dataclass(frozen=True)
class B14OverlapDecision:
    applies: bool
    suppress_status_digest: bool
    reason_code: str
    classification_available: bool


def _metadata_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _episode_key(metadata: Mapping[str, Any]) -> Optional[str]:
    schedule = metadata.get("schedule_label")
    gap_end = metadata.get("gap_episode_end")
    data_status = metadata.get("data_status")
    if not data_status:
        return None
    period = schedule or gap_end
    if not period:
        return None
    return f"{data_status}:{period}"


def _has_gap_intent_or_notification(
    db: Session,
    *,
    health_subject_id: int,
    recipient_user_id: int,
    episode_key: str,
) -> bool:
    intents = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.health_subject_id == health_subject_id,
            models.CaregiverNotificationIntent.recipient_user_id == recipient_user_id,
            models.CaregiverNotificationIntent.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .all()
    )
    for intent in intents:
        meta = _metadata_dict(intent.payload_metadata_json)
        if _episode_keys_equivalent(episode_key, meta):
            return True
    notifications = (
        db.query(models.Notification)
        .filter(
            models.Notification.health_subject_id == health_subject_id,
            models.Notification.user_id == recipient_user_id,
            models.Notification.semantic_family == I10SemanticFamily.CARE_DATA_GAP.value,
        )
        .all()
    )
    for notif in notifications:
        ctx = _metadata_dict(notif.context_json)
        meta = {**ctx}
        if notif.metadata_json:
            meta.update(_metadata_dict(notif.metadata_json))
        if _episode_keys_equivalent(episode_key, meta):
            return True
    return False


def _episode_keys_equivalent(status_episode: str, gap_meta: Mapping[str, Any]) -> bool:
    gap_key = _episode_key(gap_meta)
    if gap_key == status_episode:
        return True
    if not status_episode or ":" not in status_episode:
        return False
    data_status, period = status_episode.split(":", 1)
    gap_ds = str(gap_meta.get("data_status") or "").strip().upper()
    if gap_ds != data_status.upper():
        return False
    for period_key in ("gap_episode_end", "schedule_label"):
        val = gap_meta.get(period_key)
        if val and str(val) == period:
            return True
    return False


def evaluate_b14_overlap(
    db: Session,
    *,
    semantic_family: I10SemanticFamily,
    health_subject_id: int,
    recipient_user_id: int,
    payload_metadata: Mapping[str, Any] | None,
) -> B14OverlapDecision:
    """
    Deterministic B14 overlap for same subject/recipient/window.

    Never merges semantic truth — only suppresses redundant status interruption
    when a matching CARE_DATA_GAP intent or notification is proven for the same
    subject, recipient, and bounded episode.
    """
    if semantic_family == I10SemanticFamily.CARE_SAFETY_ESCALATION:
        return B14OverlapDecision(
            applies=False,
            suppress_status_digest=False,
            reason_code="CARE_SAFETY_NEVER_BUNDLED",
            classification_available=True,
        )

    if semantic_family != I10SemanticFamily.CARE_STATUS_DIGEST:
        return B14OverlapDecision(
            applies=False,
            suppress_status_digest=False,
            reason_code=B14_OVERLAP_REASON_NOT_APPLICABLE,
            classification_available=True,
        )

    metadata = dict(payload_metadata or {})
    data_status = str(metadata.get("data_status") or "").strip().upper()
    if data_status not in DATA_GAP_TRIGGER_STATES:
        return B14OverlapDecision(
            applies=True,
            suppress_status_digest=False,
            reason_code=B14_OVERLAP_REASON_KEEP_BOTH,
            classification_available=True,
        )

    trigger = str(metadata.get("trigger_reason") or "").strip()
    if trigger != "care_status_digest":
        return B14OverlapDecision(
            applies=False,
            suppress_status_digest=False,
            reason_code=B14_OVERLAP_REASON_NOT_APPLICABLE,
            classification_available=False,
        )

    episode = _episode_key(metadata)
    if episode is None:
        return B14OverlapDecision(
            applies=True,
            suppress_status_digest=False,
            reason_code=B14_OVERLAP_REASON_KEEP_BOTH,
            classification_available=False,
        )

    if _has_gap_intent_or_notification(
        db,
        health_subject_id=health_subject_id,
        recipient_user_id=recipient_user_id,
        episode_key=episode,
    ):
        return B14OverlapDecision(
            applies=True,
            suppress_status_digest=True,
            reason_code=B14_OVERLAP_REASON_STATUS_REDUNDANT,
            classification_available=True,
        )

    return B14OverlapDecision(
        applies=True,
        suppress_status_digest=False,
        reason_code=B14_OVERLAP_REASON_KEEP_BOTH,
        classification_available=True,
    )
