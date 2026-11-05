"""R-063/R-065: answer-binding - a short reply that follows Sedi's own question IS the answer to that question.

Phone test 2026-11-05: Sedi asked «how many hours did you sleep?», the user wrote «۱۱ یا ۱۲ شب» (a bedtime) and Sedi
answered with an absurd clarification («...یا ۱۱ تا ۱۲ ساعت خوابیده‌ای؟») and then another one. The fix is a general
mechanism, not a sleep rule: for EVERY kind of question Sedi asks (time of day, duration, frequency, quantity, scale,
age/height/weight, medication, name, yes/no, either-or) the model gets one short hint that the user's short message
answers that question, how to read it, and that a reply of a different kind than asked is accepted for what it obviously
is. Deterministic, language-aware (fa/ar/en), no model call, fail-open (returns "" when it does not apply).
"""

from __future__ import annotations

import re
from typing import Final, Optional

_MAX_REPLY_WORDS: Final[int] = 8

_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("‌", " "))


def _fold(text: str) -> str:
    out = (text or "").lower()
    for a, b in _FOLD:
        out = out.replace(a, b)
    return re.sub(r"[ً-ْ]", "", out)


def _p(*alternatives: str) -> re.Pattern:
    return re.compile("(?:" + "|".join(_fold(a) for a in alternatives) + ")", re.I)


# Order matters: the first matching type wins (specific before general).
_TYPES: Final[tuple] = (
    ("scale", _p(
        r"از\s+[0-9۰-۹]+\s+تا\s+[0-9۰-۹]+", r"مقیاس", r"نمره", r"من\s+[0-9٠-٩]+\s+الی", r"مقياس", r"درجه\s+من",
        r"\bscale\b", r"from\s+\d+\s+to\s+\d+", r"\brate\b",
    )),
    ("age_body", _p(
        r"چند\s+سال(?:ت|ته|\s+دار|\s+سن)", r"\bسن\s*(?:ت|تون|تان|شما)?\b", r"\bقد\s*(?:ت|تون|تان)?\b", r"\bوزن\s*(?:ت|تون|تان)?\b",
        r"چند\s+کیلو", r"چند\s+سانت", r"كم\s+عمرك", r"كم\s+طولك", r"كم\s+وزنك", r"عمرك|طولك|وزنك",
        r"how\s+old", r"your\s+age\b", r"how\s+tall", r"your\s+(?:height|weight)\b", r"how\s+much\s+do\s+you\s+weigh",
    )),
    ("medication", _p(
        r"چه\s+دارو", r"دارو\w*\s+(?:مصرف|می)", r"\bدوز\b", r"قرص\s+(?:می|مصرف)", r"آنتی", r"أي\s+دواء", r"جرعة", r"\bدواء\b",
        r"which\s+(?:medication|medicine|drug)", r"what\s+(?:medication|medicine|drug)", r"\bdos(?:e|age)\b",
    )),
    ("name", _p(
        r"اسم\s*(?:ت|تون|تان|شما)?\s*(?:چیه|چیست)", r"چه\s+(?:اسمی|نامی)", r"نام\s*(?:ت|تان|شما)?\s*(?:چیه|چیست)",
        r"ما\s+اسمك", r"your\s+name", r"what\s+should\s+i\s+call\s+you",
    )),
    ("frequency", _p(
        r"چند\s+بار", r"هر\s+چند\s+وقت", r"چند\s+مرتبه", r"چند\s+دفعه", r"كم\s+مرة", r"كم\s+مرات",
        r"how\s+often", r"how\s+many\s+times",
    )),
    ("duration", _p(
        r"چند\s+(?:ساعت|دقیقه|روز|هفته|ماه)", r"چند\s+سال\s+است", r"چه\s+مدت", r"چقدر\s+(?:وقت|طول|مدت)", r"از\s+کی\b",
        r"كم\s+(?:ساعة|ساعات|دقيقة|يوما|يوم|أسبوع)", r"منذ\s+متى", r"كم\s+من\s+الوقت", r"كم\s+مدة",
        r"how\s+many\s+(?:hours|minutes|days|weeks|months|years)", r"how\s+long",
    )),
    ("time_of_day", _p(
        r"چه\s+ساعت", r"ساعت\s+چند", r"چه\s+موقع", r"چه\s+وقت", r"چه\s+زمان", r"کی\s+(?:معمولا|می|بیدار|به)",
        r"في\s+أي\s+(?:ساعة|وقت)", r"الساعة\s+كم", r"\bمتى\b",
        r"what\s+time", r"when\s+(?:do|did|are|will)\s+you", r"at\s+what\s+time",
    )),
    ("quantity", _p(
        r"چند\s+(?:تا|لیوان|وعده|قاشق|عدد|قرص|نخ|فنجان|تکه)", r"چقدر\s+(?:می|مصرف|ورزش)", r"كم\s+(?:كوب|وجبة|عدد|حبة|ملعقة)",
        r"how\s+many\b", r"how\s+much\b",
    )),
    ("yes_no", _p(
        r"^\s*آیا\b", r"(?:داری|دارید|داشتی|داشته\s*ای|هست|هستی|هستید|نیست|بوده|شده|می\s*کنی|می\s*کنید|می\s*خوری|کرده\s*ای)\s*[؟?]?\s*$",
        r"^\s*هل\b", r"^\s*(?:do|does|did|are|is|have|has|can|could|would|will|was|were)\b",
    )),
    ("choice", _p(r"\bیا\b", r"\bأو\b", r"\bor\b")),
)

