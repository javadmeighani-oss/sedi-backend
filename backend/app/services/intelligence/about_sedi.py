"""R-047: Sedi knows and states WHO she is and WHAT she can do (identity + capabilities), deterministically.

When the user asks "who are you / what can you do / can you send me notifications" the answer must be Sedi's locked
identity (the user's memory and dedicated health caretaker) and her real capabilities, never a generic
"I am an AI assistant" or a false "I cannot send reminders". Text lives in the copy catalog (R-043).
"""

from __future__ import annotations

import re
from typing import Final

from backend.app import sedi_copy

_MAX_WORDS: Final[int] = 14

_ABOUT = re.compile(
    r"("
    # fa
    r"تو\s+(?:دقیقا\s+|اصلا\s+)?کی\s*(?:هستی|هستی؟|ای)|تو\s+چی\s+هستی|خودت\s+رو\s+معرفی|خودتو\s+معرفی|معرفی\s+کن|"
    r"چه\s+کار\S*\s+(?:می\s*[\u200c ]?تونی|می\s*[\u200c ]?تونید|بلدی)|"
    r"چیکار\s+می\s*[\u200c ]?تونی|چی\s+کار\s+می\s*[\u200c ]?تونی|چه\s+کمکی\s+می\s*[\u200c ]?تونی|"
    r"(?:توانایی|توانمندی|قابلیت|امکانات)\s*(?:ها)?\s*[\u200c ]?(?:ت|هات|های\s*تو|هایت)|"
    r"کارت\s+چیه|وظیفه\s*[\u200c ]?ت\s+چیه|به\s+چه\s+دردی\s+می\s*[\u200c ]?خوری|"
    r"(?:می\s*[\u200c ]?تونی|می\s*[\u200c ]?شه)\s+(?:برام\s+|بهم\s+)?(?:نوتیف|اعلان|یادآور|یادآوری)|"
    r"(?:تو\s+)?(?:چه|چی)\s+(?:زمینه|حوزه)\s*(?:ها|های)?\s*(?:ای|هایی)?\s*(?:اطلاعات|دانش|تخصص)|"
    # ar
    r"من\s+أنت|ما\s+أنت|عرفي\s+بنفسك|ماذا\s+(?:تستطيعين|يمكنك|تقدمين)|ما\s+(?:هي\s+)?(?:قدراتك|إمكانياتك|مهامك)|"
    r"هل\s+(?:تستطيعين|يمكنك)\s+(?:أن\s+)?(?:ترسلي|إرسال)\s+(?:لي\s+)?(?:إشعار|اشعار|تذكير)|"
    # en
    r"who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|what\s+do\s+you\s+do|introduce\s+yourself|"
    r"tell\s+me\s+about\s+yourself|your\s+(?:abilities|capabilities|features)|"
    r"can\s+you\s+(?:send|give)\s+(?:me\s+)?(?:a\s+)?(?:notification|reminder|alert)s?"
    r")",
    re.I,
)


def _norm(text: str) -> str:
    out = (text or "").replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return re.sub(r"\s+", " ", out).strip()


def is_about_sedi_question(message: str) -> bool:
    """True for a short, direct question about Sedi herself (identity / abilities / notifications)."""
    text = _norm(message)
    if not text or len(text.split()) > _MAX_WORDS:
        return False
    return bool(_ABOUT.search(text))


def about_sedi_message(language: str) -> str:
    lang = (language or "fa").split("-")[0].lower()
    return sedi_copy.t("about.sedi", lang if lang in ("fa", "ar", "en") else "en")
