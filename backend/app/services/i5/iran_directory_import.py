"""Idempotent persistence for governed Iran directory records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .iran_directory_normalization import normalize_records
from .iran_directory_service import refuse_ir_directory_to_knowledge_unit

_MODEL_BY_FAMILY = {
    "DOCTOR": ("IranDoctor", ("full_name", "specialty", "city", "province", "phone", "address", "record_state")),
    "LABORATORY": ("IranLaboratory", ("name", "city", "province", "services_text", "phone", "address", "record_state")),
    "HOSPITAL": ("IranHospital", ("name", "facility_type", "city", "province", "phone", "address", "record_state")),
}
_FORBIDDEN_KU_FIELDS = {"knowledge_unit_id", "canonical_unit_id", "normalized_statement", "evidence_strength"}


def _empty_counts() -> dict[str, dict[str, int]]:
    return {family.lower(): {"insert": 0, "update": 0, "unchanged": 0, "reject": 0}
            for family in _MODEL_BY_FAMILY}


def _family_name(record: dict[str, Any]) -> str:
    return str(record.get("entity_family", "UNKNOWN")).lower()


def _normalized(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    for record in records:
        if _FORBIDDEN_KU_FIELDS.intersection(record):
            refuse_ir_directory_to_knowledge_unit(record=record)
    return normalize_records(records)


def dry_run_plan(records: list[dict[str, Any]], db_session: Session | None = None) -> dict[str, dict[str, int]]:
    """Count a plan without writing. With no session, valid records are inserts."""
    counts = _empty_counts()
    valid, rejected = _normalized(records)
    for rejected_record in rejected:
        family = _family_name(rejected_record["record"])
        if family in counts:
            counts[family]["reject"] += 1
    if db_session is None:
        for record in valid:
            counts[_family_name(record)]["insert"] += 1
        return counts
    from backend.app import models
    for record in valid:
        family = record["entity_family"]
        cls = getattr(models, _MODEL_BY_FAMILY[family][0])
        existing = db_session.query(cls).filter_by(canonical_directory_key=record["canonical_directory_key"]).one_or_none()
        bucket = counts[family.lower()]
        if existing is None:
            bucket["insert"] += 1
        elif existing.source_system_label != record["source_system_label"]:
            bucket["reject"] += 1
        elif any(getattr(existing, key) != record.get(key) for key in _MODEL_BY_FAMILY[family][1]):
            bucket["update"] += 1
        else:
            bucket["unchanged"] += 1
    return counts


def apply_plan(db_session: Session, records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Apply inserts and factual updates only; never deletes or deactivates rows."""
    from .iran_directory_source_manifest import get_authorized_source

    plan = dry_run_plan(records, db_session)
    valid, _ = _normalized(records)
    from backend.app import models
    now = datetime.utcnow()
    for record in valid:
        # Fail closed: only V1-authorized sources may mutate directory tables.
        get_authorized_source(record["source_system_label"])
        family = record["entity_family"]
        cls_name, factual_fields = _MODEL_BY_FAMILY[family]
        cls = getattr(models, cls_name)
        existing = db_session.query(cls).filter_by(canonical_directory_key=record["canonical_directory_key"]).one_or_none()
        if existing is None:
            data = {key: record.get(key) for key in factual_fields}
            data.update(
                canonical_directory_key=record["canonical_directory_key"],
                source_system_label=record["source_system_label"],
                last_observed_at=now,
                last_verified_at=now,
            )
            db_session.add(cls(**data))
        elif existing.source_system_label == record["source_system_label"]:
            changed = any(getattr(existing, key) != record.get(key) for key in factual_fields)
            if changed:
                for key in factual_fields:
                    setattr(existing, key, record.get(key))
                existing.last_observed_at = now
                existing.last_verified_at = now
    db_session.flush()
    return plan
