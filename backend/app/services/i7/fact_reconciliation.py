"""Consent-safe, nondestructive legacy→UMF reconciliation. Not inside Alembic 067."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.db03.memory_fact_merge import _as_json_text, _domain_key_effective
from backend.app.services.i6.consent_service import MEMORY_CONSENT_TYPE, MEMORY_PURPOSE, has_permission, PERM_WRITE

PROVENANCE_PREFIX = "s45_reconcile"


@dataclass
class StackCensus:
    source_table: str
    total_rows: int = 0
    distinct_users: int = 0
    null_invalid_owners: int = 0
    date_range: tuple[Optional[str], Optional[str]] = (None, None)
    duplicate_key_candidates: int = 0
    rows_already_in_umf: int = 0
    rows_requiring_mapping: int = 0
    rows_unmappable: int = 0


@dataclass
class ReconcileResult:
    dry_run: bool
    mapped: int = 0
    skipped_existing: int = 0
    unmappable_no_consent: int = 0
    unmappable_no_owner: int = 0
    conflicts_recorded: int = 0
    source_rows_untouched: int = 0
    details: list[str] = field(default_factory=list)


def _active_memory_consent(db: Session, user_id: int) -> Optional[models.UserConsent]:
    return (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.consent_type == MEMORY_CONSENT_TYPE,
            models.UserConsent.purpose == MEMORY_PURPOSE,
            models.UserConsent.status == "active",
        )
        .first()
    )


def _umf_has_provenance(db: Session, provenance: str) -> bool:
    return (
        db.query(models.UserMemoryFact.id)
        .filter(models.UserMemoryFact.provenance == provenance)
        .first()
        is not None
    )


def census_legacy_stacks(db: Session) -> list[StackCensus]:
    out: list[StackCensus] = []
    specs: list[tuple[str, Any, str, str]] = [
        ("user_facts", models.UserFact, "key", "updated_at"),
        ("kc_user_facts", models.KcUserFact, "fact_type", "created_at"),
        ("user_profile_facts", models.UserProfileFact, "fact_type", "created_at"),
    ]
    for table, model, key_col, ts_col in specs:
        rows = db.query(model).all()
        c = StackCensus(source_table=table, total_rows=len(rows))
        users = set()
        keys: dict[tuple, int] = {}
        stamps: list[datetime] = []
        for row in rows:
            uid = getattr(row, "user_id", None)
            if uid is None:
                c.null_invalid_owners += 1
                continue
            users.add(uid)
            key = getattr(row, key_col)
            keys[(uid, key)] = keys.get((uid, key), 0) + 1
            ts = getattr(row, ts_col, None)
            if ts is not None:
                stamps.append(ts)
            prov = f"{PROVENANCE_PREFIX}:{table}:{row.id}"
            if _umf_has_provenance(db, prov):
                c.rows_already_in_umf += 1
            elif _active_memory_consent(db, uid) is None or not has_permission(db, uid, PERM_WRITE):
                c.rows_unmappable += 1
            else:
                c.rows_requiring_mapping += 1
        c.distinct_users = len(users)
        c.duplicate_key_candidates = sum(1 for n in keys.values() if n > 1)
        if stamps:
            c.date_range = (min(stamps).isoformat(), max(stamps).isoformat())
        out.append(c)
    return out


def _project(source_name: str, row: Any) -> dict[str, Any]:
    if source_name == "user_facts":
        return {
            "domain": "legacy_user_facts",
            "key": row.key,
            "value_json": _as_json_text(row.value_json),
            "confidence": float(row.confidence if row.confidence is not None else 0.7),
            "source": row.source or "manual",
            "valid_from": None,
            "valid_until": None,
            "provenance_class": "SYSTEM_DERIVED",
        }
    if source_name == "kc_user_facts":
        return {
            "domain": "kc",
            "key": row.fact_type,
            "value_json": _as_json_text(row.value_json),
            "confidence": 0.85,
            "source": "manual",
            "valid_from": row.valid_from,
            "valid_until": row.valid_to,
            "provenance_class": "USER_CONFIRMED",
        }
    return {
        "domain": "profile",
        "key": row.fact_type,
        "value_json": _as_json_text(row.value_json),
        "confidence": float(row.confidence if row.confidence is not None else 0.7),
        "source": row.source or "manual",
        "valid_from": row.valid_from,
        "valid_until": row.valid_to,
        "provenance_class": "USER_STATED",
    }


def reconcile_legacy_facts(db: Session, *, dry_run: bool = True, persist: bool = False) -> ReconcileResult:
    """Nondestructive, idempotent, consent-fail-closed. Never deletes source rows."""
    result = ReconcileResult(dry_run=dry_run)
    sources = [
        ("user_facts", db.query(models.UserFact).all()),
        ("kc_user_facts", db.query(models.KcUserFact).all()),
        ("user_profile_facts", db.query(models.UserProfileFact).all()),
    ]
    result.source_rows_untouched = sum(len(rows) for _, rows in sources)
    index: dict[tuple, models.UserMemoryFact] = {}
    for existing in db.query(models.UserMemoryFact).all():
        index[_domain_key_effective(existing.user_id, existing.domain, existing.key, existing.valid_from)] = existing

    for source_name, rows in sources:
        for row in rows:
            uid = getattr(row, "user_id", None)
            if uid is None:
                result.unmappable_no_owner += 1
                result.details.append(f"{source_name}:{getattr(row, 'id', '?')}:NO_OWNER")
                continue
            consent = _active_memory_consent(db, uid)
            if consent is None or not has_permission(db, uid, PERM_WRITE):
                result.unmappable_no_consent += 1
                result.details.append(f"{source_name}:{row.id}:CONSENT_PROVENANCE_UNRESOLVED")
                continue
            provenance = f"{PROVENANCE_PREFIX}:{source_name}:{row.id}"
            if _umf_has_provenance(db, provenance):
                result.skipped_existing += 1
                continue
            proj = _project(source_name, row)
            dk = _domain_key_effective(uid, proj["domain"], proj["key"], proj["valid_from"])
            if dry_run or not persist:
                if dk in index and index[dk].value_json != proj["value_json"]:
                    result.conflicts_recorded += 1
                else:
                    result.mapped += 1
                continue
            if dk in index and index[dk].value_json == proj["value_json"]:
                result.skipped_existing += 1
                continue
            status = "active"
            supersedes = None
            if dk in index and index[dk].value_json != proj["value_json"]:
                result.conflicts_recorded += 1
                existing = index[dk]
                existing.fact_status = "superseded"
                existing.soft_invalidated_at = datetime.now(timezone.utc)
                existing.invalidation_reason = f"superseded_by:{provenance}"
                supersedes = existing.id
            new_fact = models.UserMemoryFact(
                user_id=uid,
                domain=proj["domain"],
                key=proj["key"],
                value_json=proj["value_json"],
                confidence=proj["confidence"],
                source=proj["source"],
                provenance=provenance,
                provenance_class=proj["provenance_class"],
                valid_from=proj["valid_from"],
                valid_until=proj["valid_until"],
                consent_id=consent.id,
                supersedes_fact_id=supersedes,
                fact_status=status,
            )
            db.add(new_fact)
            db.flush()
            index[dk] = new_fact
            result.mapped += 1
    if persist and not dry_run:
        db.commit()
    return result
