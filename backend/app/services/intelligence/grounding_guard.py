# backend.app.services.intelligence.grounding_guard
"""R-014 (2026-10-24): Sedi must never state a personal or family health fact that was not recorded or said.

A pure, deterministic post-generation filter (no I/O, no LLM). It removes a sentence of the model's reply when that
sentence asserts a relative's condition ("با توجه به اینکه مادرت دیابت داشته…") and either the relative or the
condition never appears in what the user said / what the user's memory supplied. First-person claims by Sedi about her
own relatives ("مادرم دیابت داره") are always removed — Sedi is an AI companion and has no such family history.
"""
from __future__ import annotations

import re
from typing import Iterable

_RELATIVE_TERMS = (
    "مادر", "پدر", "خواهر", "برادر", "همسر", "فرزند", "دختر", "پسر", "پدربزرگ", "مادربزرگ", "عمو", "عمه", "دایی",
    "خاله", "نوه", "خانواده", "والدین",
    "mother", "father", "sister", "brother", "wife", "husband", "parent", "grandmother", "grandfather", "family",
    "أم", "أب", "اخت", "أخت", "أخ", "زوج", "عائل",
)
_CONDITION_TERMS = (
    "دیابت", "قند", "فشار خون", "فشارخون", "سرطان", "قلب", "سکته", "کلسترول", "چاقی", "آلزایمر", "ام اس", "کلیه",
    "آسم", "صرع", "افسردگی", "بیماری",
    "diabet", "cancer", "hypertension", "blood pressure", "heart", "stroke", "cholesterol", "obesity", "alzheimer",
    "kidney", "asthma", "epilep", "depress", "illness", "disease",
    "سكري", "سرطان", "ضغط", "قلب", "مرض",
)
_CLAIM_VERB = re.compile(
    r"(?:داشت|داره|دارد|دارند|داشته|مبتلا|گرفته|گرفت|بوده|سابقه|\bhad\b|\bhas\b|\bhave\b|suffer|diagnosed|history|كان|لديه|عانى)",
    re.I,
)
_FIRST_PERSON_RELATIVE = re.compile(
    r"(?:مادرم|پدرم|خواهرم|برادرم|همسرم|مادر\s+من|پدر\s+من|\bmy\s+(?:mother|father|sister|brother|mom|dad)\b|أمي|أبي)",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟!\n])\s+|\n+")

_FALLBACK = {
    "fa": "برای اینکه دقیق‌ترین پیشنهاد را به تو بدهم، اول باید درباره‌ی وضعیت خودت بیشتر بدانم؛ برایم تعریف کن.",
    "en": "To give you the most accurate suggestion, I'd like to know more about your own situation first. Tell me more.",
    "ar": "لأقدّم لك أدق اقتراح أودّ أن أعرف عن وضعك أكثر أولاً؛ حدّثني.",
}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("‌", " ").split())


def _terms_in(text: str, terms: Iterable[str]) -> list[str]:
    return [t for t in terms if t in text]


def _is_unsupported(sentence: str, haystack: str) -> bool:
    s = _norm(sentence)
    if not _CLAIM_VERB.search(s):
        return False
    if _FIRST_PERSON_RELATIVE.search(s) and _terms_in(s, _CONDITION_TERMS):
        return True
    relatives = _terms_in(s, _RELATIVE_TERMS)
    conditions = _terms_in(s, _CONDITION_TERMS)
    if not relatives or not conditions:
        return False
    # The sentence ties a relative to a condition: both must be grounded in user-sourced text.
    if not any(r in haystack for r in relatives):
        return True
    return not any(c in haystack for c in conditions)


def strip_unsupported_personal_claims(reply: str, supported_text: str, language: str = "fa") -> str:
    """Drop sentences that assert unrecorded relative/condition facts; keep the rest verbatim."""
    text = (reply or "").strip()
    if not text:
        return text
    haystack = _norm(supported_text)
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    kept = [p for p in parts if not _is_unsupported(p, haystack)]
    if len(kept) == len(parts):
        return text
    if not kept:
        lang = (language or "fa").split("-")[0].lower()
        return _FALLBACK.get(lang, _FALLBACK["en"])
    return " ".join(k.strip() for k in kept)


