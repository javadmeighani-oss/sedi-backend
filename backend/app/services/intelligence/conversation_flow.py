"""R-066/R-067: conversation, not interrogation - the flow helpers.

Phone test 2026-11-05 (sleep): every Sedi reply restated what the user had just said («متوجه شدم؛ معمولاً ساعت ۱۱ تا ۱۲
شب می‌خوابی و صبح زود بیدار می‌شوی») and ended with a question, so the user felt questioned. Javad's decision: there is NO
hard cap on questions - the goal is a complete and correct conclusion; what matters is how Sedi explains and asks. So:

* ``strip_echo``      - deterministic: a reply never opens by repeating the user's own words (and bare acknowledgements
                         such as «متوجه شدم،» that only introduce a restatement are removed). It is deliberately CAUTIOUS
                         (Codex P1 on PR #142): a sentence is dropped only with positive evidence that it is a pure
                         restatement - never when it carries advice, a risk statement, a number the user did not give,
                         a dose/medicine, or when the message is about a severe symptom; only the opening span is edited
                         so paragraph breaks survive (Codex P2);
* ``advance_hint``    - a SOFT hint (never a strip): when two or more consecutive replies ended with a question, Sedi is
                         reminded to give her hypothesis + reason + a step unless a missing fact truly blocks the advice.

General (every topic, fa/ar/en), deterministic, no model call, fail-open (returns the input / '' on any problem).
"""

from __future__ import annotations

import re
from typing import Final, Optional, Sequence

_SENTENCE = re.compile(r"(?<=[.!?؟…])\s+|\n+")
_FIRST_BREAK = re.compile(r"(?<=[.!?؟…])[ \t]+|\n+")
_ECHO_THRESHOLD: Final[float] = 0.35
_MIN_ECHO_WORDS: Final[int] = 4
_NUMBER = re.compile(r"[0-9۰-۹٠-٩]+(?:[.,٫][0-9۰-۹٠-٩]+)?")

# A sentence that confirms a dose / medicine / quantity is kept even when it overlaps the user's words.
_KEEP_CONFIRMATION = re.compile(
    r"(?:\bmg\b|\bml\b|\bmcg\b|میلی\s*گرم|میلی‌گرم|قرص|دوز|دارو|آمپول|ملغ|جرعة|جرعه|دواء|\bdose\b|\bpill|\bmedic)", re.I
)

# Advice / risk / instruction markers: such a sentence is NEVER an echo (fa / ar / en).
_ADVICE_MARKERS = re.compile(
    r"(?:\b(?:require|requires|need|needs|should|must|avoid|stop|call|seek|urgent|urgently|emergency|danger|dangerous|serious|"
    r"immediately|risk|doctor|hospital|ambulance|warning|careful|dont|don't|do not)\b|"
    r"اورژانس|فوری|فوراً|فورا|خطر|جدی|باید|نباید|لازم|نکن|بپرهیز|پرهیز|مراقب|بیمارستان|پزشک|دکتر|آمبولانس|"
    r"طوارئ|عاجل|خطير|خطر|يجب|لا\s+ت|تجنب|انتبه|مستشفى|طبيب|إسعاف)",
    re.I,
)

# Severe symptoms / crises in the user's message: the guard stands aside completely (the I4 safety floor owns them).
_SEVERE = re.compile(
    r"(?:chest\s+pain|shortness\s+of\s+breath|can'?t\s+breathe|cannot\s+breathe|difficulty\s+breathing|bleeding|stroke|seizure|"
    r"faint|unconscious|overdose|suicid|kill\s+myself|self[-\s]?harm|allergic\s+reaction|heart\s+attack|"
    r"درد\s+قفسه|تنگی\s+نفس|نفس\s+نمی|خونریزی|سکته|تشنج|غش\s|بیهوش|خودکشی|خودکشي|آسیب\s+به\s+خود|مسمومیت|حمله\s+قلبی|"
    r"ألم\s+في\s+الصدر|ضيق\s+(?:في\s+)?التنفس|نزيف|سكتة|نوبة|إغماء|انتحار|إيذاء\s+النفس|جرعة\s+زائدة)",
    re.I,
)

