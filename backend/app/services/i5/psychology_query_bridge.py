"""Deterministic Persian/Arabic -> English keyword bridge for psychology / wellbeing questions (R-044).

The governed knowledge is English official text. A Persian/Arabic question reaches it through English keyword
alternatives. Until now every such question needed an LLM translation call (about 2-4 s) and the call sometimes
chose the wrong topic (OCD -> PTSD, grief -> panic). For the topics people actually bring to Sedi as a friend this
module answers instantly and exactly, with the official English names the sources use (NHS, NIMH, NCCIH).

- Leaf module: no app imports, no I/O, no model call. Deterministic.
- Output is a non-authoritative search hint (same contract as ``query_translation``): evidence still comes from
  governed, ELIGIBLE knowledge units only.
- Conservative: a topic fires only when its marker words are present; messages that also name a disease
  (diabetes, blood pressure, cancer ...) are left to the existing LLM path so combined questions keep working.
- Keyword tables live here by design (R-043: parsing regexes / keyword lists are not user-facing copy).
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

MAX_ALTERNATIVES = 4
MAX_TOPICS = 2

_TASHKEEL = re.compile(r"[ً-ٰٟـ]")  # Arabic diacritics + tatweel
_MAP = str.maketrans(
    {
        "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", "ئ": "ی",
        "‌": " ", "‏": " ", "‎": " ",
    }
)


def normalize(text: str) -> str:
    """Unify Persian/Arabic letter variants, strip diacritics, collapse spaces, lower-case Latin."""
    s = _TASHKEEL.sub("", str(text or "")).translate(_MAP).lower()
    return " ".join(s.split())


class _Topic(NamedTuple):
    key: str
    markers: re.Pattern
    alternatives: tuple[str, ...]
    also: Optional[re.Pattern] = None  # must ALSO match (e.g. postpartum needs a sad/low word)


def _r(pattern: str) -> re.Pattern:
    return re.compile(pattern)


# Patterns are written in NORMALIZED form (ی ک ه ا, no diacritics, ZWNJ -> space).
_TOPICS: tuple[_Topic, ...] = (
    _Topic("panic", _r(r"پانیک|حمله ی? ?هراس|حمله هراس|هلع"), ("panic attack", "panic disorder")),
    _Topic("ocd", _r(r"وسواس|افکار تکراری|افکار مزاحم|افکار متکرره"), ("obsessive compulsive disorder", "OCD")),
    _Topic("ptsd", _r(r"تروما|ضربه روحی|استرس پس از|ما بعد الصدمه|صدمه نفسیه|اتفاق بد|اتفاق وحشتناک|حدث مولم"),
           ("PTSD", "post-traumatic stress disorder", "trauma")),
    _Topic("postpartum", _r(r"زایمان|نوزاد|بچه دار شدن|ولاده|مولود|طفل"),
           ("postnatal depression", "postpartum depression", "perinatal"),
           also=_r(r"غم|افسرد|گریه|ناامید|خسته|حزن|اکتئاب|بکاء|یاس")),
    _Topic("seasonal", _r(r"افسردگی فصلی|الاکتئاب الموسمی|اکتئاب موسمی"), ("seasonal affective disorder", "SAD")),
    _Topic("depression", _r(r"افسرد|ناامید|غمگین|بی حوصله|اکتئاب|حزن|الیاس|یائس"),
           ("depression", "depression in adults", "low mood")),
    _Topic("social_anxiety", _r(r"فوبیا|اضطراب اجتماعی|جلوی جمع|کنار ادم|رهاب|قلق اجتماعی|امام الاخرین|وسط الناس"),
           ("social anxiety", "phobias", "anxiety")),
    _Topic("anxiety", _r(r"اضطراب|نگرانی|دلشوره|دل شوره|قلق|التفکیر الزائد|الافراط فی التفکیر"),
           ("anxiety", "generalised anxiety disorder", "coping with stress and anxiety")),
    _Topic("burnout", _r(r"فرسود|خستگی شغلی|خسته از کار|از کار خسته|احتراق وظیفی|محترق|منهک"),
           ("burnout", "work stress", "stress busters")),
    _Topic("stress", _r(r"استرس|فشار روانی|تنیدگی|توتر|ضغط نفسی|ضغوط نفسیه|ضغط عصبی|اجهاد"),
           ("stress", "stress busters", "coping with stress")),
    _Topic("sleep", _r(r"بی خوابی|بیخوابی|بد خوابی|خوابم نمی|خوابیدن|کیفیت خواب|ارق|الارق|لا استطیع النوم|اضطراب النوم"),
           ("insomnia", "sleep", "sleep habits")),
    _Topic("grief", _r(r"سوگ|عزادار|داغدار|داغ عزیز|فوت کرد|فوت شد|مرگ عزیز|از دست دادن عزیز|فقدان|حداد|وفاه|فقدت"),
           ("grief", "bereavement", "loss")),
    _Topic("loneliness", _r(r"تنهایی|احساس تنها|تنهام|وحده|الوحده|وحید|عزله"),
           ("loneliness", "connect with other people", "mental wellbeing")),
    _Topic("anger", _r(r"عصبانی|خشم|پرخاشگری|غضب|غاضب"), ("anger", "managing anger")),
    _Topic("self_esteem", _r(r"اعتماد به نفس|عزت نفس|خودباوری|ثقه بالنفس|ثقتی بنفسی|تقدیر الذات|احترام الذات"),
           ("self-esteem", "confidence", "mental wellbeing")),
    _Topic("mindfulness", _r(r"ذهن اگاهی|ذهن اگاه|مدیتیشن|مراقبه|التامل|الیقظه الذهنیه"),
           ("mindfulness", "meditation")),
    _Topic("breathing", _r(r"تنفس|نفس عمیق|شهیق|زفیر"), ("breathing exercises", "breathing")),
    _Topic("cbt", _r(r"شناختی رفتاری|درمان شناختی|cbt|المعرفی السلوکی|العلاج المعرفی"),
           ("cognitive behavioural therapy", "CBT")),
    _Topic("motivation", _r(r"انگیزه|عادت سالم|الدافع|دافعی|عادات صحیه"),
           ("healthy habits", "physical activity", "motivation")),
)

# A disease word means the user is asking about the condition too: leave it to the existing translation path.
_DISEASE = _r(
    r"دیابت|قند خون|فشار خون|سرطان|ام اس|ای ال اس|سکته|کلیه|کلیوی|آسم|asthma|سکری|ضغط الدم|التصلب|ربو"
)


def bridge_alternatives(query: str) -> list[str]:
    """English keyword alternatives for a clear psychology / wellbeing question, [] when not applicable."""
    s = normalize(query)
    if not s or _DISEASE.search(s):
        return []
    matched: list[_Topic] = []
    for topic in _TOPICS:
        if topic.markers.search(s) and (topic.also is None or topic.also.search(s)):
            matched.append(topic)
            if len(matched) == MAX_TOPICS:
                break
    if not matched:
        return []
    out: list[str] = []
    depth = max(len(t.alternatives) for t in matched)
    for i in range(depth):  # most specific name of each topic first, then the broader ones
        for topic in matched:
            if i < len(topic.alternatives):
                cand = topic.alternatives[i]
                if cand.lower() not in {c.lower() for c in out}:
                    out.append(cand)
                if len(out) == MAX_ALTERNATIVES:
                    return out
    return out