# R-033 (Javad 2026-10-28): Sedi must not put herself on trial in front of the user - no "I am not a psychologist", "I cannot
# diagnose", "I am only an AI". These patterns (checked on normalised text) mark such a clause; the guard removes the
# clause and keeps the useful rest of the sentence.
_SELF_LIMIT = re.compile(
    r"(?:"
    r"(?:روان ?شناس|پزشک|دکتر|متخصص|مشاور|درمانگر)(?: انسانی| واقعی| حرفه ای)? نیستم|"
    r"(?:نمی ?تونم|نمیتونم|نمی ?توانم|نمیتوانم)(?: که)? (?:بیماری |اختلال )?تشخیص|"
    r"تشخیص (?:نمی ?دم|نمیدم|نمی ?دهم|نمیدهم)|"
    r"توانایی (?:تشخیص|درمان) ندارم|"
    # R-047: false "I cannot send notifications/reminders" (she CAN; the system delivers them).
    r"(?:نمی ?تونم|نمیتونم|نمی ?توانم|نمیتوانم)(?: که)? (?:برات |برایت |بهت |بهتون )?(?:نوتیف|اعلان|یادآور|یادآوری|پیام)(?: ?ی)? ?(?:بفرستم|بدم|بدهم|ارسال)|"
    r"\bi (?:cannot|can't|can not) (?:send|give) (?:you )?(?:any )?(?:notification|reminder|alert)s?\b|"
    r"لا أستطيع (?:أن )?(?:أرسل|إرسال) (?:لك )?(?:أي )?(?:إشعار|اشعار|تذكير)|"
    r"فقط (?:یه|یک) (?:هوش مصنوعی|برنامه|دستیار)|"
    r"جایگزین (?:پزشک|روان ?شناس|متخصص)(?: نیستم| نمی ?شم| نمی ?شوم)|"
    r"\bi(?:'m| am) not (?:a |an )?(?:human )?(?:psychologist|therapist|doctor|physician|counsel+or)\b|"
    r"\bi (?:cannot|can't|can not|don't|do not) (?:really )?diagnos|"
    r"\bi(?:'m| am) (?:just|only|merely) an? (?:ai|assistant|program|bot)\b|"
    r"\bas an ai\b|"
    r"لست (?:أخصائية|اخصائية|طبيبة|معالجة|مختصة)|"
    r"لا أستطيع (?:ال)?تشخيص|لا أشخّص|لا اشخص|"
    r"(?:أنا )?مجرد (?:ذكاء اصطناعي|برنامج)|"
    # R-051: no self-doubt about her memory or her ability to diagnose/treat, in any wording.
    r"حافظه ?(?:ام|م) (?:کامل|تضمینی|دقیق)(?: و (?:کامل|تضمینی|دقیق))? نیست|"
    r"(?:تشخیص|درمان)(?: پزشکی)?(?: یا [^.؛،]{1,40})? انجام (?:نمی ?دم|نمیدم|نمی ?دهم|نمیدهم)|"
    r"\bmy memory (?:is not|isn't) (?:complete|perfect|guaranteed)\b|"
    r"ذاكرتي (?:ليست|غير) (?:كاملة|مضمونة)"
    r")",
    re.I,
)
_CLAUSE_SPLIT = re.compile(r"\s*[؛;]\s*|\s+(?:اما|ولی|ولي|but|لكن|لكنني)\s+", re.I)
_END_PUNCT = ".!?؟!…"


