"""I5-IMPL-W5-P01 / P10 — Iran directory search service.

Directory discovery only. Iranian sources MUST NOT become clinical KnowledgeUnit
authority. No network, no crawl, no KU writes, no production side effects.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

PACKAGE_ID = "I5-IMPL-W5-P01"
MANAGEMENT_ALIAS = "P10"
PACKAGE_TITLE = "Iran doctors/labs/hospitals directory layer"
SERVICE_NAME = "directory_search"

ENTITY_DOCTOR = "DOCTOR"
ENTITY_LABORATORY = "LABORATORY"
ENTITY_HOSPITAL = "HOSPITAL"
ENTITY_MEDICAL_CENTER = "MEDICAL_CENTER"

ENDORSEMENT_DISCLAIMER = (
    "Directory results are informational listings only. "
    "They do not mean Sedi recommends, ranks, or certifies this provider."
)

NO_IR_TO_KU = True
NO_CLINICAL_AUTHORITY = True
NO_LIVE_IR_SOURCE_FETCH = True
MIGRATION_RUN_EXECUTED = False

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class IranDirectoryServiceError(Exception):
    """Bounded service error for directory operations."""


class ForbiddenClinicalWriteError(IranDirectoryServiceError):
    """Raised when a caller attempts IR-directory → KnowledgeUnit clinical write."""


def refuse_ir_directory_to_knowledge_unit(*_args: Any, **_kwargs: Any) -> None:
    """Hard refuse IR directory → KU / clinical evidence writes."""
    raise ForbiddenClinicalWriteError(
        "IR_DIRECTORY_TO_KNOWLEDGE_UNIT_FORBIDDEN:"
        "Iran directory records cannot become KnowledgeUnit clinical authority"
    )


def assert_not_clinical_authority(payload: dict[str, Any]) -> None:
    """Fail closed if a directory payload masquerades as clinical KU evidence."""
    banned = {
        "knowledge_unit_id",
        "canonical_unit_id",
        "immutable_version_id",
        "normalized_statement",
        "evidence_strength",
        "medical_safety_state",
        "runtime_eligibility",
        "provenance_id",
    }
    leaked = sorted(banned.intersection(payload.keys()))
    if leaked:
        raise IranDirectoryServiceError(f"CLINICAL_AUTHORITY_LEAK:{','.join(leaked)}")


def _clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise IranDirectoryServiceError("LIMIT_INVALID") from exc
    if value < 1:
        raise IranDirectoryServiceError("LIMIT_INVALID")
    return min(value, MAX_LIMIT)


def _ilike_contains(column, value: Optional[str]):
    if value is None or not str(value).strip():
        return None
    return column.ilike(f"%{str(value).strip()}%")


def search_doctors(
    db: Session,
    *,
    name: Optional[str] = None,
    city: Optional[str] = None,
    province: Optional[str] = None,
    specialty: Optional[str] = None,
    include_inactive: bool = False,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    from backend.app.models import IranDoctor

    lim = _clamp_limit(limit)
    q = db.query(IranDoctor)
    if not include_inactive:
        q = q.filter(IranDoctor.record_state == "ACTIVE")
    for clause in (
        _ilike_contains(IranDoctor.full_name, name),
        _ilike_contains(IranDoctor.city, city),
        _ilike_contains(IranDoctor.province, province),
        _ilike_contains(IranDoctor.specialty, specialty),
    ):
        if clause is not None:
            q = q.filter(clause)
    rows = q.order_by(IranDoctor.full_name.asc(), IranDoctor.id.asc()).limit(lim).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "entity_type": ENTITY_DOCTOR,
            "id": int(row.id),
            "canonical_directory_key": row.canonical_directory_key,
            "full_name": row.full_name,
            "specialty": row.specialty,
            "city": row.city,
            "province": row.province,
            "phone": row.phone,
            "address": row.address,
            "record_state": row.record_state,
            "source_system_label": row.source_system_label,
            "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
            "last_observed_at": row.last_observed_at.isoformat() if row.last_observed_at else None,
            "endorsement_disclaimer": ENDORSEMENT_DISCLAIMER,
            "is_clinical_authority": False,
            "is_knowledge_unit": False,
        }
        assert_not_clinical_authority(item)
        out.append(item)
    return out


def search_laboratories(
    db: Session,
    *,
    name: Optional[str] = None,
    city: Optional[str] = None,
    province: Optional[str] = None,
    service: Optional[str] = None,
    include_inactive: bool = False,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    from backend.app.models import IranLaboratory

    lim = _clamp_limit(limit)
    q = db.query(IranLaboratory)
    if not include_inactive:
        q = q.filter(IranLaboratory.record_state == "ACTIVE")
    for clause in (
        _ilike_contains(IranLaboratory.name, name),
        _ilike_contains(IranLaboratory.city, city),
        _ilike_contains(IranLaboratory.province, province),
        _ilike_contains(IranLaboratory.services_text, service),
    ):
        if clause is not None:
            q = q.filter(clause)
    rows = q.order_by(IranLaboratory.name.asc(), IranLaboratory.id.asc()).limit(lim).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "entity_type": ENTITY_LABORATORY,
            "id": int(row.id),
            "canonical_directory_key": row.canonical_directory_key,
            "name": row.name,
            "city": row.city,
            "province": row.province,
            "services_text": row.services_text,
            "phone": row.phone,
            "address": row.address,
            "record_state": row.record_state,
            "source_system_label": row.source_system_label,
            "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
            "last_observed_at": row.last_observed_at.isoformat() if row.last_observed_at else None,
            "endorsement_disclaimer": ENDORSEMENT_DISCLAIMER,
            "is_clinical_authority": False,
            "is_knowledge_unit": False,
        }
        assert_not_clinical_authority(item)
        out.append(item)
    return out


def search_hospitals(
    db: Session,
    *,
    name: Optional[str] = None,
    city: Optional[str] = None,
    province: Optional[str] = None,
    facility_type: Optional[str] = None,
    include_inactive: bool = False,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    from backend.app.models import IranHospital

    lim = _clamp_limit(limit)
    q = db.query(IranHospital)
    if not include_inactive:
        q = q.filter(IranHospital.record_state == "ACTIVE")
    if facility_type and str(facility_type).strip():
        ft = str(facility_type).strip().upper()
        if ft not in {"HOSPITAL", "MEDICAL_CENTER"}:
            raise IranDirectoryServiceError(f"FACILITY_TYPE_INVALID:{ft}")
        q = q.filter(IranHospital.facility_type == ft)
    for clause in (
        _ilike_contains(IranHospital.name, name),
        _ilike_contains(IranHospital.city, city),
        _ilike_contains(IranHospital.province, province),
    ):
        if clause is not None:
            q = q.filter(clause)
    rows = q.order_by(IranHospital.name.asc(), IranHospital.id.asc()).limit(lim).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        et = ENTITY_MEDICAL_CENTER if row.facility_type == "MEDICAL_CENTER" else ENTITY_HOSPITAL
        item = {
            "entity_type": et,
            "id": int(row.id),
            "canonical_directory_key": row.canonical_directory_key,
            "name": row.name,
            "facility_type": row.facility_type,
            "city": row.city,
            "province": row.province,
            "phone": row.phone,
            "address": row.address,
            "record_state": row.record_state,
            "source_system_label": row.source_system_label,
            "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
            "last_observed_at": row.last_observed_at.isoformat() if row.last_observed_at else None,
            "endorsement_disclaimer": ENDORSEMENT_DISCLAIMER,
            "is_clinical_authority": False,
            "is_knowledge_unit": False,
        }
        assert_not_clinical_authority(item)
        out.append(item)
    return out


def directory_package_metadata() -> dict[str, Any]:
    return {
        "package_id": PACKAGE_ID,
        "management_alias": MANAGEMENT_ALIAS,
        "package_title": PACKAGE_TITLE,
        "service": SERVICE_NAME,
        "no_ir_to_ku": NO_IR_TO_KU,
        "no_clinical_authority": NO_CLINICAL_AUTHORITY,
        "no_live_ir_source_fetch": NO_LIVE_IR_SOURCE_FETCH,
        "migration_run_executed": MIGRATION_RUN_EXECUTED,
        "endorsement_disclaimer": ENDORSEMENT_DISCLAIMER,
    }
