"""Canonical Chat-facing facade for I5 governed care-directory authority.

This module MUST NOT implement a second directory store or query engine.
It only:
  1) detects care-navigation intent (application-side);
  2) dispatches to the existing governed I5 directory service;
  3) maps hits into one Chat contract / explicit NO_VERIFIED fail-safe;
  4) provides server-side authority guards (RAG/Memory/I8/I10 ≠ SoT).

Underlying governed implementation (current V1): iran_directory_service.
Chat MUST NOT import that module directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

# Private governed backend — Chat/orchestrator import THIS facade only.
from backend.app.services.i5 import iran_directory_service as _governed_directory
from backend.app.services.i5.iran_directory_source_manifest import SOURCE_MANIFEST

PACKAGE_ID = "I5-DIRECTORY-CHAT-FAILSAFE-01"
CANONICAL_AUTHORITY = "I5_GOVERNED_CARE_DIRECTORY"
STATUS_VERIFIED = "VERIFIED_DIRECTORY_RESULT"
STATUS_NO_VERIFIED = "NO_VERIFIED_DIRECTORY_RESULT"
PERSONAL_PROVIDER_CONTEXT = "PERSONAL_PROVIDER_CONTEXT"
GOVERNED_DIRECTORY_PROVIDER = "GOVERNED_DIRECTORY_PROVIDER"

GOVERNED_DIRECTORY_DISCLAIMER = _governed_directory.ENDORSEMENT_DISCLAIMER

# Laboratory V1 population is not authorized — never surface labs as verified.
LAB_POPULATION_AUTHORIZED = any(
    bool(meta.get("ALLOWED_FOR_V1_POPULATION"))
    and "LABORATORY" in (meta.get("ENTITY_FAMILIES") or ())
    for meta in SOURCE_MANIFEST.values()
)


class CareNavEntity(str, Enum):
    SPECIALIST = "SPECIALIST"
    HOSPITAL = "HOSPITAL"
    SPECIALTY_CENTER = "SPECIALTY_CENTER"
    LABORATORY = "LABORATORY"


@dataclass(frozen=True)
class CareNavRequest:
    entity: CareNavEntity
    specialty_or_service: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    name_hint: Optional[str] = None
    language: str = "en"
    authenticated_user_id: Optional[int] = None
    target_health_subject_id: Optional[int] = None
    target_subject_kind: Optional[str] = None
    limit: int = 5


@dataclass(frozen=True)
class VerifiedDirectoryIdentity:
    """One structured governed directory hit — fields sourced from backend rows."""

    directory_record_id: int
    entity_type: str
    canonical_name: str
    canonical_directory_key: str
    specialty_or_service: Optional[str]
    city: Optional[str]
    province: Optional[str]
    source_system_label: Optional[str]
    record_state: str
    last_verified_at: Optional[str]
    endorsement_disclaimer: str
    is_clinical_authority: bool = False
    is_knowledge_unit: bool = False
    authority: str = GOVERNED_DIRECTORY_PROVIDER


@dataclass(frozen=True)
class CareNavResult:
    status: str
    entity: CareNavEntity
    identities: tuple[VerifiedDirectoryIdentity, ...] = ()
    reason_code: str = STATUS_NO_VERIFIED
    user_message: str = ""
    package_id: str = PACKAGE_ID
    authority: str = CANONICAL_AUTHORITY
    lab_population_authorized: bool = LAB_POPULATION_AUTHORIZED
    identity_notes: tuple[str, ...] = ()


# --- Intent detection (application-side; not prompt-only) ---

_SPECIALIST_PAT = re.compile(
    r"\b("
    r"doctor|specialist|physician|neurologist|cardiologist|oncologist|"
    r"پزشک|دکتر|متخصص|فوق\s*تخصص|"
    r"طبيب|دكتور|اخصائي|أخصائي"
    r")\b",
    re.I,
)
_HOSPITAL_PAT = re.compile(r"\b(hospital|بیمارستان|مستشفى)\b", re.I)
_CENTER_PAT = re.compile(
    r"\b("
    r"specialty\s*center|medical\s*center|clinic|"
    r"مرکز\s*تخصصی|مرکز\s*درمانی|کلینیک|"
    r"مركز\s*طبي|عيادة"
    r")\b",
    re.I,
)
_LAB_PAT = re.compile(r"\b(laboratory|lab\b|آزمایشگاه|مختبر)\b", re.I)
_CARE_NAV_VERB = re.compile(
    r"\b("
    r"find|recommend|suggest|near|nearby|introduce|list|search|look\s*up|"
    r"پیدا|معرفی|پیشنهاد|نزدیک|جستجو|لیست|"
    r"ابحث|اقترح|قرب|قريب"
    r")\b|"
    r"(یه|یک|any|یک\s*تا)\s+(دکتر|پزشک|doctor)",
    re.I,
)
_LOCATION_CITY = re.compile(
    r"\b(?:in|near|around|at|در|نزدیک|فی)\s+([A-Za-z\u0600-\u06FF]{2,40})\b",
    re.I,
)
_PROVINCE_HINT = re.compile(
    r"\b(province|استان|محافظة)\s*[:=]?\s*([A-Za-z\u0600-\u06FF]{2,40})\b",
    re.I,
)
_SPECIALTY_HINT = re.compile(
    r"\b("
    r"neurology|neurologist|cardiology|cardiologist|oncology|oncologist|"
    r"endocrinology|endocrinologist|pulmonology|pulmonologist|psychiatry|psychiatrist|"
    r"orthopedics|orthopedic|dermatology|dermatologist|"
    r"gastroenterology|gastroenterologist|urology|urologist|nephrology|nephrologist|"
    r"اعصاب|قلب|سرطان|غدد|ریه|روان|ارتوپد|پوست|گوارش|"
    r"مغز\s*و\s*اعصاب"
    r")\b",
    re.I,
)
_SPECIALTY_NORMALIZE = {
    "neurologist": "Neurology",
    "cardiologist": "Cardiology",
    "oncologist": "Oncology",
    "endocrinologist": "Endocrinology",
    "pulmonologist": "Pulmonology",
    "psychiatrist": "Psychiatry",
    "orthopedic": "Orthopedics",
    "dermatologist": "Dermatology",
    "gastroenterologist": "Gastroenterology",
    "urologist": "Urology",
    "nephrologist": "Nephrology",
}
_INJECTION_PAT = re.compile(
    r"(ignore|bypass|بدون\s*درنظر|نادیده).{0,40}(director|verified|directory|ثبت|معتبر)",
    re.I,
)


def is_care_navigation_query(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    entity_hit = bool(
        _SPECIALIST_PAT.search(text)
        or _HOSPITAL_PAT.search(text)
        or _CENTER_PAT.search(text)
        or _LAB_PAT.search(text)
    )
    if not entity_hit:
        return False
    if _CARE_NAV_VERB.search(text) or _INJECTION_PAT.search(text):
        return True
    if _LOCATION_CITY.search(text) or _SPECIALTY_HINT.search(text):
        return True
    if re.search(r"\b(for|برای|برایِ|جهت)\b", text, re.I):
        return True
    if _SPECIALIST_PAT.search(text) and (
        _SPECIALTY_HINT.search(text) or _LOCATION_CITY.search(text)
    ):
        return True
    if _HOSPITAL_PAT.search(text) or _LAB_PAT.search(text) or _CENTER_PAT.search(text):
        return True
    return bool(_SPECIALIST_PAT.search(text) and len(text) < 80)


def detect_care_nav_entity(message: str) -> CareNavEntity:
    text = message or ""
    if _LAB_PAT.search(text):
        return CareNavEntity.LABORATORY
    if _CENTER_PAT.search(text) and not _HOSPITAL_PAT.search(text):
        return CareNavEntity.SPECIALTY_CENTER
    if _HOSPITAL_PAT.search(text):
        return CareNavEntity.HOSPITAL
    return CareNavEntity.SPECIALIST


def parse_care_nav_request(
    message: str,
    *,
    language: str = "en",
    authenticated_user_id: Optional[int] = None,
    target_health_subject_id: Optional[int] = None,
    target_subject_kind: Optional[str] = None,
) -> CareNavRequest:
    text = message or ""
    entity = detect_care_nav_entity(text)
    city = None
    m_city = _LOCATION_CITY.search(text)
    if m_city:
        city = m_city.group(1).strip()
    province = None
    m_prov = _PROVINCE_HINT.search(text)
    if m_prov:
        province = m_prov.group(2).strip()
    specialty = None
    m_spec = _SPECIALTY_HINT.search(text)
    if m_spec:
        raw_spec = m_spec.group(1).strip()
        specialty = _SPECIALTY_NORMALIZE.get(raw_spec.casefold(), raw_spec)
    return CareNavRequest(
        entity=entity,
        specialty_or_service=specialty,
        city=city,
        province=province,
        language=(language or "en")[:8],
        authenticated_user_id=authenticated_user_id,
        target_health_subject_id=target_health_subject_id,
        target_subject_kind=target_subject_kind,
    )


def _no_result_message(entity: CareNavEntity, language: str) -> str:
    lang = (language or "en").lower()
    if lang.startswith("fa"):
        return (
            "در حال حاضر نتیجهٔ تأییدشده‌ای از فهرست معتبر ارائه‌دهندگان/مراکز "
            "برای معیارهای درخواستی شما ندارم. می‌توانید شهر/استان را گسترده‌تر کنید "
            "یا دستهٔ تخصصی دیگری را مشخص کنید. من هویت پزشک یا مرکز را بدون "
            "رکورد تأییدشدهٔ فهرست رسمی اختراع نمی‌کنم."
        )
    if lang.startswith("ar"):
        return (
            "لا توجد نتيجة موثّقة حالياً في الدليل المعتمد لمقدّمي/مرافق الرعاية "
            "وفق معاييرك. يمكنك توسيع المدينة/المحافظة أو اختيار تخصص آخر. "
            "لن أخترع اسم طبيب أو منشأة بدون سجل دليل موثّق."
        )
    return (
        "Sedi currently has no verified matching provider or facility in the "
        "governed directory for your criteria. You can broaden the location or "
        "choose another specialty/service. I will not invent a provider or "
        "facility identity without a verified directory record."
    )


def fail_safe_user_message(entity: CareNavEntity, language: str = "en") -> str:
    """Public fail-safe copy for Chat when directory miss or resolver error."""
    return _no_result_message(entity, language)


def _serialize_hits_message(
    hits: Sequence[VerifiedDirectoryIdentity],
    language: str,
) -> str:
    lang = (language or "en").lower()
    lines: list[str] = []
    if lang.startswith("fa"):
        lines.append("نتایج تأییدشده از فهرست رسمی (اطلاعاتی؛ توصیه/رتبه‌بندی نیست):")
    elif lang.startswith("ar"):
        lines.append("نتائج موثّقة من الدليل الرسمي (معلوماتية؛ ليست توصية/ترتيب):")
    else:
        lines.append(
            "Verified governed-directory listings (informational only; not a ranking or endorsement):"
        )
    for h in hits:
        bit = h.canonical_name
        if h.specialty_or_service:
            bit += f" — {h.specialty_or_service}"
        loc = ", ".join(x for x in (h.city, h.province) if x)
        if loc:
            bit += f" ({loc})"
        if h.source_system_label:
            bit += f" [source: {h.source_system_label}]"
        bit += f" [id:{h.directory_record_id}]"
        lines.append(f"- {bit}")
    lines.append(GOVERNED_DIRECTORY_DISCLAIMER)
    return "\n".join(lines)


def _map_backend_row(item: Mapping[str, Any]) -> VerifiedDirectoryIdentity:
    """Map existing directory service dict → Chat contract (no re-query)."""
    name = item.get("full_name") or item.get("name") or ""
    specialty = item.get("specialty") or item.get("services_text")
    return VerifiedDirectoryIdentity(
        directory_record_id=int(item["id"]),
        entity_type=str(item.get("entity_type") or ""),
        canonical_name=str(name),
        canonical_directory_key=str(item.get("canonical_directory_key") or ""),
        specialty_or_service=str(specialty) if specialty else None,
        city=item.get("city"),
        province=item.get("province"),
        source_system_label=item.get("source_system_label"),
        record_state=str(item.get("record_state") or ""),
        last_verified_at=item.get("last_verified_at"),
        endorsement_disclaimer=str(
            item.get("endorsement_disclaimer") or GOVERNED_DIRECTORY_DISCLAIMER
        ),
        is_clinical_authority=False,
        is_knowledge_unit=False,
        authority=GOVERNED_DIRECTORY_PROVIDER,
    )


def _dispatch_governed_search(
    db: Session, request: CareNavRequest
) -> list[dict[str, Any]]:
    """Single dispatch to existing governed directory service (ACTIVE-filtered there)."""
    entity = request.entity
    try:
        if entity is CareNavEntity.SPECIALIST:
            return _governed_directory.search_doctors(
                db,
                name=request.name_hint,
                city=request.city,
                province=request.province,
                specialty=request.specialty_or_service,
                include_inactive=False,
                limit=request.limit,
            )
        if entity is CareNavEntity.HOSPITAL:
            return _governed_directory.search_hospitals(
                db,
                name=request.name_hint,
                city=request.city,
                province=request.province,
                facility_type="HOSPITAL",
                include_inactive=False,
                limit=request.limit,
            )
        if entity is CareNavEntity.SPECIALTY_CENTER:
            return _governed_directory.search_hospitals(
                db,
                name=request.name_hint,
                city=request.city,
                province=request.province,
                facility_type="MEDICAL_CENTER",
                include_inactive=False,
                limit=request.limit,
            )
        if entity is CareNavEntity.LABORATORY:
            return _governed_directory.search_laboratories(
                db,
                name=request.name_hint,
                city=request.city,
                province=request.province,
                service=request.specialty_or_service,
                include_inactive=False,
                limit=request.limit,
            )
    except _governed_directory.IranDirectoryServiceError:
        return []
    return []


def query_governed_directory(db: Session, request: CareNavRequest) -> CareNavResult:
    """Resolve care-navigation via canonical I5 governed directory only."""
    notes: list[str] = []
    if request.target_subject_kind == "managed":
        notes.append("MANAGED_SUBJECT_CONTEXT_PRESERVED")
    if request.target_health_subject_id is not None:
        notes.append("TARGET_HEALTH_SUBJECT_REF_ONLY")

    entity = request.entity

    if entity is CareNavEntity.LABORATORY and not LAB_POPULATION_AUTHORIZED:
        return CareNavResult(
            status=STATUS_NO_VERIFIED,
            entity=entity,
            reason_code="LAB_POPULATION_NOT_AUTHORIZED",
            user_message=_no_result_message(entity, request.language),
            lab_population_authorized=False,
            identity_notes=tuple(notes + ["LAB_FAIL_SAFE"]),
        )

    hits_raw = _dispatch_governed_search(db, request)
    # Backend already filters ACTIVE when include_inactive=False.
    # Contract assert only: refuse non-ACTIVE if a caller/mock leaks them.
    identities = tuple(
        _map_backend_row(item)
        for item in hits_raw
        if str(item.get("record_state") or "").upper() == "ACTIVE"
    )

    if not identities:
        return CareNavResult(
            status=STATUS_NO_VERIFIED,
            entity=entity,
            reason_code=STATUS_NO_VERIFIED,
            user_message=_no_result_message(entity, request.language),
            identity_notes=tuple(notes),
        )

    return CareNavResult(
        status=STATUS_VERIFIED,
        entity=entity,
        identities=identities,
        reason_code=STATUS_VERIFIED,
        user_message=_serialize_hits_message(identities, request.language),
        identity_notes=tuple(notes),
    )


def resolve_care_navigation(
    db: Session,
    message: str,
    *,
    language: str = "en",
    authenticated_user_id: Optional[int] = None,
    target_health_subject_id: Optional[int] = None,
    target_subject_kind: Optional[str] = None,
) -> Optional[CareNavResult]:
    """If message is care-navigation, return governed result; else None."""
    if not is_care_navigation_query(message):
        return None
    req = parse_care_nav_request(
        message,
        language=language,
        authenticated_user_id=authenticated_user_id,
        target_health_subject_id=target_health_subject_id,
        target_subject_kind=target_subject_kind,
    )
    return query_governed_directory(db, req)


# --- Authority guards (server-side; defense-in-depth beyond primary gate) ---

_NAMED_PROVIDER_CLAIM = re.compile(
    r"\b("
    r"(?:dr\.?|doctor|پزشک|دکتر)\s+[A-ZÀ-ÖØ-Ý\u0600-\u06FF][\w\u0600-\u06FF'.-]{1,40}"
    r"|"
    r"(?:hospital|بیمارستان|مستشفى)\s+[A-ZÀ-ÖØ-Ý\u0600-\u06FF][\w\u0600-\u06FF'.-]{1,40}"
    r"|"
    r"(?:lab(?:oratory)?|آزمایشگاه|مختبر)\s+[A-ZÀ-ÖØ-Ý\u0600-\u06FF][\w\u0600-\u06FF'.-]{1,40}"
    r")\b",
    re.I,
)


def extract_provider_like_mentions(text: str) -> list[str]:
    return [m.group(0).strip() for m in _NAMED_PROVIDER_CLAIM.finditer(text or "")]


def is_name_validated_against_directory(
    name_fragment: str, identities: Sequence[VerifiedDirectoryIdentity]
) -> bool:
    frag = re.sub(
        r"^(dr\.?|doctor|پزشک|دکتر|hospital|بیمارستان|lab|laboratory)\s+",
        "",
        name_fragment,
        flags=re.I,
    ).strip()
    frag_l = frag.casefold()
    if not frag_l:
        return False
    for ident in identities:
        if frag_l in ident.canonical_name.casefold():
            return True
    return False


def assert_no_ungoverned_provider_authority(
    *,
    candidate_text: str,
    verified: Sequence[VerifiedDirectoryIdentity] = (),
    rag_text: str = "",
    memory_text: str = "",
    i8_action_text: str = "",
) -> tuple[bool, str]:
    """Return (allowed, reason_code). Blocks unverified named provider claims."""
    del rag_text, memory_text, i8_action_text  # context only; never grant authority
    mentions = extract_provider_like_mentions(candidate_text)
    if not mentions:
        return True, "NO_PROVIDER_CLAIM"
    for mention in mentions:
        if is_name_validated_against_directory(mention, verified):
            continue
        return False, "UNGOVERNED_PROVIDER_CLAIM_BLOCKED"
    return True, "PROVIDER_CLAIMS_DIRECTORY_VALIDATED"


def refuse_synthetic_provider_after_zero_result(
    *,
    directory_status: str,
    proposed_text: str,
) -> tuple[bool, str]:
    """After NO_VERIFIED result, any named provider claim is forbidden."""
    if directory_status != STATUS_NO_VERIFIED:
        return True, "NOT_APPLICABLE"
    if extract_provider_like_mentions(proposed_text):
        return False, "SYNTHETIC_PROVIDER_AFTER_ZERO_BLOCKED"
    return True, "ZERO_RESULT_SAFE"


def result_to_public_dict(result: CareNavResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "entity": result.entity.value,
        "reason_code": result.reason_code,
        "package_id": result.package_id,
        "authority": result.authority,
        "lab_population_authorized": result.lab_population_authorized,
        "identity_notes": list(result.identity_notes),
        "identities": [
            {
                "directory_record_id": i.directory_record_id,
                "entity_type": i.entity_type,
                "canonical_name": i.canonical_name,
                "canonical_directory_key": i.canonical_directory_key,
                "specialty_or_service": i.specialty_or_service,
                "city": i.city,
                "province": i.province,
                "source_system_label": i.source_system_label,
                "record_state": i.record_state,
                "last_verified_at": i.last_verified_at,
                "endorsement_disclaimer": i.endorsement_disclaimer,
                "authority": i.authority,
                "is_clinical_authority": False,
                "is_knowledge_unit": False,
            }
            for i in result.identities
        ],
        "user_message": result.user_message,
    }