def strip_self_limit_disclaimers(reply: str, language: str = "fa") -> str:
    """R-033: drop the clauses where Sedi talks about her own limits; keep the helpful rest verbatim. Never empties a reply."""
    text = (reply or "").strip()
    if not text:
        return text
    sep = "; " if (language or "fa").split("-")[0].lower() == "en" else "؛ "
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    out: list[str] = []
    changed = False
    for p in parts:
        if not _SELF_LIMIT.search(_norm(p)):
            out.append(p.strip())
            continue
        changed = True
        clauses = [c.strip() for c in _CLAUSE_SPLIT.split(p) if c and c.strip()]
        kept = [c for c in clauses if not _SELF_LIMIT.search(_norm(c))]
        if kept:
            s = sep.join(kept)
            tail = p.rstrip()[-1:] if p.rstrip() else ""
            if tail in _END_PUNCT and not s.endswith(tuple(_END_PUNCT)):
                s += tail
            out.append(s)
    if not changed or not out:
        return text
    return " ".join(out)


def limit_questions(reply: str, max_questions: int = 1) -> str:
    """R-020: Sedi talks like a friend, not an interviewer — keep at most ``max_questions`` question sentences
    (the first ones); every statement is kept. Deterministic, never empties a reply."""
    text = (reply or "").strip()
    if not text:
        return text
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    kept: list[str] = []
    asked = 0
    for p in parts:
        is_q = p.rstrip().endswith(("؟", "?"))
        if is_q:
            asked += 1
            if asked > max_questions:
                continue
        kept.append(p.strip())
    if not kept or len(kept) == len(parts):
        return text
    return " ".join(kept)


# R-049 (Javad 2026-11-01): Sedi is a permanent companion and a professional adviser - she speaks with certainty and
# gives her recommendation; she does not hedge every sentence with «اگه دوست داری / اگه خواستی / if you like» and does
# not close with an offer menu. The persona prompt says so; this guard removes what the model still produces.
_ZW = "\u200c"
_HEDGE_FA = (
    r"(?:اگه|اگر|اگ)\s+(?:دوست\s+داری|دوست\s+داشتی|خواستی|بخوای|بخواهی|می" + _ZW + r"?\s*خوای|می" + _ZW + r"?\s*خواهی|مایلی|مایل\s+باشی|تمایل\s+داری|حوصله\s+داشتی)"
)
_HEDGE_AR = r"(?:إن|إذا|لو)\s+(?:أحببت|احببت|رغبت|شئت|أردت|اردت|تحب|ترغب)|متى\s+(?:ما\s+)?(?:رغبت|شئت|أحببت)"
_HEDGE_EN = r"(?:if\s+you(?:'d|\s+would)?\s+(?:like|want|wish|prefer|feel\s+like)(?:\s+to)?|whenever\s+you(?:'re|\s+are)\s+ready|feel\s+free\s+to)"
_HEDGE_ANY = "(?:" + _HEDGE_FA + "|" + _HEDGE_AR + "|" + _HEDGE_EN + ")"
_HEDGE_PREFIX = re.compile(r"^\s*" + _HEDGE_ANY + r"\s*[,،:]?\s*", re.I)
_HEDGE_SUFFIX = re.compile(r"\s*[,،؛;]?\s*" + _HEDGE_ANY + r"\s*(?=[.!?؟…]*\s*$)", re.I)
_OFFER_Q = re.compile(
    r"^\s*(?:"
    r"(?:می" + _ZW + r"?\s*خوای|دوست\s+داری|می" + _ZW + r"?\s*خواهی|مایلی|بخوام|بگم|بدم)\b.*|"
    r"(?:would\s+you\s+like|do\s+you\s+want|shall\s+i|should\s+i|want\s+me\s+to|would\s+you\s+want)\b.*|"
    r"(?:هل\s+(?:تريد|تحب|ترغب|تود)|أتريد|هل\s+تحب)\b.*|"
    # R-051: closing menu questions in any register («… یا چه نوع کمکی می‌خواهی؟»)
    r".*(?:می" + _ZW + r"?\s*(?:خوای|خواهی)\s+(?:بدونی|بدانی))\b.*|"
    r".*\bیا\s+(?:چه|چی)\s+(?:نوع\s+)?(?:کمک|کار)\w*\s+.*?(?:می" + _ZW + r"?\s*(?:تونی|توانی|خوای|خواهی)|نیاز\s+داری|لازم\s+داری).*|"
    r".*(?:what|which)\s+(?:kind|type)\s+of\s+help\s+(?:can\s+you|could\s+you|would\s+you|do\s+you\s+(?:want|need)|should\s+i)\b.*|"
    r".*(?:أي|ما)\s+نوع\s+من\s+المساعدة\s+(?:تحتاج|تريد|تحب|يمكنك|تود)\b.*"
    r")$",
    re.I,
)
_PROTECT = re.compile(r"(?:متخصص|پزشک|دکتر|روانشناس|روان" + _ZW + r"شناس|specialist|doctor|psychologist|therapist|مختص|طبيب|أخصائي)", re.I)
_FIND_WORDS = re.compile(r"(?:پیدا|find|أجد|ابحث|أبحث)", re.I)


