"""J3-a (R-094/R-089, D-405): ONE specialty lexicon for provider requests, in Persian, English and Arabic.

The user can name a kind of doctor in many words: «نورولوژی», «کاردیولوژیست», "heart doctor", "pediatrician", «طبيب قلب».
This module turns any of them into ONE canonical Persian specialty name (the names the triage layer and the booking sites use), and
reads two request qualifiers («شبانه‌روزی» = 24 h, «رضایت بالا» = high rating). Deterministic, no model, no network, never raises.

``find_specialty(text)`` -> canonical name or None;  ``governed_stem(name)`` -> the substring the legacy governed directory matched
before (kept so the old rows still match until the old list is retired, R-093 / J7);  ``has_practitioner_word(text)`` -> the text
names a practitioner by a specialty word («کاردیولوژیست», "pediatrician") even without «دکتر»;  ``qualifiers(text)``.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

_MARKS = re.compile("[ً-ٰٟـ‏‎]")
_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("ة", "ه"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ؤ", "و"), ("ئ", "ی"))


def fold(text: str) -> str:
    out = (text or "").lower().replace("‌", " ").replace("-", " ")
    for a, b in _FOLD:
        out = out.replace(a, b)
    return re.sub(r"\s+", " ", _MARKS.sub("", out)).strip()


# Arabic-script LETTERS only: punctuation such as «،» «؟» is a word boundary (Codex P2, PR 189).
_LETTERS = "ء-غف-يٮ-ۓەۮۯۺ-ۼ"


class Specialty(NamedTuple):
    canonical: str          # Persian name used everywhere (triage, requests, booking-site queries)
    stem: str               # what the legacy governed directory matched on
    aliases: tuple          # fa / en / ar words for the field
    persons: tuple = ()     # words that name the PRACTITIONER by themselves (no «دکتر» needed)


_SPECIALTIES: tuple[Specialty, ...] = (
    Specialty("قلب", "قلب", ("قلب", "قلب و عروق", "کاردیولوژی", "cardiology", "heart", "امراض القلب", "طب القلب"),
              ("کاردیولوژیست", "cardiologist", "اخصائی قلب", "طبیب قلب")),
    Specialty("مغز و اعصاب", "اعصاب", ("مغز و اعصاب", "اعصاب", "نورولوژی", "neurology", "brain", "الجهاز العصبی", "مخ و اعصاب", "امراض الاعصاب"),
              ("نورولوژیست", "neurologist", "جراح مغز")),
    Specialty("دندانپزشکی", "دندان", ("دندانپزشک", "دندان پزشک", "دندانپزشکی", "دندان", "dentist", "dental", "dentistry", "اسنان", "طب الاسنان"),
              ("dentist", "طبیب اسنان", "دندانپزشک", "دندان پزشک")),
    Specialty("اورولوژی", "اورولوژی", ("اورولوژی", "ارولوژی", "کلیه و مجاری ادرار", "مجاری ادراری", "urology", "المسالک البولیه", "جراحه المسالک"),
              ("اورولوژیست", "ارولوژیست", "urologist")),
    Specialty("اطفال", "اطفال", ("اطفال", "کودکان", "پزشک کودک", "کودک", "pediatrics", "paediatrics", "pediatric", "paediatric", "طب الاطفال", "اطفال"),
              ("pediatrician", "paediatrician", "طبیب اطفال", "متخصص کودکان")),
    Specialty("زنان", "زنان", ("زنان", "زایمان", "زنان و زایمان", "gynecology", "gynaecology", "obstetrics", "النساء", "امراض النساء", "نسائیه", "نسائی"),
              ("gynecologist", "gynaecologist", "obstetrician", "طبیب نسائی", "طبیبه نسائیه")),
    Specialty("پوست", "پوست", ("پوست", "پوست و مو", "درماتولوژی", "dermatology", "skin", "جلدیه", "امراض جلدیه", "جلد"),
              ("dermatologist", "درماتولوژیست", "طبیب جلدیه")),
    Specialty("ارتوپدی", "ارتوپد", ("ارتوپدی", "ارتوپد", "orthopedics", "orthopaedics", "orthopedic", "orthopaedic", "bone", "عظام", "جراحه عظام"),
              ("orthopedist", "orthopaedist", "طبیب عظام")),
    Specialty("گوارش", "گوارش", ("گوارش", "معده", "گاستروانترولوژی", "gastroenterology", "gastro", "الجهاز الهضمی", "معده"),
              ("gastroenterologist", "گاستروانترولوژیست")),
    Specialty("چشم", "چشم", ("چشم", "چشم پزشکی", "چشم پزشک", "افتالمولوژی", "ophthalmology", "eye", "عیون", "طب العیون"),
              ("ophthalmologist", "optometrist", "چشم پزشک", "طبیب عیون")),
    Specialty("گوش و حلق و بینی", "گوش و حلق و بینی", ("گوش و حلق و بینی", "گوش و حلق", "ای ان تی", "ent", "otolaryngology", "انف و اذن و حنجره"),
              ("otolaryngologist", "ent doctor", "ent specialist")),
    Specialty("روانپزشکی", "روان", ("روانپزشکی", "روان پزشکی", "روانپزشک", "روان پزشک", "psychiatry", "الطب النفسی", "طب نفسی"),
              ("psychiatrist", "طبیب نفسی", "روانپزشک", "روان پزشک")),
    Specialty("روان‌شناسی", "روان", ("روان شناس", "روانشناسی", "روان شناسی", "مشاوره", "psychology", "counselling", "counseling", "علم النفس", "ارشاد نفسی"),
              ("psychologist", "therapist", "counselor", "counsellor", "روانشناس", "روان شناس", "اخصائی نفسی")),
    Specialty("غدد", "غدد", ("غدد", "دیابت", "تیروئید", "اندوکرینولوژی", "endocrinology", "diabetes", "thyroid", "الغدد الصماء", "غدد صماء"),
              ("endocrinologist", "اندوکرینولوژیست")),
    Specialty("ریه", "ریه", ("ریه", "تنفس", "پولمونولوژی", "pulmonology", "lung", "lungs", "الصدریه", "امراض الصدر", "الرئه"),
              ("pulmonologist", "پولمونولوژیست")),
    Specialty("کلیه", "کلیه", ("نفرولوژی", "کلیه", "nephrology", "kidney", "الکلی", "امراض الکلی"),
              ("nephrologist", "نفرولوژیست")),
    Specialty("داخلی", "داخلی", ("داخلی", "internal medicine", "الباطنیه", "باطنیه", "طب باطنی"),
              ("internist", "اخصائی باطنیه")),
    Specialty("انکولوژی", "سرطان", ("سرطان", "آنکولوژی", "انکولوژی", "oncology", "cancer", "الاورام", "اورام"),
              ("oncologist", "انکولوژیست", "آنکولوژیست")),
    Specialty("جراحی عمومی", "جراحی", ("جراحی عمومی", "جراح عمومی", "جراحی", "general surgery", "surgery", "الجراحه العامه", "جراحه عامه"),
              ("surgeon", "جراح", "جراح عمومی")),
    Specialty("فیزیوتراپی", "فیزیوتراپی", ("فیزیوتراپی", "طب فیزیکی", "physiotherapy", "physical therapy", "العلاج الطبیعی", "علاج طبیعی"),
              ("physiotherapist", "فیزیوتراپیست", "physical therapist")),
    Specialty("تغذیه", "تغذیه", ("تغذیه", "رژیم درمانی", "nutrition", "dietetics", "diet", "التغذیه"),
              ("nutritionist", "dietitian", "dietician", "متخصص تغذیه", "اخصائی تغذیه")),
)


def _compile(words: tuple) -> Optional[re.Pattern]:
    folded = sorted({fold(w) for w in words if w}, key=len, reverse=True)
    if not folded:
        return None
    body = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in folded)
    return re.compile(r"(?<![a-z" + _LETTERS + r"])(?:" + body + r")(?![a-z" + _LETTERS + r"])")


_GENERIC = frozenset({"جراحی عمومی"})

_ALIAS_RX = [(sp, _compile(sp.aliases + sp.persons)) for sp in _SPECIALTIES]
_PERSON_RX = _compile(tuple(w for sp in _SPECIALTIES for w in sp.persons))
_BY_NAME = {sp.canonical: sp for sp in _SPECIALTIES}


def find_specialty(text: str) -> Optional[str]:
    """The canonical Persian specialty named in ``text`` (the LONGEST matching word wins), or None. Never raises."""
    try:
        t = fold(text)
        # A generic practitioner word («surgeon») never overrides an explicitly named specialty («eye surgeon» -> چشم): Codex P2.
        for generic in (False, True):
            best: tuple[int, Optional[str]] = (0, None)
            for sp, rx in _ALIAS_RX:
                if rx is None or (sp.canonical in _GENERIC) != generic:
                    continue
                for m in rx.finditer(t):
                    if len(m.group(0)) > best[0]:
                        best = (len(m.group(0)), sp.canonical)
            if best[1]:
                return best[1]
        return None
    except Exception:  # noqa: BLE001
        return None


def governed_stem(name: Optional[str]) -> Optional[str]:
    """What the legacy governed directory matched on for this canonical name (unknown names pass through unchanged)."""
    if not name:
        return name
    sp = _BY_NAME.get(name)
    return sp.stem if sp else name


def has_practitioner_word(text: str) -> bool:
    """«کاردیولوژیست», "pediatrician", «طبيب قلب»: a practitioner named by the specialty word itself."""
    try:
        return bool(_PERSON_RX and _PERSON_RX.search(fold(text)))
    except Exception:  # noqa: BLE001
        return False


_HOURS_24 = re.compile(fold(r"شبانه ?روزی|۲۴ ?ساعته|24 ?ساعته|24 ?hours?|24 ?/ ?7|24h|round the clock|open all night|على مدار الساعة|علی مدار الساعه|24 ساعه"))
_HIGH_RATING = re.compile(fold(
    r"رضایت (?:بالا|زیاد|بیماران)|امتیاز بالا|خوش نام|محبوب|پر ?مراجعه|ممتاز|highly rated|best rated|top rated|well reviewed|high rating|"
    r"تقییم عالی|الاعلى تقییما|الافضل تقییما"))


def qualifiers(text: str) -> tuple[str, ...]:
    """Request qualifiers read from the text: ``24h`` and/or ``high_rating``."""
    t = fold(text)
    out = []
    if _HOURS_24.search(t):
        out.append("24h")
    if _HIGH_RATING.search(t):
        out.append("high_rating")
    return tuple(out)


_ENGLISH = {
    "قلب": "Cardiology", "مغز و اعصاب": "Neurology", "اورولوژی": "Urology", "ارتوپدی": "Orthopedics", "پوست": "Dermatology",
    "گوارش": "Gastroenterology", "روانپزشکی": "Psychiatry", "غدد": "Endocrinology", "ریه": "Pulmonology", "کلیه": "Nephrology",
    "انکولوژی": "Oncology",
}


def governed_terms(name: Optional[str]) -> tuple:
    """Every string a legacy governed row may carry for this specialty: the Persian stem first, then the English label (Codex P2)."""
    if not name:
        return ()
    terms = [governed_stem(name)]
    if _ENGLISH.get(name):
        terms.append(_ENGLISH[name])
    return tuple(t for t in terms if t)
