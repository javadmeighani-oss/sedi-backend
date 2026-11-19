"""Iranian place gazetteer for care navigation (R-089, D-381).

Finds a city and/or a neighbourhood (محله/منطقه) in a free-text request such as «یه دکتر قلب خوب در تهرانپارس»
or «آزمایشگاه نزدیک منطقه ۸». Spelling variants are tolerated: with/without space or half-space
(«تهرانپارس»، «تهران‌پارس»، «تهران پارس») and Arabic Yeh/Kaf. A neighbourhood implies its city (Tehran list).

Read-only, deterministic, no I/O. Paziresh24 slugs are only listed for cities verified on 2026-11-17.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

# Arabic-script LETTERS only: punctuation such as «،» «؛» «؟» counts as a word boundary (Codex P2, PR #184).
_FA = "ء-غف-يٮ-ۓەۮۯۺ-ۼ"
_SEP = "[\\s‌‏‎-]?"

# Persian name -> Paziresh24 slug (None = city known, no verified slug).
CITIES: dict[str, Optional[str]] = {
    "تهران": "tehran", "مشهد": "mashhad", "اصفهان": "isfahan", "شیراز": "shiraz", "تبریز": "tabriz",
    "کرج": "karaj", "قم": "qom", "اهواز": "ahvaz", "رشت": "rasht", "کرمان": "kerman", "یزد": "yazd",
    "کرمانشاه": None, "ارومیه": None, "زاهدان": None, "همدان": None, "اردبیل": None, "بندر عباس": None,
    "اراک": None, "قزوین": None, "زنجان": None, "سنندج": None, "گرگان": None, "ساری": None, "بوشهر": None,
    "خرم آباد": None, "بیرجند": None, "سمنان": None, "ایلام": None, "یاسوج": None, "شهرکرد": None,
    "کاشان": None, "بابل": None, "آمل": None, "دزفول": None, "نیشابور": None, "سبزوار": None,
    "قائم شهر": None, "ورامین": None, "اسلامشهر": None, "شهریار": None, "پردیس": None, "لواسان": None,
    "دماوند": None, "بجنورد": None, "کیش": None,
}
_CITIES_EN: dict[str, str] = {
    "tehran": "تهران", "mashhad": "مشهد", "isfahan": "اصفهان", "esfahan": "اصفهان", "shiraz": "شیراز",
    "tabriz": "تبریز", "karaj": "کرج", "qom": "قم", "ahvaz": "اهواز", "rasht": "رشت", "kerman": "کرمان",
    "yazd": "یزد", "kermanshah": "کرمانشاه", "urmia": "ارومیه", "hamedan": "همدان", "qazvin": "قزوین",
}

# Arabic spellings that differ from the Persian ones (J3-a, D-405); Yeh/Kaf are folded before matching.
_CITIES_AR: dict[str, str] = {
    "طهران": "تهران", "أصفهان": "اصفهان", "اصبهان": "اصفهان", "أهواز": "اهواز", "الأهواز": "اهواز", "الاهواز": "اهواز",
    "مشهد المقدسة": "مشهد", "قم المقدسة": "قم", "كرمانشاه": "کرمانشاه", "همدان": "همدان",
}

# Tehran neighbourhoods / districts (spaces mark optional separators).
TEHRAN_AREAS: tuple[str, ...] = (
    "تهران پارس", "نارمک", "پاسداران", "ونک", "سعادت آباد", "شهرک غرب", "جردن", "تجریش", "الهیه", "زعفرانیه",
    "نیاوران", "اقدسیه", "فرمانیه", "دروس", "قیطریه", "ستارخان", "صادقیه", "پونک", "جنت آباد", "یوسف آباد",
    "امیرآباد", "گیشا", "مرزداران", "شهران", "اکباتان", "چیتگر", "تهران نو", "نظام آباد", "مجیدیه",
    "شمیران نو", "حکیمیه", "هفت حوض", "قلهک", "ظفر", "میرداماد", "شهر ری", "نازی آباد", "یافت آباد", "افسریه",
    "خاک سفید", "لویزان", "اندرزگو", "کامرانیه", "ازگل", "سید خندان", "منیریه", "طرشت", "تهرانسر", "شهرک اکباتان", "پرند",
    "دولت آباد", "جیحون", "سلسبیل", "خزانه", "مشیریه", "شهرک محلاتی", "دارآباد", "باغ فیض", "شهرزیبا",
    # Street / square names shared by many Iranian cities (شریعتی، ولیعصر، مطهری…) are deliberately NOT listed (Codex P2).
    "وردآورد", "میدان ونک", "میدان تجریش", "پل رومی", "آرژانتین", "شهرک قدس", "شهرک راه آهن", "اتابک",
)
_AREAS_EN: dict[str, str] = {
    "tehranpars": "تهران پارس", "tehran pars": "تهران پارس", "narmak": "نارمک", "pasdaran": "پاسداران",
    "vanak": "ونک", "saadat abad": "سعادت آباد", "saadatabad": "سعادت آباد", "shahrak gharb": "شهرک غرب",
    "jordan": "جردن", "tajrish": "تجریش", "elahieh": "الهیه", "zafaranieh": "زعفرانیه", "niavaran": "نیاوران",
    "sattarkhan": "ستارخان", "sadeghieh": "صادقیه", "punak": "پونک", "yousef abad": "یوسف آباد",
    "gisha": "گیشا", "ekbatan": "اکباتان", "tehran no": "تهران نو", "gheytarieh": "قیطریه",
}

_DISTRICT = re.compile(r"(?<![" + _FA + r"])منطقه\s*([0-9۰-۹]{1,2})(?![0-9۰-۹])")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


class Place(NamedTuple):
    city: Optional[str]
    area: Optional[str]
    city_slug: Optional[str]
    city_inferred: bool = False  # True = Tehran assumed from the neighbourhood (an explicit city may override it)


def normalize(text: str) -> str:
    """Arabic Yeh/Kaf -> Persian; drop half-space, bidi marks and spaces; lower-case (for containment checks)."""
    t = (text or "").replace("ي", "ی").replace("ك", "ک").replace("ى", "ی")
    return re.sub(r"[\s‌‏‎-]+", "", t).lower()


def _pattern(name: str) -> re.Pattern[str]:
    parts = [re.escape(ch) for ch in name.replace("ي", "ی").replace("ك", "ک")]
    body = "".join(_SEP if p in ("\\ ", " ") else p for p in parts)
    return re.compile(r"(?<![" + _FA + r"])" + body + r"(?![" + _FA + r"])")


def _canon(name: str) -> str:
    """Display form: half-space joins (e.g. «تهران‌پارس», «سعادت‌آباد»)."""
    return name.replace(" ", "‌") if name.endswith(("آباد", "پارس", " نو")) else name


_CITY_PATS = sorted(((n, _pattern(n)) for n in CITIES), key=lambda x: -len(x[0]))
_AREA_PATS = sorted(((n, _pattern(n)) for n in TEHRAN_AREAS), key=lambda x: -len(x[0]))


def aliases(city: Optional[str]) -> set[str]:
    """Normalized spellings of one city in Persian and English («Shiraz» == «شیراز»)."""
    if not city:
        return set()
    out = {normalize(city)}
    fa = _CITIES_EN.get(city.strip().lower())
    if fa:
        out.add(normalize(fa))
    for en, fa2 in _CITIES_EN.items():
        if normalize(fa2) in out:
            out.add(normalize(en))
    for ar, fa3 in _CITIES_AR.items():  # Arabic spellings of the same city (Codex P2, PR 189)
        if normalize(fa3) in out:
            out.add(normalize(ar))
    return out


def mentions(text_normalized: str, city: Optional[str]) -> bool:
    return any(a and a in text_normalized for a in aliases(city))


def slug_for(city: Optional[str]) -> Optional[str]:
    """Verified Paziresh24 slug for a Persian or English city name, else None."""
    if not city:
        return None
    fa = city.replace("‌", " ")
    if fa in CITIES:
        return CITIES[fa]
    alias = _CITIES_EN.get(city.strip().lower()) or _CITIES_AR.get(city.strip().replace("ي", "ی").replace("ك", "ک"))
    return CITIES.get(alias) if alias else None


def find_place(text: str) -> Place:
    """City and/or neighbourhood named in ``text`` (longest match wins). Never raises."""
    raw = (text or "").replace("ي", "ی").replace("ك", "ک")
    low = raw.lower()
    area: Optional[str] = None
    for name, pat in _AREA_PATS:
        m = pat.search(raw)
        # «تهران پارس» must not be read as just the city «تهران»
        if m:
            area = _canon(name)
            raw = raw[: m.start()] + " " + raw[m.end():]
            break
    area_en = False
    if area is None:
        for en, fa in sorted(_AREAS_EN.items(), key=lambda x: -len(x[0])):
            if re.search(r"\b" + re.escape(en) + r"\b", low):
                area, area_en = _canon(fa), True
                break
    if area is None:
        d = _DISTRICT.search(raw)
        if d:
            area = "منطقه " + d.group(1).translate(_FA_DIGITS)
    city: Optional[str] = None
    slug: Optional[str] = None
    for name, pat in _CITY_PATS:
        if pat.search(raw):
            city, slug = (_canon(name) if " " in name else name), CITIES[name]
            break
    if city is None:
        for en, fa in _CITIES_EN.items():
            if re.search(r"\b" + re.escape(en) + r"\b", low):
                city, slug = en.title(), CITIES.get(fa)  # keep the user's own (English) city name
                break
    if city is None:
        for ar, fa in sorted(_CITIES_AR.items(), key=lambda x: -len(x[0])):
            if _pattern(ar).search(raw):
                city, slug = fa, CITIES.get(fa)
                break
    inferred = False
    if area and city is None:
        # every listed neighbourhood / numbered district defaults to Tehran (in the request's script)
        city, slug, inferred = ("Tehran" if area_en else "تهران"), "tehran", True
    return Place(city=city, area=area, city_slug=slug, city_inferred=inferred)
