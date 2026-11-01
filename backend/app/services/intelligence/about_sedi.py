"""R-047: Sedi knows and states WHO she is and WHAT she can do (identity + capabilities), deterministically.

When the user asks "who are you / what can you do / can you send me notifications" the answer must be Sedi's locked
identity (the user's memory and dedicated health caretaker) and her real capabilities, never a generic
"I am an AI assistant" or a false "I cannot send reminders". Text lives in the copy catalog (R-043).

Arabic and Persian spellings are folded to one form on BOTH the message and the patterns (Codex review on PR #139), and a
message that names a day, a clock or a number is a real scheduling request - the reminder path owns it.
"""

from __future__ import annotations

import re
from typing import Final

from backend.app import sedi_copy

_MAX_WORDS: Final[int] = 14

_ABOUT_SOURCE = (
    r"("
    # fa
    r"تو\s+(?:دقیقا\s+|اصلا\s+)?کی\s*(?:هستی|هستی؟|ای)|تو\s+چی\s+هستی|خودت\s+رو\s+معرفی|خودتو\s+معرفی|معرفی\s+کن|"
    r"چه\s+کار\S*\s+(?:می\s*[‌ ]?تونی|می\s*[‌ ]?تونید|بلدی)|"
    r"چیکار\s+می\s*[‌ ]?تونی|چی\s+کار\s+می\s*[‌ ]?تونی|چه\s+کمکی\s+می\s*[‌ ]?تونی|"
    r"(?:توانایی|توانمندی|قابلیت|امکانات)\s*(?:ها)?\s*[‌ ]?(?:ت|هات|های\s*تو|هایت)|"
    r"کارت\s+چیه|وظیفه\s*[‌ ]?ت\s+چیه|به\s+چه\s+دردی\s+می\s*[‌ ]?خوری|"
    r"(?:می\s*[‌ ]?تونی|می\s*[‌ ]?شه)\s+(?:برام\s+|بهم\s+)?(?:نوتیف|اعلان|یادآور|یادآوری)|"
    r"(?:تو\s+)?(?:چه|چی)\s+(?:زمینه|حوزه)\s*(?:ها|های)?\s*(?:ای|هایی)?\s*(?:اطلاعات|دانش|تخصص)|"
    # ar
    r"من\s+أنت|ما\s+أنت|عرف\S*\s+بنفسك|ماذا\s+(?:تستطيع\S*|يمكنك|تقدم\S*|تفعل\S*)|"
    r"ما\s+(?:هي\s+)?(?:قدراتك|إمكانياتك|مهامك|وظيفتك)|"
    r"هل\s+(?:تستطيع\S*|يمكنك)\s+(?:أن\s+)?(?:ترسل\S*|إرسال)\s+(?:لي\s+)?(?:إشعار\S*|اشعار\S*|تذكير\S*)|"
    # en
    r"who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|what\s+do\s+you\s+do|introduce\s+yourself|"
    r"tell\s+me\s+about\s+yourself|your\s+(?:abilities|capabilities|features)|"
    r"can\s+you\s+(?:send|give)\s+(?:me\s+)?(?:a\s+)?(?:notification|reminder|alert)s?"
    r")"
)

_FOLD_PAIRS = (
    ("ي", "ی"),  # Arabic yeh -> Persian yeh
    ("ى", "ی"),  # alef maksura -> Persian yeh
    ("ك", "ک"),  # Arabic kaf -> Persian kaf
    ("أ", "ا"),  # alef + hamza above -> alef
    ("إ", "ا"),  # alef + hamza below -> alef
    ("آ", "ا"),  # alef madda -> alef
    ("‌", " "),  # half-space -> space
)


def _fold(text: str) -> str:
    """Arabic and Persian spellings meet in one form; diacritics (tanween, fatha...) are dropped."""
    out = text or ""
    for a, b in _FOLD_PAIRS:
        out = out.replace(a, b)
    return re.sub("[ً-ْ]", "", out)


_ABOUT = re.compile(_fold(_ABOUT_SOURCE), re.I)

# A real scheduling request (a day, a clock, a number) is NOT a question about Sedi: the reminder path owns it.
_SCHEDULE_HINT = re.compile(
    r"[0-9۰-۹٠-٩]|فردا|امروز|امشب|ساعت|tomorrow|tonight|today|\bat\b|\bin \d|غدا|غد|الليل|اليوم",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", _fold(text)).strip()


def is_about_sedi_question(message: str) -> bool:
    """True for a short, direct question about Sedi herself (identity / abilities / notifications)."""
    text = _norm(message)
    if not text or len(text.split()) > _MAX_WORDS:
        return False
    if _SCHEDULE_HINT.search(text):
        return False
    return bool(_ABOUT.search(text))


def about_sedi_message(language: str) -> str:
    lang = (language or "fa").split("-")[0].lower()
    return sedi_copy.t("about.sedi", lang if lang in ("fa", "ar", "en") else "en")