_FIRST_PERSON_OFFER = re.compile(
    r"(?:(?:می" + _ZW + r"?\s*تونم|می" + _ZW + r"?\s*دم|می" + _ZW + r"?\s*گم|می" + _ZW + r"?\s*نویسم|می" + _ZW + r"?\s*سازم|می" + _ZW + r"?\s*چینم)\b.*"
    r"|(?:بگم|بدم|بسازم|بنویسم|بفرستم|بچینم|توضیح\s+بدم)\s*$"
    r"|^(?:i\s+can|i'll|i\s+will|let\s+me|i\s+could)\b.*"
    r"|(?:يمكنني|أستطيع|سأ\w+)\b.*)",
    re.I,
)


def _is_protected_offer(sentence: str) -> bool:
    """The R-033 specialist offer («یه متخصص مناسب برات پیدا کنم؟») is kept - it is the consent question."""
    return bool(_PROTECT.search(sentence) and _FIND_WORDS.search(sentence))


# R-042: a model reply reaches this guard only when NO notification/reminder was created in this turn (the deterministic reminder
# path answers before the model). A sentence that claims «I sent you a notification right now» is therefore false and is removed.
_SEND_NOUN = re.compile(r"نوتیف|اعلان|پیام|یادآور|[اإ]شعار|اشعار|notification|reminder|\bping\b|\balert\b|تنبيه", re.IGNORECASE)
_SEND_DONE = re.compile(
    r"فرستادم|ارسال\s*کردم|فرستاده\s*شد|ارسال\s*شد|\b(?:i(?:'ve| have)?\s+)?sent\b|\bjust\s+sent\b|أرسلت|ارسلت|تم\s+إرسال|تم\s+ارسال",
    re.IGNORECASE,
)
_SEND_NOW = re.compile(r"همین\s*الان|الان|همین\s*حالا|حالا|\bright\s+now\b|\bjust\s+now\b|\bnow\b|للتو|الآن|الان", re.IGNORECASE)


# a DENIAL of a send («نفرستادم», «ارسال نکردم», «I did not send», «لم أرسل») is accurate and must stay
_SEND_NEGATED = re.compile(r"نفرستاد|نکردم|نکرده|نشد|نمی\s*[‌]?\s*فرست|\bnot\b|n't\b|\bnever\b|\bno\b|لم\s|لا\s|ما\s+أرسل|ما\s+ارسل", re.IGNORECASE)


def strip_unverified_send_claims(reply: str, language: str = "fa") -> str:
    """Remove «نوتیف … را همین الان فرستادم»-style claims (an immediate send that did not happen). Past references
    without «now» («this morning I sent the digest») and every other sentence stay. If nothing remains, one honest line asks
    for the time and topic."""
    text = (reply or "").strip()
    if not text:
        return text
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    kept = [
        p.strip()
        for p in parts
        if not (_SEND_NOUN.search(p) and _SEND_DONE.search(p) and _SEND_NOW.search(p) and not _SEND_NEGATED.search(p))
    ]
    if len(kept) == len(parts):
        return text
    if kept:
        return " ".join(kept)
    from backend.app import sedi_copy

    block = sedi_copy.by_lang("reminder.not_sent_say_when")
    return block.get(language) or block["en"]


