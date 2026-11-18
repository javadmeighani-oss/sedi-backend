"""Iranian place gazetteer for care navigation (R-089, D-381).

Finds a city and/or a neighbourhood (محله/منطقه) in a free-text request such as «یه دکتر قلب خوب در تهرانپارس»
or «آزمایشگاه نزدیک منطقه ۸». Spelling variants are tolerated: with/without space or half-space
(«تهرانپارس»، «تهران‌پارس»، «تهران پارس») and Arabic Yeh/Kaf. A neighbourhood implies its city (Tehran list).

Read-only, deterministic, no I/O. Paziresh24 slugs are only listed for cities verified on 2026-11-17.
"""
from __future__ import annotations

import re
from typing import NamedTuple, Optional

_FA = "؀-ۿ"
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

# Tehran neighbourhoods / districts (spaces mark optional separators).
TEHRAN_AREAS: tuple[str, ...] = (
    "تهران پارس", "نارمک", "پاسداران", "ونک", "سعادت آباد", "شهرک غرب", "جردن", "تجریش", "الهیه", "زعفرانیه",
    "نیاوران", "اقدسیه", "فرمانیه", "دروس", "قیطریه", "ستارخان", "صادقیه", "پونک", "جنت آباد", "یوسف آباد",
    "امیرآباد", "گیشا", "مرزداران", "شهران", "اکباتان", "چیتگر", "پیروزی", "تهران نو", "نظام آباد", "مجیدیه",
    "شمیران نو", "حکیمیه", "هفت حوض", "قلهک", "ظفر", "میرداماد", "شهر ری", "نازی آباد", "یافت آباد", "افسریه",
    "خاک سفید", "لویزان", "اندرزگو", "کامرانیه", "ازگل", "سید خندان", "شریعتی", "ولیعصر", "فاطمی", "میدان انقلاب",
    "میدان آزادی", "منیریه", "میدان امام حسین", "هفت تیر", "طرشت", "تهرانسر", "شهرک اکباتان", "پرند",
    "دولت آباد", "جیحون", "سلسبیل", "خزانه", "مشیریه", "شهرک محلاتی", "دارآباد", "باغ فیض", "شهرزیبا",
    "وردآورد", "بلوار کشاورز", "میدان ونک", "میدان تجریش", "پل رومی", "سهروردی", "مطهری", "آرژانتین",
    "شهرک قدس", "شهرک راه آهن", "نواب", "اتابک",
)
_AREAS_EN: dict[str, str] = {
    "tehranpars": "تهران پارس", "tehran pars": "تهران پارس", "narmak": "نارمک", "pasdaran": "پاسداران",
    "vanak": "ونک", "saadat abad": "سعادت آباد", "saadatabad": "سعادت آباد", "shahrak gharb": "شهرک غرب",
    "jordan": "جردن", "tajrish": "تجریش", "elahieh": "الهیه", "zafaranieh": "زعفرانیه", "niavaran": "نیاوران",
    "sattarkhan": "ستارخان", "sadeghieh": "صادقیه", "punak": "پونک", "yousef abad": "یوسف آباد",
    "gisha": "گیشا", "ekbatan": "اکباتان", "piroozi": "پیروزی", "tehran no": "تهران نو", "gheytarieh": "قیطریه",
}

_DISTRICT = re.compile(r"(?<![" + _FA + r"])منطقه\s*([0-9۰-۹]{1,2})(?![0-9۰-۹])")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


class Place(NamedTuple):
    city: Optional[str]
    area: Optional[str]
    city_slug: Optional[str]


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
    if area is None:
        for en, fa in sorted(_AREAS_EN.items(), key=lambda x: -len(x[0])):
            if re.search(r"\b" + re.escape(en) + r"\b", low):
                area = _canon(fa)
                break
    if area is None:
        d = _DISTRICT.search(raw)
        if d:
            area = "منطقه " + d.group(1).translate(_FA_DIGITS)
    city: Optional[str] = None
    for name, pat in _CITY_PATS:
        if pat.search(raw):
            city = _canon(name) if " " in name else name
            break
    if city is None:
        for en, fa in _CITIES_EN.items():
            if re.search(r"\b" + re.escape(en) + r"\b", low):
                city = fa
                break
    if area and city is None:
        city = "تهران"  # every listed neighbourhood / numbered district defaults to Tehran
    slug = CITIES.get(city.replace("‌", " ")) if city else None
    return Place(city=city, area=area, city_slug=slug)