# What the short reply means, per type, per language.
_MEANING: Final[dict] = {
    "fa": {
        "scale": "یک عدد روی همان مقیاس است",
        "age_body": "یک عدد برای سن، قد یا وزن است",
        "medication": "نام یا دوز یک دارو است",
        "name": "یک نام است",
        "frequency": "تعداد دفعات است",
        "duration": "مدت زمان (ساعت، دقیقه، روز…) است",
        "time_of_day": "یک ساعت از شبانه‌روز است (مثلاً زمان خوابیدن، بیدار شدن یا غذا خوردن)، نه یک مدت",
        "quantity": "یک مقدار یا تعداد است",
        "yes_no": "بله، خیر یا یک پاسخ نیمه‌کاره است",
        "choice": "انتخاب یکی از گزینه‌های همان سؤال است",
    },
    "ar": {
        "scale": "رقم على المقياس نفسه",
        "age_body": "رقم للعمر أو الطول أو الوزن",
        "medication": "اسم دواء أو جرعته",
        "name": "اسم",
        "frequency": "عدد المرات",
        "duration": "مدة زمنية (ساعات أو دقائق أو أيام…)",
        "time_of_day": "ساعة من اليوم (مثلاً وقت النوم أو الاستيقاظ أو الأكل) لا مدة زمنية",
        "quantity": "كمية أو عدد",
        "yes_no": "نعم أو لا أو جواب ناقص",
        "choice": "اختيار أحد خيارات السؤال نفسه",
    },
    "en": {
        "scale": "a number on that same scale",
        "age_body": "a number for age, height or weight",
        "medication": "the name or dose of a medicine",
        "name": "a name",
        "frequency": "a number of times",
        "duration": "a length of time (hours, minutes, days...)",
        "time_of_day": "a clock time (for example bedtime, waking time or a meal time), not a duration",
        "quantity": "an amount or a count",
        "yes_no": "yes, no or a partial answer",
        "choice": "a pick from the options in that same question",
    },
}

_HINT: Final[dict] = {
    "fa": (
        "[پاسخ_به_سؤال_تو] پیام کوتاه کاربر، پاسخِ همان سؤال آخر توست («{question}»). {meaning_line}"
        "آن را در بافت همان سؤال بخوان؛ از کاربر نخواه دوباره توضیح بدهد و حرفش را بازگو نکن. "
        "اگر پاسخ از نوعی غیر از آنچه پرسیدی است، همان را که آشکارا هست بپذیر (مثلاً ساعت به‌جای مدت) و جلو برو. "
        "فقط اگر دو برداشت به دو توصیه‌ی متفاوت می‌رسد، یک بار و کوتاه روشن‌گر بپرس؛ وگرنه پاسخ را بپذیر و قدم بعدی یا سؤال تازه‌ی لازم را بده."
    ),
    "ar": (
        "[جواب_سؤالك] رسالة المستخدم القصيرة هي جواب سؤالك الأخير («{question}»). {meaning_line}"
        "اقرئيها في سياق ذلك السؤال؛ لا تطلبي منه الشرح مجدداً ولا تعيدي صياغة كلامه. "
        "وإن كان الجواب من نوع غير ما سألتِ فاقبليه على ما هو عليه بوضوح (مثلاً ساعة بدل مدة) وتابعي. "
        "اسألي سؤالاً توضيحياً قصيراً مرة واحدة فقط إذا أدى فهمان إلى نصيحتين مختلفتين؛ وإلا اقبلي الجواب وقدّمي الخطوة التالية أو السؤال الجديد اللازم."
    ),
    "en": (
        "[ANSWER_TO_YOUR_QUESTION] The user's short message is the ANSWER to your last question (\"{question}\"). {meaning_line}"
        "Read it in the context of that question; do not ask them to explain again and do not echo their words back. "
        "If the reply is of a different kind than you asked, accept it for what it obviously is (for example a clock time "
        "instead of a duration) and move on. Ask one short clarifying question, once, only if two readings would lead to "
        "different advice; otherwise accept the answer and give the next step or the one new question you need."
    ),
}

_MEANING_LEAD: Final[dict] = {
    "fa": "او احتمالاً گفته: ",
    "ar": "غالباً قصد: ",
    "en": "It is most likely ",
}

_SENTENCE = re.compile(r"(?<=[.!?؟\n])\s+|\n+")


def last_question(assistant_text: Optional[str]) -> Optional[str]:
    """The last question sentence of Sedi's previous reply, or None."""
    sentences = [s.strip() for s in _SENTENCE.split(assistant_text or "") if s and s.strip()]
    for sentence in reversed(sentences):
        if sentence.endswith(("?", "؟")):
            return sentence
    return None


def expected_answer_type(question: Optional[str]) -> Optional[str]:
    """One of scale / age_body / medication / name / frequency / duration / time_of_day / quantity / yes_no / choice."""
    folded = _fold(question or "")
    if not folded.strip():
        return None
    for name, pattern in _TYPES:
        if pattern.search(folded):
            return name
    return None


def binding_hint(assistant_text: Optional[str], user_message: Optional[str], language: Optional[str]) -> str:
    """The system hint for the model, or '' when it does not apply (no question asked, or the user wrote a long message)."""
    question = last_question(assistant_text)
    message = (user_message or "").strip()
    if not question or not message:
        return ""
    if len(message.split()) > _MAX_REPLY_WORDS or message.endswith(("?", "؟")):
        return ""
    lang = (language or "fa").split("-")[0].lower()
    lang = lang if lang in _HINT else "en"
    kind = expected_answer_type(question)
    meaning_line = ""
    if kind:
        meaning_line = _MEANING_LEAD[lang] + _MEANING[lang][kind] + ". "
    return _HINT[lang].format(question=question[:160], meaning_line=meaning_line)