def strip_hedging_offers(reply: str, language: str = "fa") -> str:
    """R-049: remove «اگه دوست داری / if you like / إن أحببت» softeners and trailing offer-menu questions
    («می‌خوای بیشتر بگم؟»). Statements and recommendations stay; the R-033 specialist offer stays; never empties a reply."""
    text = (reply or "").strip()
    if not text:
        return text
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    if not parts:
        return text
    out: list[str] = []
    changed = False
    for idx, p in enumerate(parts):
        s = p.strip()
        if _is_protected_offer(s):
            out.append(s)
            continue
        is_q = s.endswith(("؟", "?"))
        has_other = len(parts) > 1
        core = s.rstrip(" ؟?.!…")
        hedged = bool(_HEDGE_PREFIX.match(core)) or bool(_OFFER_Q.match(core))
        if is_q and hedged and has_other and idx > 0:
            changed = True  # an offer-menu question closing the reply: drop it
            continue
        new = s
        m = _HEDGE_PREFIX.match(new)
        if m:
            rest = new[m.end():].strip()
            if rest and has_other and idx > 0 and _FIRST_PERSON_OFFER.search(rest.rstrip(" .!…")):
                changed = True  # «اگه خواستی بیشتر توضیح می‌دم» is an offer menu, not content
                continue
            if rest:
                new = rest[:1].upper() + rest[1:] if rest[:1].isascii() else rest
        new2 = _HEDGE_SUFFIX.sub("", new).strip()
        if new2 and new2 != new:
            tail = s.rstrip()[-1:]
            if tail in ".!?؟…" and not new2.endswith(tuple(".!?؟…")):
                new2 += tail
            new = new2
        if new != s:
            changed = True
        out.append(new)
    if not changed or not out:
        return text
    return " ".join(out)


# R-051 (Javad 2026-11-04 phone test): a reply repeated a phrase and a sentence («... موضوع‌ها روشن‌تر بشن و قدم بعدی
# موضوع‌ها روشن‌تر بشن ...»). Deterministic clean-up: a sentence that already appeared is dropped, and a phrase of 3+
# words repeated back to back is written once. Never empties a reply.
_TOKEN_PUNCT = ".,،؛;!?؟…:«»\"()"


def _tok(token: str) -> str:
    return token.strip(_TOKEN_PUNCT).lower()


def _collapse_stutter(line: str) -> str:
    tokens = line.split(" ")
    changed = True
    while changed:
        changed = False
        n = len(tokens)
        for width in range(min(12, n // 2), 2, -1):
            for i in range(0, n - 2 * width + 1):
                first = [_tok(t) for t in tokens[i : i + width]]
                second = [_tok(t) for t in tokens[i + width : i + 2 * width]]
                if first == second and any(first):
                    del tokens[i + width : i + 2 * width]
                    changed = True
                    break
            if changed:
                break
    return " ".join(tokens)


def collapse_repetitions(reply: str) -> str:
    """R-051: drop a repeated sentence and a back-to-back repeated phrase (3+ words); everything else is kept."""
    text = (reply or "").strip()
    if not text:
        return text
    seen: set[str] = set()
    kept_lines: list[str] = []
    for line in text.split("\n"):
        parts = [p for p in _SENTENCE_SPLIT.split(line) if p and p.strip()]
        kept: list[str] = []
        for p in parts:
            key = _norm(p).rstrip(" ؟?.!…")
            if len(key.split()) >= 3 and key in seen:
                continue
            seen.add(key)
            kept.append(_collapse_stutter(p.strip()))
        kept_lines.append(" ".join(kept))
    out = "\n".join(kept_lines).strip()
    return out or text

