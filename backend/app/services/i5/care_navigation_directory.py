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
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

# Private governed backend — Chat/orchestrator import THIS facade only.
from backend.app.services.i5 import iran_directory_service as _governed_directory
from backend.app.services.i5.iran_directory_source_manifest import SOURCE_MANIFEST
from backend.app.services.i5 import directory_web_lookup as _web_lookup
from backend.app.services.i5 import iran_places as _places
from backend.app.services.i5 import specialty_lexicon as _spec

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
    PHARMACY = "PHARMACY"  # J3-a: found ONLINE only (no governed pharmacy list exists, R-093)


@dataclass(frozen=True)
class CareNavRequest:
    entity: CareNavEntity
    specialty_or_service: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    name_hint: Optional[str] = None
    area: Optional[str] = None  # neighbourhood / district (R-089), e.g. «تهران‌پارس»
    language: str = "en"
    authenticated_user_id: Optional[int] = None
    target_health_subject_id: Optional[int] = None
    target_subject_kind: Optional[str] = None
    limit: int = 5
    wants_sources: bool = False
    qualifiers: tuple = ()  # J3-a: («24h», «high_rating») read from the user's words; used in the online search and ranking


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
    phone: Optional[str] = None
    address: Optional[str] = None
    rating_avg: Optional[float] = None
    rating_count: Optional[int] = None
    satisfaction_percent: Optional[int] = None
    source_url: Optional[str] = None  # set only for transient web-search results
    web_trusted: Optional[bool] = None
    # J3-b (D-407): facts confirmed against the result's own page
    phone_status: Optional[str] = None  # verified | unchecked (page unreadable) | None
    visit_days: tuple = ()
    next_turn: Optional[str] = None
    checked_on: Optional[str] = None
    why: tuple = ()


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
    r"doctor|specialist|physician|neurologist|cardiologist|oncologist|dentist|"
    r"پزشک|دکتر|متخصص|فوق\s*تخصص|دندان\s*پزشک|دندانپزشک|دندان‌پزشک|"
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
_PHARMACY_PAT = re.compile(r"\b(pharmacy|pharmacies|داروخانه|دارو\s*خانه|صيدلية|صيدليه|صيدلية)\b|داروخانه", re.I)
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
    r"dentist|dental|دندان\s*پزشک|دندانپزشک|دندان‌پزشک|اعصاب|قلب|سرطان|غدد|ریه|روان|ارتوپد|پوست|گوارش|دندان|"
    r"مغز\s*و\s*اعصاب"
    r")\b",
    re.I,
)
_SPECIALTY_NORMALIZE = {
    "dentist": "دندان",
    "dental": "دندان",
    "دندانپزشک": "دندان",
    "دندان‌پزشک": "دندان",
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


# R-014 (2026-10-24): the directory answers only an explicit "find me a doctor / place" request. A message that merely
# contains «متخصص/دکتر/پزشک» (e.g. «راهکارهای تو چیه؟ متخصص صدی باشه», «به دکتر نمی‌خوام برم») is a normal chat turn.
_NOT_A_FIND_REQUEST = re.compile(
    r"(?:"
    r"(?:متخصص|مشاور|دکتر|پزشک|کارشناس)\s*(?:من|ما|خودم|خودمون)?\s*(?:،|,)?\s*(?:صدی|تو|خودت)\s*(?:باش|باشه|باشی|بشو|هستی|می[‌ ]?شی|میشی)"
    r"|(?:صدی|خودت|تو)\s*(?:متخصص|مشاور|دکتر|پزشک)\s*(?:من\s*)?(?:باش|باشه|باشی|هستی|بشو)"
    r"|(?:نمی[‌ ]?خوام|نمیخوام|نیازی\s*ندارم|لازم\s*نیست|نرم|نمی[‌ ]?رم)\s*(?:که\s*)?(?:به\s*|پیش\s*)?(?:دکتر|پزشک|متخصص)"
    r"|(?:به\s*)?(?:دکتر|پزشک|متخصص)\s*(?:ارجاع|رجوع|مراجعه)\s*(?:نده|ندی|نکن|نکنی)"
    r"|(?:ارجاع|رجوع|مراجعه)\s*(?:نده|ندی|نکن)"
    r"|\b(?:be\s+my|you\s+be\s+my|you\s+are\s+my)\s+(?:doctor|specialist|advisor|physician)"
    r"|\b(?:don'?t|do\s+not|stop)\b.{0,30}\b(?:refer|send|tell)\b.{0,30}\b(?:doctor|specialist|physician)"
    r")",
    re.I,
)
_STRONG_FIND_VERB = re.compile(
    r"\b("
    r"find|near|nearby|introduce|list|search|look\s*up|"
    r"پیدا|معرفی|نزدیک|جستجو|لیست|"
    r"ابحث|قرب|قريب"
    r")\b",
    re.I,
)
_WANT_VERB = re.compile(
    r"\b(need|want|looking\s+for|seeking|أحتاج|أريد|ابحث)\b|می[‌ ]?خوام|میخوام|می[‌ ]?خواهم|نیاز\s*دارم|لازم\s*دارم",
    re.I,
)
_REFUSAL = re.compile(r"\b(?:don'?t|do\s+not|no\s+longer|never)\s+(?:need|want)\b|لا\s+أحتاج|لا\s+أريد", re.I)
_WEAK_FIND_VERB = re.compile(r"\b(recommend|suggest|پیشنهاد|اقترح)\b", re.I)
_ASK_FOR_A_DOCTOR = re.compile(r"(?:یه|یک|any|a|an)\s+(?:دکتر|پزشک|doctor|specialist|dentist)", re.I)
_NOT_A_CITY = frozenset(
    {
        "مورد", "این", "آن", "اون", "همین", "همون", "حال", "واقع", "کل", "کنار", "مقابل", "برابر", "طول", "کجا",
        "من", "ما", "تو", "شما", "صدی", "خانه", "خونه", "منزل", "دست", "پی", "جریان", "اختیار", "کار",
        "منطقه", "محله", "حوالی", "اطراف", "شهر", "سمت", "نزدیکی",
        "the", "my", "this", "that", "a", "an", "your", "case", "general", "mind",
    }
)


def _has_real_location(text: str) -> bool:
    place = _places.find_place(text)
    if place.city or place.area:
        return True
    for m in _LOCATION_CITY.finditer(text):
        if m.group(1).strip().lower() not in _NOT_A_CITY:
            return True
    return False


def _declined_provider(text: str) -> bool:
    """«I don't need a therapist» declines a PROVIDER lookup; «I don't want surgery, find a cardiologist» declines a treatment and
    must still route (Codex P2, PR 189): the refusal counts only when what follows it, up to the next clause, names a provider."""
    for m in _REFUSAL.finditer(text):
        tail = re.split(r"[,;.،؛]|\b(?:but|and|so|then)\b", text[m.end():])[0]
        if _SPECIALIST_PAT.search(tail) or _HOSPITAL_PAT.search(tail) or _CENTER_PAT.search(tail) or _LAB_PAT.search(tail) \
                or _PHARMACY_PAT.search(tail) or _spec.has_practitioner_word(tail):
            return True
    return False


def _practitioner_request(text: str) -> bool:
    """A practitioner named by a specialty word counts only inside a REQUEST to find one («My psychiatrist changed my meds» is not)."""
    return _spec.has_practitioner_word(text) and bool(
        _WANT_VERB.search(text) or _STRONG_FIND_VERB.search(text) or _CARE_NAV_VERB.search(text) or _has_real_location(text)
    )


def is_care_navigation_query(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _NOT_A_FIND_REQUEST.search(text) or _declined_provider(text):
        return False
    entity_hit = bool(
        _SPECIALIST_PAT.search(text)
        or _PHARMACY_PAT.search(text)
        or _practitioner_request(text)
        or _HOSPITAL_PAT.search(text)
        or _CENTER_PAT.search(text)
        or _LAB_PAT.search(text)
    )
    if not entity_hit:
        return False
    if _INJECTION_PAT.search(text) or _STRONG_FIND_VERB.search(text):
        return True
    if _pharmacy_is_requested(text) and (_has_real_location(text) or _CARE_NAV_VERB.search(text)):
        return True
    if _ASK_FOR_A_DOCTOR.search(text):
        return True
    located = _has_real_location(text)
    if located:
        return True
    if _WEAK_FIND_VERB.search(text) or _CARE_NAV_VERB.search(text):
        # "suggest/پیشنهاد" alone is ordinary chat; it is a directory request only with a named specialty.
        return bool(_SPECIALTY_HINT.search(text) or _spec.find_specialty(text))
    if (_HOSPITAL_PAT.search(text) or _LAB_PAT.search(text) or _CENTER_PAT.search(text)) and len(text) < 60:
        return True
    return bool(
        (_SPECIALIST_PAT.search(text) or _practitioner_request(text))
        and (_SPECIALTY_HINT.search(text) or _spec.find_specialty(text))
        and len(text) < 40
    )


_LANDMARK_PREP = re.compile(
    r"(?:\bnear|next\s+to|beside|opposite|behind|close\s+to|around|by|in\s+front\s+of|نزدیک|کنار|روبروی|روبرو|مقابل|پشت|حوالی|اطراف|قرب|بجانب|بجوار|جنب)"
    r"\s+(?:the\s+|a\s+|an\s+|یه\s+|یک\s+)?$",
    re.I,
)


def _is_landmark(text: str, start: int) -> bool:
    """The word at ``start`` is only a place reference («near the pharmacy») when a landmark preposition directly precedes it."""
    return bool(_LANDMARK_PREP.search(text[max(0, start - 24):start]))


def _pharmacy_is_requested(text: str) -> bool:
    """Pharmacy is the requested entity when it is mentioned as a head noun (not a landmark) and no other provider word comes
    first as a head noun: «find a cardiologist near the pharmacy» asks for a cardiologist (Codex P2, PR 189)."""
    heads = [m.start() for m in _PHARMACY_PAT.finditer(text) if not _is_landmark(text, m.start())]
    if not heads:
        return False
    first = heads[0]
    for pat in (_SPECIALIST_PAT, _HOSPITAL_PAT, _CENTER_PAT, _LAB_PAT):
        for m in pat.finditer(text):
            if m.start() < first and not _is_landmark(text, m.start()):
                return False
    return True


def detect_care_nav_entity(message: str) -> CareNavEntity:
    text = message or ""
    if _pharmacy_is_requested(text):
        return CareNavEntity.PHARMACY
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
    place = _places.find_place(text)
    city, area = place.city, place.area
    if not city or place.city_inferred:
        # an explicitly named city (even one outside the gazetteer) beats the Tehran guess from a neighbourhood
        area_norm = _places.normalize(area or "")
        for m_city in _LOCATION_CITY.finditer(text):
            word = m_city.group(1).strip()
            if word.lower() in _NOT_A_CITY or (area_norm and _places.normalize(word) in area_norm) or _places.find_place(word).area:
                continue
            city = word
            break
    province = None
    m_prov = _PROVINCE_HINT.search(text)
    if m_prov:
        province = m_prov.group(2).strip()
    specialty = _spec.find_specialty(text) if entity in (CareNavEntity.SPECIALIST, CareNavEntity.SPECIALTY_CENTER) else None
    m_spec = _SPECIALTY_HINT.search(text) if specialty is None and entity is not CareNavEntity.PHARMACY else None
    if m_spec:
        raw_spec = re.sub(r"\s+", "", m_spec.group(1).strip()) if "دندان" in m_spec.group(1) else m_spec.group(1).strip()
        specialty = _SPECIALTY_NORMALIZE.get(raw_spec.casefold(), raw_spec)
    return CareNavRequest(
        entity=entity,
        specialty_or_service=specialty,
        city=city,
        province=province,
        area=area,
        language=(language or "en")[:8],
        wants_sources=wants_sources(text),
        authenticated_user_id=authenticated_user_id,
        target_health_subject_id=target_health_subject_id,
        target_subject_kind=target_subject_kind,
        qualifiers=_spec.qualifiers(text),
    )


def _no_result_message(entity: CareNavEntity, language: str) -> str:
    """Generic fallback (no request context, e.g. resolver error): never «I cannot help» (R-089)."""
    from backend.app import sedi_copy

    return sedi_copy.t("care_nav.no_result.generic", _lk((language or "en").lower()))


_ENTITY_WORD = {
    CareNavEntity.SPECIALIST: {"fa": "پزشک", "ar": "طبيب", "en": "doctor"},
    CareNavEntity.HOSPITAL: {"fa": "بیمارستان", "ar": "مستشفى", "en": "hospital"},
    CareNavEntity.SPECIALTY_CENTER: {"fa": "کلینیک", "ar": "عيادة", "en": "clinic"},
    CareNavEntity.LABORATORY: {"fa": "آزمایشگاه", "ar": "مختبر", "en": "laboratory"},
    CareNavEntity.PHARMACY: {"fa": "داروخانه", "ar": "صيدلية", "en": "pharmacy"},
}
_SITE_LABEL = {"p24": {"fa": "پذیرش۲۴", "ar": "Paziresh24", "en": "Paziresh24"},
               "doctoreto": {"fa": "دکترتو", "ar": "Doctoreto", "en": "Doctoreto"}}


def directory_search_links(request: "CareNavRequest") -> list[tuple[str, str]]:
    """Direct search pages on Iranian booking/listing sites (patterns verified 2026-11-17). Never invented names."""
    from urllib.parse import quote

    k = _lk((request.language or "en").lower())
    if request.entity is CareNavEntity.PHARMACY:  # booking sites do not list pharmacies: a plain map search
        q = " ".join(x for x in ("داروخانه", "شبانه‌روزی" if "24h" in request.qualifiers else "", request.area, request.city) if x)
        return [({"fa": "نقشه", "ar": "الخريطة", "en": "Map"}[k], f"https://www.google.com/maps/search/?api=1&query={quote(q)}")]
    term_fa = request.specialty_or_service or _ENTITY_WORD.get(request.entity, _ENTITY_WORD[CareNavEntity.SPECIALIST])["fa"]
    slug = _places.slug_for(request.city)
    p24 = f"https://www.paziresh24.com/s/{slug + '/' if slug else ''}?text={quote(term_fa)}"
    where = " ".join(x for x in (request.area, request.city) if x)
    dto = f"https://doctoreto.com/search?q={quote((term_fa + ' ' + where).strip())}"
    return [(_SITE_LABEL["p24"][k], p24), (_SITE_LABEL["doctoreto"][k], dto)]


def no_result_message_for(request: "CareNavRequest") -> str:
    """R-089: no city -> ONE question for the place; nothing found -> direct search links + ONE refining question."""
    from backend.app import sedi_copy

    k = _lk((request.language or "en").lower())
    if not request.city and not request.area:
        return sedi_copy.t("care_nav.ask_location", k)
    what = request.specialty_or_service or _ENTITY_WORD.get(request.entity, _ENTITY_WORD[CareNavEntity.SPECIALIST])[k]
    where = ("، " if k != "en" else ", ").join(x for x in (request.area, request.city) if x)
    links = "\n".join(f"• {label}: {url}" for label, url in directory_search_links(request))
    return sedi_copy.t("care_nav.no_result.links", k, what=what, where=where, links=links)


def fail_safe_user_message(entity: CareNavEntity, language: str = "en") -> str:
    """Public fail-safe copy for Chat when directory miss or resolver error."""
    return _no_result_message(entity, language)


_SOURCE_NAMES = {
    "paziresh24_public_directory": {"fa": "پذیرش۲۴", "ar": "Paziresh24", "en": "Paziresh24"},
    "irimc_member_search": {"fa": "نظام پزشکی", "ar": "نقابة الأطباء الإيرانية", "en": "the Iranian Medical Council"},
    "fed_sbmu_affiliated_hospitals": {
        "fa": "سایت دانشگاه علوم پزشکی شهید بهشتی",
        "ar": "موقع جامعة شهيد بهشتي للعلوم الطبية",
        "en": "the Shahid Beheshti University of Medical Sciences site",
    },
}
_SOURCE_Q = re.compile(
    r"(منبع|رفرنس|مرجع|از\s*کجا|reference|source|مصدر|المصدر)",
    re.I,
)
_SOURCE_Q_TOPIC = re.compile(
    r"(پزشک|دکتر|بیمارستان|کلینیک|آزمایشگاه|اطلاعات|نتایج|لیست|پذیرش\s*۲۴|پذیرش24|"
    r"doctor|hospital|clinic|lab|listing|طبيب|مستشفى)|(منبعش|رفرنسش|مرجعش)",
    re.I,
)
_RATING_Q = re.compile(
    r"(رضایت|نظر\s*(?:بیماران|کاربران|مراجعین)|امتیاز|satisfaction|reviews?|ratings?|رضا\s*المرضى|تقييم)",
    re.I,
)


def _lk(lang: str) -> str:
    return "fa" if lang.startswith("fa") else "ar" if lang.startswith("ar") else "en"


def wants_sources(message: str) -> bool:
    text = message or ""
    return bool(_SOURCE_Q.search(text) or _RATING_Q.search(text))


def is_directory_source_question(message: str) -> bool:
    """Follow-up such as «منبعش چیه؟» or «رضایت بیماران چقدره؟». Needs topic words to avoid hijacking chat."""
    text = message or ""
    if _RATING_Q.search(text):
        return bool(
            _SPECIALIST_PAT.search(text)
            or _HOSPITAL_PAT.search(text)
            or _CENTER_PAT.search(text)
            or _LAB_PAT.search(text)
            or re.search(r"(پذیرش|بیمار|مراجع|patients?)", text, re.I)
        )
    return bool(_SOURCE_Q.search(text) and _SOURCE_Q_TOPIC.search(text))


def source_info_message(language: str) -> str:
    k = _lk((language or "en").lower())
    if k == "fa":
        return (
            "این اطلاعات رو از منابع معتبر پیدا می‌کنم؛ مثل سایت نظام پزشکی، سایت دانشگاه‌ها و بیمارستان‌ها و "
            "سامانه‌هایی مثل پذیرش۲۴، و وقتی لازم باشه همون لحظه در وب جست‌وجو می‌کنم. امتیاز یا درصد رضایتِ بیماران هم دقیقاً همونیه که خودِ "
            "پذیرش۲۴ نشون می‌ده و برای همه‌ی پزشک‌ها وجود نداره. اگه اسم پزشک یا تخصص و شهر رو بگی، "
            "برات می‌گم نظر بیمارها دربارش چیه. این‌ها فقط اطلاعاتن، نه توصیه یا رتبه‌بندی."
        )
    if k == "ar":
        return (
            "جمعتُ هذه المعلومات من قوائم عامة مثل Paziresh24 ونقابة الأطباء ومواقع الجامعات الطبية، وأحدّثها باستمرار. "
            "أما التقييم أو نسبة رضا المرضى فهي كما يعرضها Paziresh24 نفسه وليست متاحة للجميع. "
            "أخبرني باسم الطبيب أو التخصص والمدينة وسأذكر لك رأي المرضى. هذه معلومات فقط وليست توصية."
        )
    return (
        "I gathered this from public listings such as Paziresh24, the Medical Council site and university "
        "hospital pages, and I keep them updated. Patient ratings or satisfaction are exactly what Paziresh24 "
        "shows and aren't available for every doctor. Tell me a doctor, specialty and city and I'll share what "
        "patients say. This is information only, not a recommendation or ranking."
    )


def _feedback_phrase(h: "VerifiedDirectoryIdentity", lang: str) -> str:
    k = _lk(lang)
    domain = _web_lookup.source_domain(h.canonical_directory_key)
    if domain:
        return {"fa": f"؛ منبع: {domain}", "ar": f"؛ المصدر: {domain}", "en": f"; source: {domain}"}[k]
    src = _SOURCE_NAMES.get(h.source_system_label or "", {}).get(k)
    has_rating = bool(h.rating_count and h.rating_avg is not None)
    if not src or not (has_rating or h.satisfaction_percent is not None):
        return ""
    bits = []
    if h.satisfaction_percent is not None:
        bits.append(
            {"fa": f"{str(h.satisfaction_percent).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))}٪ رضایت", "ar": f"رضا {h.satisfaction_percent}٪",
             "en": f"{h.satisfaction_percent}% satisfaction"}[k]
        )
    if has_rating:
        avg = f"{h.rating_avg:.1f}"
        fa_digits = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")
        bits.append(
            {"fa": f"میانگین {avg.translate(fa_digits)} از ۵ بر پایه {str(h.rating_count).translate(fa_digits)} نظر",
             "ar": f"متوسط {avg} من 5 من {h.rating_count} رأي",
             "en": f"average {avg}/5 from {h.rating_count} reviews"}[k]
        )
    joined = ("، " if k != "en" else ", ").join(bits)
    return {"fa": f"؛ بیمارها در {src}: {joined}", "ar": f"؛ المرضى في {src}: {joined}",
            "en": f"; patients on {src}: {joined}"}[k]


def _serialize_hits_message(
    hits: Sequence[VerifiedDirectoryIdentity],
    language: str,
    with_sources: bool = False,
) -> str:
    """Sedi-voice reply: no ids, no links, no source tags unless the user asked."""
    from backend.app import sedi_copy

    lang = (language or "en").lower()
    k = _lk(lang)
    lines = [{
        "fa": "چند مورد از اطلاعاتی که دارم رو برات پیدا کردم:",
        "ar": "هذه بعض النتائج من المعلومات التي لديّ:",
        "en": "Here are a few options from the information I have:",
    }[k]]
    for h in hits:
        head = h.canonical_name + (f" — {h.specialty_or_service}" if h.specialty_or_service else "")
        loc = ("، " if k != "en" else ", ").join(x for x in (h.city, h.province) if x)
        line = "• " + head + (f"، {loc}" if loc else "")
        if h.address:
            line += {"fa": f"؛ آدرس: {h.address}", "ar": f"؛ العنوان: {h.address}", "en": f"; address: {h.address}"}[k]
        sep = "؛ " if k != "en" else "; "
        if h.phone and h.phone_status == "unchecked":
            line += sep + sedi_copy.t("care_nav.hit.phone_unverified", k, phone=h.phone)
        elif h.phone:
            line += {"fa": f"؛ تلفن: {h.phone}", "ar": f"؛ الهاتف: {h.phone}", "en": f"; phone: {h.phone}"}[k]
        if h.visit_days:
            line += sep + sedi_copy.t("care_nav.hit.days", k, days=("، " if k != "en" else ", ").join(h.visit_days))
        if h.next_turn:
            line += sep + sedi_copy.t("care_nav.hit.next_turn", k, when=h.next_turn)
        if h.source_url and h.rating_avg:  # web rows: the page's own rating (governed rows use the feedback phrase below)
            line += sep + sedi_copy.t("care_nav.hit.rating", k, avg=f"{float(h.rating_avg):g}", count=h.rating_count or 0)
        if with_sources:
            line += _feedback_phrase(h, lang)
        # Source link, page-check date and «why this one» only when the user ASKED for the source (Javad, 2026-11-19: no clutter otherwise).
        if h.source_url and with_sources:
            line += {"fa": f"؛ منبع: {h.source_url}", "ar": f"؛ المصدر: {h.source_url}", "en": f"; source: {h.source_url}"}[k]
            if h.checked_on:
                line += sep + sedi_copy.t("care_nav.hit.checked", k, date=h.checked_on)
        if h.why and with_sources:
            reasons = ("، " if k != "en" else ", ").join(sedi_copy.t(f"care_nav.why.{w}", k) for w in h.why if sedi_copy.has(f"care_nav.why.{w}"))
            if reasons:
                line += "\n   " + sedi_copy.t("care_nav.hit.why", k, reasons=reasons)
        lines.append(line)
    if any(h.source_url and not h.web_trusted for h in hits):
        lines.append({
            "fa": "بعضی از این موارد را از جست‌وجوی وب پیدا کردم و تأیید نشده‌اند؛ قبل از مراجعه حتماً تماس بگیر و مطمئن شو.",
            "ar": "وجدتُ بعض هذه النتائج عبر البحث في الويب وهي غير مؤكدة؛ يرجى الاتصال والتأكد قبل الذهاب.",
            "en": "I found some of these through a web search and they are not verified; please call to confirm before going.",
        }[k])
    lines.append({
        "fa": "این‌ها فقط اطلاعاتن، نه توصیه یا رتبه‌بندی؛ قبل از رفتن بهتره با خود مرکز هماهنگ کنی. "
              "بپرس تا بگم این اطلاعات از کجاست و بیمارها چه نظری دارن.",
        "ar": "هذه معلومات فقط وليست توصية أو ترتيباً؛ يُفضّل الاتصال بالمركز قبل الذهاب. "
              "إن أردت أخبرتك بمصدر المعلومات ورأي المرضى.",
        "en": "This is information only, not a recommendation or ranking; please confirm with the provider "
              "before going. Ask me and I'll tell you where it comes from and what patients say.",
    }[k])
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
        phone=item.get("phone"),
        address=item.get("address"),
        rating_avg=item.get("rating_avg"),
        rating_count=item.get("rating_count"),
        satisfaction_percent=item.get("satisfaction_percent"),
    )


def _dispatch_governed_search(
    db: Session, request: CareNavRequest
) -> list[dict[str, Any]]:
    """Single dispatch to existing governed directory service (ACTIVE-filtered there)."""
    entity = request.entity
    try:
        if entity is CareNavEntity.SPECIALIST:
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for term in (_spec.governed_terms(request.specialty_or_service) or (request.specialty_or_service,)):
                for item in _governed_directory.search_doctors(
                    db,
                    name=request.name_hint,
                    city=request.city,
                    province=request.province,
                    specialty=term,
                    include_inactive=False,
                    limit=request.limit,
                ):
                    key = str(item.get("canonical_directory_key") or item.get("id") or item)
                    if key not in seen:
                        seen.add(key)
                        merged.append(item)
                if len(merged) >= request.limit:
                    break
            return merged[: request.limit]
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


def _web_identities(request: "CareNavRequest") -> tuple[VerifiedDirectoryIdentity, ...]:
    """Transient web-search results as identities (never stored; labelled by link and trust)."""
    results = _web_lookup.search_web_providers(
        entity=request.entity.value,
        specialty=request.specialty_or_service,
        city=request.city,
        province=request.province,
        area=request.area,
        qualifiers=request.qualifiers,
    )
    kind = "DOCTOR" if request.entity is CareNavEntity.SPECIALIST else (
        "LABORATORY" if request.entity is CareNavEntity.LABORATORY else (
            "PHARMACY" if request.entity is CareNavEntity.PHARMACY else "HOSPITAL"
        )
    )
    return tuple(
        VerifiedDirectoryIdentity(
            directory_record_id=0,
            entity_type=kind,
            canonical_name=r["name"],
            canonical_directory_key=_web_lookup.web_record_key(r["source_url"]),
            specialty_or_service=r.get("specialty"),
            city=r.get("city"),
            province=request.province,
            source_system_label=_web_lookup.WEB_LOOKUP_SOURCE,
            record_state="ACTIVE",
            last_verified_at=None,
            endorsement_disclaimer=GOVERNED_DIRECTORY_DISCLAIMER,
            phone=r.get("phone"),
            address=r.get("address"),
            source_url=r["source_url"],
            web_trusted=bool(r.get("trusted")),
            rating_avg=r.get("rating_avg"),
            rating_count=r.get("rating_count"),
            phone_status=r.get("phone_status"),
            visit_days=tuple(r.get("visit_days") or ()),
            next_turn=r.get("next_turn"),
            checked_on=r.get("checked_on"),
            why=tuple(r.get("why") or ()),
        )
        for r in results
    )


def query_governed_directory(db: Session, request: CareNavRequest) -> CareNavResult:
    """Resolve care-navigation via canonical I5 governed directory only."""
    notes: list[str] = []
    if request.target_subject_kind == "managed":
        notes.append("MANAGED_SUBJECT_CONTEXT_PRESERVED")
    if request.target_health_subject_id is not None:
        notes.append("TARGET_HEALTH_SUBJECT_REF_ONLY")

    entity = request.entity

    if (entity is CareNavEntity.LABORATORY and not LAB_POPULATION_AUTHORIZED) or entity is CareNavEntity.PHARMACY:
        web_labs = _web_identities(request) if _web_lookup.web_lookup_enabled() else ()
        if web_labs:
            return CareNavResult(
                status=STATUS_VERIFIED,
                entity=entity,
                identities=web_labs,
                reason_code="WEB_SEARCH_RESULTS",
                user_message=_serialize_hits_message(web_labs, request.language, request.wants_sources),
                lab_population_authorized=False,
                identity_notes=tuple(notes + ["WEB_SEARCH_ONLY"]),
            )
        return CareNavResult(
            status=STATUS_NO_VERIFIED,
            entity=entity,
            reason_code="LAB_POPULATION_NOT_AUTHORIZED",
            user_message=no_result_message_for(request),
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
        and not _web_lookup.is_stale_web_row(item.get("source_system_label"), item.get("last_verified_at"))
    )

    # Too few governed hits → search the web for what the user asked (transient, linked, unverified unless on a
    # known listing/official domain). Nothing from the web enters the governed store.
    if len(identities) < _web_lookup.MIN_LOCAL_HITS and _web_lookup.web_lookup_enabled():
        web = _web_identities(request)
        if web:
            known = {i.canonical_name for i in identities}
            identities = (identities + tuple(w for w in web if w.canonical_name not in known))[: max(request.limit, 5)]
            notes.append("WEB_SEARCH_ENRICHED")

    if not identities:
        return CareNavResult(
            status=STATUS_NO_VERIFIED,
            entity=entity,
            reason_code=STATUS_NO_VERIFIED,
            user_message=no_result_message_for(request),
            identity_notes=tuple(notes),
        )

    return CareNavResult(
        status=STATUS_VERIFIED,
        entity=entity,
        identities=identities,
        reason_code=STATUS_VERIFIED,
        user_message=_serialize_hits_message(identities, request.language, request.wants_sources),
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
        if is_directory_source_question(message):
            return CareNavResult(
                status=STATUS_VERIFIED,
                entity=CareNavEntity.SPECIALIST,
                reason_code="DIRECTORY_SOURCE_INFO",
                user_message=source_info_message(language),
            )
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