# «متوجه شدم، جواد؛» / «I understand,» - an acknowledgement that only introduces a restatement.
_ACK_OPENER = re.compile(
    r"^\s*(?:متوجه\s+شدم|فهمیدم|می‌?\s*فهمم|مفهوم(?:\s+است)?|باشه|حله|"
    r"i\s+(?:understand|see|get\s+it)|got\s+it|understood|"
    r"فهمت|فهمتُ|أفهم)"
    r"\s*[,،;؛:.!\-–—]*\s*(?:[^\s,،;؛:.!]{2,16}\s*[,،;؛:]\s*)?",
    re.I,
)


def _norm(text: str) -> str:
    out = (text or "").lower().replace("‌", "").replace("ي", "ی").replace("ك", "ک").replace("ى", "ی")
    out = re.sub(r"[^\w\s]", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def _grams(text: str, size: int = 4) -> set:
    squeezed = _norm(text).replace(" ", "")
    return {squeezed[i : i + size] for i in range(max(0, len(squeezed) - size + 1))}


def _overlap(sentence: str, message: str) -> float:
    """Share of the sentence's 4-grams that also occur in the user's message (0..1)."""
    mine = _grams(sentence)
    if not mine:
        return 0.0
    return len(mine & _grams(message)) / len(mine)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _digits_key(text: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return text.translate(table)


_NUMBER_WORDS: Final[frozenset] = frozenset(
    {
        # fa
        "صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "ده", "یازده", "دوازده", "بیست", "سی", "چهل", "پنجاه",
        "صد", "هزار", "نیم", "نصف", "دوبار", "سهبار",
        # ar
        "واحد", "اثنان", "اثنين", "ثلاثة", "ثلاث", "أربعة", "اربعه", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة", "نصف",
        # en
        "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "twenty", "thirty",
        "forty", "fifty", "hundred", "thousand", "half", "twice",
    }
)


def _tokens(text: str) -> set:
    return set(_norm(text).split())


def _has_new_number(sentence: str, message: str) -> bool:
    """True when the sentence contains a number - written in digits or in words - the user did not give (a computation /
    a new fact, not a restatement)."""
    given = set(_NUMBER.findall(_digits_key(message)))
    if any(n not in given for n in _NUMBER.findall(_digits_key(sentence))):
        return True
    return bool((_tokens(sentence) & _NUMBER_WORDS) - _tokens(message))


def asks_a_question(text: Optional[str]) -> bool:
    """True when the LAST sentence of a reply is a question."""
    parts = [p.strip() for p in _SENTENCE.split(text or "") if p and p.strip()]
    return bool(parts) and parts[-1].rstrip("\"'») ").endswith(("?", "؟"))


def _is_pure_restatement(sentence: str, message: str) -> bool:
    """Positive evidence that ``sentence`` only repeats the user's words (and adds nothing)."""
    return (
        _words(sentence) >= _MIN_ECHO_WORDS
        and not sentence.rstrip("\"'») ").endswith(("?", "؟"))
        and not _KEEP_CONFIRMATION.search(sentence)
        and not _ADVICE_MARKERS.search(sentence)
        and not _SEVERE.search(sentence)
        and not _has_new_number(sentence, message)
        and _overlap(sentence, message) >= _ECHO_THRESHOLD
    )


def strip_echo(reply: str, user_message: str, language: str = "fa") -> str:
    """R-066: never open by repeating the user's own words. Cautious by design; edits only the opening span."""
    text = reply or ""
    message = (user_message or "").strip()
    if not text.strip() or not message:
        return text.strip() if text else text
    try:
        if _SEVERE.search(message):
            return text  # a severe-symptom message: the safety floor owns the answer; no cosmetic edits
        body = text.lstrip()
        lead = text[: len(text) - len(body)]
        match = _FIRST_BREAK.search(body)
        first, sep, rest = (body[: match.start()], body[match.start() : match.end()], body[match.end() :]) if match else (body, "", "")
        stripped = _ACK_OPENER.sub("", first, count=1).strip()
        if not stripped and rest.strip():
            # the whole first sentence was a bare acknowledgement («فهمیدم.» / "I understand."): drop it, then check the next
            return strip_echo(rest, message, language)
        if stripped and stripped != first.strip() and _words(stripped) >= 2:
            first = stripped[:1].upper() + stripped[1:] if stripped[:1].isascii() else stripped
        rest_sentences = [p for p in _SENTENCE.split(rest) if p and _words(p) >= 3]
        if rest_sentences and _is_pure_restatement(first, message):
            return rest.lstrip()
        rebuilt = lead + first + sep + rest
        return rebuilt if rebuilt.strip() else text
    except Exception:
        return text


_ADVANCE: Final[dict] = {
    "fa": (
        "[پیشروی_به_نتیجه] در چند پاسخ اخیر پیاپی سؤال پرسیده‌ای. هدف تو رسیدن به یک نتیجه‌ی کامل و درست است، نه گرفتن اطلاعات: "
        "مگر واقعیتِ ناشناخته‌ای توصیه را کاملاً متوقف کرده باشد، این بار حدس مشخص خودت را با دلیلش بگو (کاربر اصلاحش می‌کند)، "
        "یک توضیح کوتاه بده که وضع خودش را برایش روشن کند و یک قدم مشخص پیشنهاد کن. فقط اگر واقعاً لازم است، یک سؤال بپرس که "
        "جوابش توصیه را عوض می‌کند و دلیل پرسیدنش را همان‌جا بگو. حرف کاربر را بازگو نکن."
    ),
    "ar": (
        "[التقدم_نحو_الخلاصة] سألتِ في عدة ردود متتالية. هدفك الوصول إلى خلاصة كاملة وصحيحة لا جمع المعلومات: "
        "ما لم تكن معلومة ناقصة توقف النصيحة تماماً، قولي هذه المرة فرضيتك المحددة مع سببها (والمستخدم يصحّحها)، "
        "وأعطي شرحاً قصيراً يوضح له وضعه، واقترحي خطوة محددة. اسألي فقط إن كان ذلك لازماً فعلاً، بسؤال يغيّر جوابه النصيحة، "
        "وقولي سبب السؤال في الحال. لا تعيدي صياغة كلام المستخدم."
    ),
    "en": (
        "[ADVANCE_TO_A_CONCLUSION] Several of your recent replies in a row ended with a question. Your goal is a complete and "
        "correct conclusion, not collecting information: unless a missing fact truly blocks the advice, this time state your own "
        "specific hypothesis with its reason (the user will correct it), give one short explanation that makes their own "
        "situation clearer, and propose one concrete step. Ask only if it is really needed - one question whose answer changes "
        "the advice - and give the reason for asking right there. Do not restate what the user said."
    ),
}


def question_streak(assistant_texts: Sequence[str]) -> int:
    """How many of Sedi's latest replies IN A ROW ended with a question."""
    streak = 0
    for text in reversed(list(assistant_texts or ())):
        if asks_a_question(text):
            streak += 1
        else:
            break
    return streak


def advance_hint(assistant_texts: Sequence[str], language: Optional[str], *, threshold: int = 2) -> str:
    """The SOFT hint (R-067: never a cap, never a strip) once ``threshold`` replies in a row ended with a question."""
    try:
        if question_streak(assistant_texts) < threshold:
            return ""
        lang = (language or "fa").split("-")[0].lower()
        return _ADVANCE.get(lang, _ADVANCE["en"])
    except Exception:
        return ""
