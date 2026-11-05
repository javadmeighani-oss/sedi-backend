"""R-066/R-067: conversation, not interrogation - the flow helpers.

Phone test 2026-11-05 (sleep): every Sedi reply restated what the user had just said («متوجه شدم؛ معمولاً ساعت ۱۱ تا ۱۲
شب می‌خوابی و صبح زود بیدار می‌شوی») and ended with a question, so the user felt questioned. Javad's decision: there is NO
hard cap on questions - the goal is a complete and correct conclusion; what matters is how Sedi explains and asks. So:

* ``strip_echo``      - deterministic: a reply never opens by repeating the user's own words (and bare acknowledgements
                         such as «متوجه شدم،» that only introduce a restatement are removed);
* ``advance_hint``    - a SOFT hint (never a strip): when two or more consecutive replies ended with a question, Sedi is
                         reminded to give her hypothesis + reason + a step unless a missing fact truly blocks the advice.

General (every topic, fa/ar/en), deterministic, no model call, fail-open (returns the input / '' on any problem).
"""

from __future__ import annotations

import re
from typing import Final, Optional, Sequence

_SENTENCE = re.compile(r"(?<=[.!?؟…])\s+|\n+")
_ECHO_THRESHOLD: Final[float] = 0.35
_MIN_ECHO_WORDS: Final[int] = 4

# A sentence that confirms a dose / medicine / quantity is kept even when it overlaps the user's words.
_KEEP_CONFIRMATION = re.compile(
    r"(?:\bmg\b|\bml\b|\bmcg\b|میلی\s*گرم|میلی‌گرم|قرص|دوز|دارو|آمپول|mg/|ملغ|جرعة|دواء)", re.I
)

# «متوجه شدم، جواد؛» / «I understand,» - an acknowledgement that only introduces a restatement.
_ACK_OPENER = re.compile(
    r"^\s*(?:متوجه\s+شدم|فهمیدم|می‌?\s*فهمم|مفهوم(?:\s+است)?|باشه|حله|"
    r"i\s+(?:understand|see|get\s+it)|got\s+it|understood|"
    r"فهمت|فهمتُ|أفهم|مفهوم)"
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


def asks_a_question(text: Optional[str]) -> bool:
    """True when the LAST sentence of a reply is a question."""
    parts = [p.strip() for p in _SENTENCE.split(text or "") if p and p.strip()]
    return bool(parts) and parts[-1].rstrip("\"'») ").endswith(("?", "؟"))


def strip_echo(reply: str, user_message: str, language: str = "fa") -> str:
    """R-066: never open by repeating the user's own words. Keeps every statement that adds something, never empties."""
    text = (reply or "").strip()
    message = (user_message or "").strip()
    if not text or not message:
        return text
    try:
        parts = [p.strip() for p in _SENTENCE.split(text) if p and p.strip()]
        if not parts:
            return text
        first = parts[0]
        stripped = _ACK_OPENER.sub("", first, count=1).strip()
        if not stripped and len(parts) > 1:
            # the whole first sentence was a bare acknowledgement («فهمیدم.» / "I understand."): drop it, then check the next
            return strip_echo(" ".join(parts[1:]), message, language)
        if stripped and _words(stripped) >= 2:
            first = stripped[:1].upper() + stripped[1:] if stripped[:1].isascii() else stripped
        rest = parts[1:]
        substantive_rest = [p for p in rest if _words(p) >= 3]
        is_question = first.rstrip("\"'») ").endswith(("?", "؟"))
        if (
            substantive_rest
            and not is_question
            and _words(first) >= _MIN_ECHO_WORDS
            and not _KEEP_CONFIRMATION.search(first)
            and _overlap(first, message) >= _ECHO_THRESHOLD
        ):
            return " ".join(rest).strip()
        return " ".join([first] + rest).strip() or text
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
