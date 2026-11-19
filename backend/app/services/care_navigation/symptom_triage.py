"""J2 (R-094, D-393): from what the user says about pain / symptoms to the BODY AREA and the KIND OF DOCTOR needed.

Deterministic first layer (no model call, no network, no DB): a Persian / English lexicon of body areas and symptom words,
red-flag patterns and a «next question» chooser. It never diagnoses a disease (R-033 / R-074): it only says which kind of
specialist fits the described area and WHY (reason keys; the user-facing wording lives in the copy catalog, R-043), and it
puts emergencies first (R-014). The strong-model layer (J0) will only EXTEND this result (extraction of duration / severity
from free text); the safety rules below stay deterministic.

``triage(text, language)`` -> ``TriageResult``:
  red_flag     True when an emergency pattern matches (the reply must urge help at once, no questions)
  urgency      "emergency" | "soon" | "routine"
  areas        body-area keys found (head, chest, back_joint, skin, stomach, mind, ent, endocrine, eye, dental, urinary,
               heart_rhythm, women, lung)
  specialties  canonical specialty names (Persian), best first
  reasons      specialty -> area key that led to it (for the «why this specialist» sentence)
  next_question  ONE question key to ask next (None for emergencies or when nothing is missing)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_MARKS = re.compile("[ً-ٰٟـ‌‏‎]")
_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("ة", "ه"))
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _fold(text: str) -> str:
    out = (text or "").lower().translate(_DIGITS)
    for a, b in _FOLD:
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", _MARKS.sub(" ", out)).strip()


def _rx(*alternatives: str) -> re.Pattern:
    return re.compile("(?:" + "|".join(_fold(a) for a in alternatives) + ")", re.I)


# --- emergencies first (R-014) --------------------------------------------------------------------------------------
_RED_FLAGS: tuple[tuple[str, re.Pattern], ...] = (
    ("chest_pain_with_breathing", _rx(
        r"(?:قفسه(?: ?ی)? سینه|درد سینه|سینه ام درد|سینه‌ام درد).{0,40}(?:نفس|تنگی|عرق سرد|دست چپ|فک|سنگینی)",
        r"(?:نفس|تنگی نفس|عرق سرد).{0,40}(?:قفسه(?: ?ی)? سینه|درد سینه)",
        r"chest pain.{0,40}(?:breath|sweat|arm|jaw)", r"(?:breath|short of breath).{0,40}chest pain")),
    ("stroke_signs", _rx(
        r"(?:یک طرف|یه طرف|نیمی از).{0,15}(?:صورت|بدن).{0,30}(?:افتاده|ضعیف|بی ?حس|کج)",
        r"(?:صورت|لبم|دهانم).{0,15}(?:افتاده|کج شده)", r"ناگهان.{0,40}(?:ضعف|بی ?حس).{0,25}(?:دست|پا|صورت)",
        r"(?:حرف زدن|تکلم|گفتار).{0,25}(?:مشکل|اختلال|سخت|نمی ?تونم|نمیتونم)",
        r"ناگهان.{0,25}(?:دستم|پایم|صورتم|بدنم|زبانم).{0,20}(?:بی ?حس|ضعیف|سست)",
        r"(?:دستم|پایم|صورتم|بدنم).{0,15}(?:بی ?حس|ضعیف).{0,30}ناگهان", r"face droop|slurred speech|sudden weakness")),
    ("worst_headache", _rx(r"بدترین سردرد", r"سردرد.{0,20}ناگهانی.{0,20}(?:شدید|وحشتناک)", r"worst headache of my life")),
    ("heavy_bleeding", _rx(r"خونریزی.{0,10}(?:شدید|بند نمیاد|بند نمی ?آید|زیاد)", r"heavy bleeding", r"bleeding (?:won.?t|will not) stop")),
    ("fainting", _rx(r"غش کردم", r"از حال رفتم", r"بیهوش شد", r"fainted|passed out|lost consciousness")),
    ("sudden_vision_loss", _rx(
        r"(?:چشمم|چشم ?ام|دیدم|بینایی ?ام|بینایی).{0,25}(?:ناگهان|یکدفعه|یهو|یک ?دفعه).{0,25}(?:سیاه|تار|از دست|رفت|کم شد|دوبین)",
        r"(?:ناگهان|یکدفعه|یهو).{0,25}(?:چشمم|دیدم|بینایی).{0,20}(?:سیاه|تار|از دست|رفت|کم شد)",
        r"(?:چشمم|دیدم).{0,15}(?:سیاه شد|سیاه شده|را از دست)",
        r"(?:ناگهان|یکدفعه|یهو).{0,25}چشم.{0,25}(?:از دست|سیاه|تار|نمی ?بین)", r"از دست دادم.{0,12}(?:بینایی|دید)",
        r"sudden.{0,20}(?:vision|sight).{0,15}(?:loss|blur|black)", r"suddenly (?:can.?t|cannot) see",
        r"(?:vision|sight|eyesight).{0,20}suddenly.{0,20}(?:went|gone|black|blur|lost|dark)", r"suddenly.{0,15}(?:lost|went blind)")),
    ("severe_breathing", _rx(r"نفسم بند (?:اومده|آمده|میاد)", r"نمی ?تونم نفس (?:بکشم|بکشم)", r"نمیتونم نفس", r"can.?t breathe")),
)

# urgent but not an emergency: the person should be seen soon
_SOON: tuple[re.Pattern, ...] = (
    _rx(r"تب.{0,10}(?:بالا|بیشتر از ?۳۹|۴۰)", r"high fever"),
)

# --- body areas -> specialties --------------------------------------------------------------------------------------
# area key -> (patterns, specialties best-first)
_AREAS: tuple[tuple[str, re.Pattern, tuple[str, ...]], ...] = (
    ("heart_rhythm", _rx(r"ضربان", r"تپش قلب", r"طپش قلب", r"قلبم.{0,15}(?:می ?زنه|میزنه|نامنظم|تند)", r"palpitation", r"irregular heart"), ("قلب",)),
    ("chest", _rx(r"قفسه(?: ?ی)? سینه", r"درد سینه", r"سینه ?ام", r"chest pain"), ("قلب", "داخلی")),
    ("head", _rx(r"سردرد", r"سر درد", r"میگرن", r"سرگیجه", r"سرم.{0,12}(?:درد|می ?زنه|میزنه)", r"headache", r"migraine", r"dizz"), ("مغز و اعصاب",)),
    ("back_joint", _rx(r"زانو", r"کمردرد", r"کمر درد", r"کمرم", r"مفصل", r"شانه ?ام", r"گردن ?درد", r"گردنم", r"پشتم", r"ستون فقرات", r"\bknee\b", r"back pain", r"joint"), ("ارتوپدی",)),
    ("skin", _rx(r"پوست", r"خارش", r"قرمزی", r"جوش", r"لکه", r"راش", r"کهیر", r"\brash\b", r"itch"), ("پوست",)),
    ("stomach", _rx(r"معده", r"نفخ", r"ریفلاکس", r"دل ?درد", r"اسهال", r"یبوست", r"سوزش سر ?دل", r"تهوع", r"stomach", r"heartburn", r"bloating"), ("گوارش",)),
    ("mind", _rx(r"اضطراب", r"افسردگی", r"افسرده", r"پانیک", r"استرس شدید", r"بی ?خوابی", r"خوابم نمی ?بره", r"خوابم نمیبره", r"anxiety", r"depress", r"insomnia"), ("روانپزشکی",)),
    ("ent", _rx(r"گلو", r"سینوس", r"گوش ?درد", r"گوشم", r"بینی", r"آب ?ریزش", r"تونسیل", r"ear ?ache", r"sore throat", r"sinus"), ("گوش و حلق و بینی",)),
    ("endocrine", _rx(r"قند خون", r"قندم", r"دیابت", r"تیروئید", r"تشنه", r"diabet", r"thyroid"), ("غدد",)),
    # «دیدم» alone means «I saw»: an eye complaint needs visual-complaint wording (Codex P2, PR 187)
    ("eye", _rx(r"چشم", r"دیدم ?(?:تار|کم|ضعیف|خوب نیست|مشکل|دو ?تا)", r"(?:تار|دو) ?می ?بینم", r"دوبینی", r"تار ?بینی", r"\beye\b", r"\bvision\b"), ("چشم",)),
    ("dental", _rx(r"دندان", r"لثه", r"\btooth\b", r"dental"), ("دندانپزشکی",)),
    ("urinary", _rx(r"ادرار", r"مثانه", r"کلیه", r"urin", r"bladder", r"kidney"), ("اورولوژی", "داخلی")),
    ("women", _rx(r"قاعدگی", r"پریود", r"بارداری", r"حامله", r"ترشح واژینال", r"period", r"pregnan", r"menstru"), ("زنان",)),
    ("lung", _rx(r"سرفه", r"تنگی نفس", r"خس ?خس", r"\bcough\b", r"wheez"), ("ریه", "داخلی")),
)
# secondary specialty added when a companion symptom is present
_COMPANIONS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("back_joint", _rx(r"گز ?گز", r"بی ?حس", r"ضعف.{0,10}پا", r"پایم.{0,12}(?:گز|بی)", r"tingl", r"numb"), "مغز و اعصاب"),
    ("ent", _rx(r"تب", r"fever"), "داخلی"),
    ("endocrine", _rx(r"تشنه", r"ادرار زیاد", r"thirst"), "داخلی"),
    ("urinary", _rx(r"سوزش", r"burning"), "زنان"),
)
# the first question per area (keys of the copy catalog, texts added with the interview package J4)
_QUESTION_BY_AREA = {
    "head": "care_nav.q.headache_detail", "chest": "care_nav.q.duration", "back_joint": "care_nav.q.which_side_and_duration",
    "skin": "care_nav.q.skin_where_since", "stomach": "care_nav.q.stomach_since_food", "mind": "care_nav.q.mind_since_sleep",
    "ent": "care_nav.q.ent_fever_days", "endocrine": "care_nav.q.last_lab", "eye": "care_nav.q.eye_sudden_or_slow",
    "dental": "care_nav.q.dental_swelling", "urinary": "care_nav.q.sex_and_fever", "heart_rhythm": "care_nav.q.palpitation_when",
    "women": "care_nav.q.duration", "lung": "care_nav.q.cough_since_fever",
}


@dataclass(frozen=True)
class TriageResult:
    red_flag: bool = False
    urgency: str = "routine"  # emergency | soon | routine
    red_flag_key: Optional[str] = None
    areas: tuple[str, ...] = ()
    specialties: tuple[str, ...] = ()
    reasons: dict = field(default_factory=dict)  # specialty -> area key
    next_question: Optional[str] = None


def triage(text: str, language: Optional[str] = "fa") -> TriageResult:
    """Never raises. Emergencies first; then area -> specialties; then ONE next question."""
    t = _fold(text)
    if not t:
        return TriageResult()
    # R-099: self-harm talk is a SUPPORT conversation, not «call and leave». ONE definition of it (the I4 safety assessor, which also
    # understands negations like «قصد خودکشی ندارم» and informational questions): care_navigation.crisis_support.
    from backend.app.services.care_navigation.crisis_support import is_self_harm_text

    if is_self_harm_text(text or "", language or "fa"):
        return TriageResult(red_flag=True, urgency="crisis", red_flag_key="self_harm", specialties=("روانپزشکی",),
                            reasons={"روانپزشکی": "self_harm"}, next_question="care_nav.q.what_hurts")
    for key, rx in _RED_FLAGS:
        if rx.search(t):
            return TriageResult(red_flag=True, urgency="emergency", red_flag_key=key, specialties=("اورژانس",) + (("قلب",) if key.startswith("chest") else ()),
                                reasons={"اورژانس": key})
    areas: list[str] = []
    specialties: list[str] = []
    reasons: dict = {}
    for key, rx, specs in _AREAS:
        if rx.search(t):
            areas.append(key)
            for sp in specs:
                if sp not in specialties:
                    specialties.append(sp)
                    reasons[sp] = key
    for area, rx, extra in _COMPANIONS:
        if area in areas and rx.search(t) and extra not in specialties:
            specialties.append(extra)
            reasons[extra] = area
    soon = any(rx.search(t) for rx in _SOON) or "chest" in areas  # chest pain is never «routine»
    if soon and "چشم" in specialties:
        specialties.remove("چشم")
        specialties.insert(0, "چشم")
    question = _QUESTION_BY_AREA.get(areas[0]) if areas else "care_nav.q.which_area"
    return TriageResult(urgency="soon" if soon else "routine", areas=tuple(areas), specialties=tuple(specialties),
                        reasons=reasons, next_question=question)

_QUESTION_MEANING = {
    "care_nav.q.headache_detail": "where in the head, since when, how severe, and whether there is vomiting or a vision change",
    "care_nav.q.duration": "since when it has been happening and whether it gets worse with effort",
    "care_nav.q.which_side_and_duration": "which side / which joint or part of the back, since when, and what makes it worse",
    "care_nav.q.skin_where_since": "where on the body, since when, and whether it itches or spreads",
    "care_nav.q.stomach_since_food": "since when, and whether it relates to meals, vomiting, or blood in stool",
    "care_nav.q.mind_since_sleep": "since when, how it affects sleep and daily life",
    "care_nav.q.ent_fever_days": "how many days, and whether there is fever or difficulty swallowing",
    "care_nav.q.last_lab": "the date and value of the last blood test, if any",
    "care_nav.q.eye_sudden_or_slow": "whether it came suddenly or gradually, and in one eye or both",
    "care_nav.q.dental_swelling": "whether there is swelling or fever and since when",
    "care_nav.q.sex_and_fever": "whether there is fever or flank pain (and the user's sex if unknown)",
    "care_nav.q.palpitation_when": "when it happens (rest / effort), how long it lasts, and any dizziness",
    "care_nav.q.cough_since_fever": "since when, and whether there is fever or breathlessness",
    "care_nav.q.which_area": "which part of the body it is about and since when",
    "care_nav.q.what_hurts": "what is hurting them the most right now (an open invitation to talk)",
}


def llm_hint(result: TriageResult, language: Optional[str] = "fa") -> Optional[str]:
    """A short, deterministic system hint for the chat model (R-094: understanding through questions). None = nothing to add.

    Emergency -> urge help at once. Otherwise: name the kind of doctor that fits and WHY, ask ONE question, never diagnose,
    never advise a drug start / stop / change (R-014 / R-033 / R-074). Meant to be appended like the other context blocks."""
    if result.red_flag_key == "self_harm":
        return None  # handled by care_navigation.crisis_support (one source of the support protocol, no duplicate hint)
    if result.red_flag:
        return (
            "SYMPTOM TRIAGE (deterministic, safety-critical): the user describes a possible EMERGENCY. In the user's language, "
            "plainly and calmly tell them to call the emergency number (115 in Iran) or go to the nearest emergency room NOW, "
            "and to ask someone nearby to stay with them. Ask NO questions, give NO diagnosis and NO drug advice."
        )
    if not result.areas:
        return None
    specs = ", ".join(result.specialties)
    why = ", ".join(f"{sp} (because of the {result.reasons.get(sp, '?')} complaint)" for sp in result.specialties[:2])
    q = _QUESTION_MEANING.get(result.next_question or "", "the key missing detail")
    urgent = " This should be looked at SOON (within a day or two), say so." if result.urgency == "soon" else ""
    return (
        "SYMPTOM TRIAGE (deterministic): the user describes a complaint. "
        f"Body area keys: {', '.join(result.areas)}. Fitting kind of doctor, best first: {specs}. Reason: {why}.{urgent} "
        f"In your reply: (1) acknowledge in one warm sentence; (2) say which kind of doctor fits and why, plainly; "
        f"(3) ask exactly ONE question about {q}; (4) once the user wants a doctor, ask for their neighbourhood if you do not "
        "already know it. Never name a disease as a diagnosis, never advise starting / stopping / changing a drug, "
        "and do not give a list of tips."
    )

