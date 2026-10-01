"""Governed durable raw conversation writes for I7 Wave-2."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.gate4.policy_prefs_bridge import (
    get_local_now,
    resolve_validated_user_timezone,
)
from backend.app.services.i6.consent_service import PERM_WRITE, has_permission, _active_consent
from backend.app.services.i7.period_summaries import resolve_week_start
from backend.app.services.i7.retention import RAW_VISIBLE_DAYS

GENERATOR = "i7-wave2-governed-raw-v1"
logger = logging.getLogger(__name__)


@dataclass
class GovernedRawResult:
    durable: bool
    memory: Optional[models.Memory]
    reason: str
    replayed: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_idempotency_key(
    *,
    user_id: int,
    user_message: str,
    sedi_response: str,
    client_key: Optional[str] = None,
) -> str:
    if client_key:
        return f"client:{client_key}"[:128]
    digest = hashlib.sha256(
        f"{user_id}\n{user_message}\n{sedi_response}".encode("utf-8")
    ).hexdigest()
    return f"auto:{digest}"[:128]


def _local_period_identity(
    db: Session, user_id: int, created_at: datetime
) -> tuple[str, int, date]:
    tz_name = resolve_validated_user_timezone(db, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    week_start = resolve_week_start(getattr(user, "preferred_language", None) if user else None)
    local_dt = get_local_now(created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc), tz_name)
    return tz_name, week_start, local_dt.date()


def _load_provenance(row: models.Memory) -> dict[str, Any]:
    try:
        loaded = json.loads(row.provenance_json) if row.provenance_json else {}
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _find_by_draft_idempotency_key(
    db: Session, *, user_id: int, draft_key: str
) -> Optional[models.Memory]:
    """Replay lookup for auto drafts whose key was recomputed on finalize."""
    if not draft_key.startswith("auto:"):
        return None
    rows = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == int(user_id), models.Memory.durable_write.is_(True))
        .order_by(models.Memory.id.desc())
        .limit(50)
        .all()
    )
    for row in rows:
        prov = _load_provenance(row)
        if prov.get("draft_idempotency_key") == draft_key:
            return row
    return None


def mark_durable_raw_ineligible(
    db: Session,
    *,
    user_id: int,
    memory_id: int,
    actor_user_id: Optional[int] = None,
    reason: str = "FINALIZATION_FAILED",
    commit: bool = True,
) -> GovernedRawResult:
    """
    Fail-closed: remove a durable raw row from history eligibility without a second row.
    Chat may continue; stale draft must not remain visible as final history.
    """
    if actor_user_id is not None and int(actor_user_id) != int(user_id):
        return GovernedRawResult(False, None, "AUTH_IDENTITY_MISMATCH")
    row = (
        db.query(models.Memory)
        .filter(models.Memory.id == int(memory_id), models.Memory.user_id == int(user_id))
        .first()
    )
    if row is None:
        return GovernedRawResult(False, None, "NOT_FOUND_OR_NOT_OWNED")

    now = _utcnow()
    row.durable_write = False
    # retain_until in the past → eligible_raw_filter / is_raw_visible fail-closed.
    row.retain_until = now - timedelta(seconds=1)
    prov = _load_provenance(row)
    inelig = prov.get("ineligibility")
    if not isinstance(inelig, list):
        inelig = []
    inelig.append({"at": now.isoformat(), "reason": reason})
    prov["ineligibility"] = inelig[-5:]
    row.provenance_json = json.dumps(prov, sort_keys=True)
    try:
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
    except Exception:
        db.rollback()
        logger.info("i7_raw_mark_ineligible_failed memory_id=%s reason=%s", memory_id, reason)
        return GovernedRawResult(False, None, "INELIGIBLE_MARK_FAILED")
    return GovernedRawResult(False, row, "MARKED_INELIGIBLE")


def try_durable_raw_write(
    db: Session,
    *,
    user_id: int,
    user_message: str,
    sedi_response: str,
    language: str = "en",
    actor_user_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    provenance: Optional[dict[str, Any]] = None,
    commit: bool = True,
) -> GovernedRawResult:
    """
    Durable raw write requires consent + provenance + idempotency + trusted auth identity.
    Without consent: no durable write and no I7 derivation from this turn.
    """
    if actor_user_id is not None and int(actor_user_id) != int(user_id):
        return GovernedRawResult(False, None, "AUTH_IDENTITY_MISMATCH")

    key = build_idempotency_key(
        user_id=user_id,
        user_message=user_message,
        sedi_response=sedi_response,
        client_key=idempotency_key,
    )
    existing = (
        db.query(models.Memory)
        .filter(models.Memory.user_id == user_id, models.Memory.idempotency_key == key)
        .first()
    )
    if existing is not None:
        return GovernedRawResult(True, existing, "IDEMPOTENT_REPLAY", replayed=True)

    # After finalize, auto draft key may live only as provenance.draft_idempotency_key.
    if key.startswith("auto:"):
        finalized_replay = _find_by_draft_idempotency_key(db, user_id=user_id, draft_key=key)
        if finalized_replay is not None:
            return GovernedRawResult(
                True, finalized_replay, "IDEMPOTENT_REPLAY", replayed=True
            )

    if not has_permission(db, user_id, PERM_WRITE):
        return GovernedRawResult(False, None, "NO_CONSENT")

    consent = _active_consent(db, user_id=user_id)
    if consent is None:
        return GovernedRawResult(False, None, "NO_CONSENT")

    now = _utcnow()
    tz_name, week_start, local_day = _local_period_identity(db, user_id, now)
    prov = provenance or {
        "source": "interact.chat",
        "generator": GENERATOR,
        "actor_user_id": user_id,
        "written_at": now.isoformat(),
    }
    row = models.Memory(
        user_id=user_id,
        user_message=user_message,
        sedi_response=sedi_response,
        language=language,
        created_at=now.replace(tzinfo=None),
        retain_until=now + timedelta(days=RAW_VISIBLE_DAYS),
        consent_id=consent.id,
        provenance_json=json.dumps(prov, sort_keys=True),
        idempotency_key=key,
        period_timezone=tz_name,
        period_week_start=week_start,
        local_period_date=local_day,
        durable_write=True,
    )
    db.add(row)
    try:
        db.flush()
        try:
            from backend.app.services.i7.derived_continuity import refresh_bounded_continuity

            refresh_bounded_continuity(db, user_id=user_id, memory=row)
        except Exception:
            pass
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("i7_raw_write_integrity_conflict user_id=%s", user_id)
        # Deterministic replay: another concurrent writer may have won the key.
        raced = (
            db.query(models.Memory)
            .filter(models.Memory.user_id == user_id, models.Memory.idempotency_key == key)
            .first()
        )
        if raced is not None:
            return GovernedRawResult(True, raced, "IDEMPOTENT_REPLAY", replayed=True)
        if key.startswith("auto:"):
            finalized_replay = _find_by_draft_idempotency_key(db, user_id=user_id, draft_key=key)
            if finalized_replay is not None:
                return GovernedRawResult(
                    True, finalized_replay, "IDEMPOTENT_REPLAY", replayed=True
                )
        return GovernedRawResult(False, None, "IDEMPOTENCY_CONFLICT")
    return GovernedRawResult(True, row, "DURABLE_WRITTEN")


def finalize_durable_raw_response(
    db: Session,
    *,
    user_id: int,
    memory_id: int,
    final_response: str,
    actor_user_id: Optional[int] = None,
    commit: bool = True,
) -> GovernedRawResult:
    """
    Ownership-scoped finalization of an existing durable Memory row.

    Sets sedi_response to the exact final orchestrator-visible response.
    Recomputes auto: idempotency keys; preserves client: keys.
    Preserves draft auto key in provenance for deterministic replay.
    No second Memory row. No cross-user mutation.
    On unique-key collision: fail closed (mark ineligible) — never overwrite another row.
    """
    if actor_user_id is not None and int(actor_user_id) != int(user_id):
        return GovernedRawResult(False, None, "AUTH_IDENTITY_MISMATCH")

    row = (
        db.query(models.Memory)
        .filter(models.Memory.id == int(memory_id), models.Memory.user_id == int(user_id))
        .first()
    )
    if row is None:
        return GovernedRawResult(False, None, "NOT_FOUND_OR_NOT_OWNED")
    if not bool(getattr(row, "durable_write", False)):
        return GovernedRawResult(False, row, "NOT_DURABLE")

    # Idempotent re-finalize with identical final text.
    existing_key = str(getattr(row, "idempotency_key", None) or "")
    if (
        row.sedi_response == final_response
        and existing_key.startswith("auto:")
        and existing_key
        == build_idempotency_key(
            user_id=user_id,
            user_message=str(row.user_message or ""),
            sedi_response=final_response,
            client_key=None,
        )
    ):
        return GovernedRawResult(True, row, "FINALIZED", replayed=True)
    if row.sedi_response == final_response and existing_key.startswith("client:"):
        return GovernedRawResult(True, row, "FINALIZED", replayed=True)

    prov = _load_provenance(row)
    final_key = existing_key
    if existing_key.startswith("auto:"):
        final_key = build_idempotency_key(
            user_id=user_id,
            user_message=str(row.user_message or ""),
            sedi_response=final_response,
            client_key=None,
        )
        if final_key != existing_key:
            collision = (
                db.query(models.Memory)
                .filter(
                    models.Memory.user_id == int(user_id),
                    models.Memory.idempotency_key == final_key,
                    models.Memory.id != int(row.id),
                )
                .first()
            )
            if collision is not None:
                # Do not mutate response or overwrite an unrelated historical turn.
                logger.info(
                    "i7_raw_finalize_key_collision user_id=%s memory_id=%s",
                    user_id,
                    memory_id,
                )
                marked = mark_durable_raw_ineligible(
                    db,
                    user_id=user_id,
                    memory_id=memory_id,
                    actor_user_id=actor_user_id,
                    reason="FINALIZE_KEY_COLLISION",
                    commit=commit,
                )
                return GovernedRawResult(False, marked.memory, "FINALIZE_KEY_COLLISION")
        # Preserve draft key once for replay of the original write identity.
        if "draft_idempotency_key" not in prov:
            prov["draft_idempotency_key"] = existing_key

    row.sedi_response = final_response
    if existing_key.startswith("auto:") and final_key != existing_key:
        row.idempotency_key = final_key
    # client:* keys remain unchanged

    finalizations = prov.get("finalizations")
    if not isinstance(finalizations, list):
        finalizations = []
    finalizations.append(
        {
            "at": _utcnow().isoformat(),
            "generator": "i7-wave2-raw-finalize-v1",
            "reason": "orchestrator_final_visible_response",
        }
    )
    prov["finalizations"] = finalizations[-5:]
    row.provenance_json = json.dumps(prov, sort_keys=True)

    try:
        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("i7_raw_finalize_integrity_conflict memory_id=%s", memory_id)
        marked = mark_durable_raw_ineligible(
            db,
            user_id=user_id,
            memory_id=memory_id,
            actor_user_id=actor_user_id,
            reason="FINALIZE_INTEGRITY_CONFLICT",
            commit=True,
        )
        return GovernedRawResult(False, marked.memory, "FINALIZE_INTEGRITY_CONFLICT")
    except Exception:
        db.rollback()
        logger.info("i7_raw_finalize_unexpected_error memory_id=%s", memory_id)
        try:
            mark_durable_raw_ineligible(
                db,
                user_id=user_id,
                memory_id=memory_id,
                actor_user_id=actor_user_id,
                reason="FINALIZE_UNEXPECTED_ERROR",
                commit=True,
            )
        except Exception:
            db.rollback()
        return GovernedRawResult(False, None, "FINALIZE_UNEXPECTED_ERROR")
    return GovernedRawResult(True, row, "FINALIZED")
