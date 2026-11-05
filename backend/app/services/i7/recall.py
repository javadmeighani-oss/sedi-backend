"""R-054 / R-072: the raw text of every chat stays whole; this module only RECALLS words and concepts from it.

``recall_snippets`` finds the earlier days on which the user said something that bears on what they say NOW (their own words,
never a summary, never an invention), and ``build_recall_block`` turns the best few into one system block for the model so
Sedi "always remembers". It reads only what the I7 retention rules make visible (``query_eligible_raw``) and only with the
memory READ permission, skips the latest turns (they already reach the model as history) and is fail-open.

V1 is lexical (token overlap weighted by rarity, prefix-tolerant for Persian / Arabic / English word forms) over a bounded
scan of the user's own turns; a search index or vectors for pure concepts can be added later on the same interface.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

SCAN_CAP = 4000
SKIP_LATEST_TURNS = 10  # already sent to the model as recent history
MAX_QUERY_TOKENS = 8
MAX_SNIPPETS = 3
MAX_SNIPPET_CHARS = 220
_MIN_TOKEN = 3

_STOP = frozenset(
    """
    و در به از که این آن را با برای من تو ما شما او است بود شد شده هم یا اما ولی هر چه چرا چطور چی چیه نه بله آره مثل خیلی کمی یه یک می دارم دارد دارید
    باید میخوام میخواهم میشه می‌شه الان امروز دیروز فردا یادته یادت یادمه یاد بگو بگویید بود هست نیست کرد کردم کردی کنم کنی کن
    درباره دربارهی دوباره امشب دیشب حرف صحبت بزنیم بزن بگیم فقط همین چیزی چیز باز هنوز همیشه هیچ چقدر کجا کی
    the a an and or to of in on for with is are was were be been i you my me it this that do does did have has had how what why when about can
    could would should please tell know remember remind just so not no yes your our we they he she his her them there here
    في من على الى إلى عن مع هل ما هذا هذه انا أنا انت أنت لا نعم كان كانت كيف لماذا متى تذكر تتذكر اتذكر اخبرني قلت
    اليوم عاد مرة اخرى أخرى ايضا أيضا كل جدا
    """.split()
)


def _norm(text: Any) -> str:
    from backend.app.services.i7.memory_explorer import norm

    return norm(text)


def _fold_token(tok: str) -> str:
    """Arabic alef variants meet; the Arabic definite article «ال» does not hide the word («الصداع» = «صداع»)."""
    tok = tok.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    if tok.startswith("ال") and len(tok) > 4:
        tok = tok[2:]
    return tok


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in _norm(text).split():
        tok = _fold_token("".join(ch for ch in raw if ch.isalnum()))
        if len(tok) >= _MIN_TOKEN and tok not in _STOP and tok not in out:
            out.append(tok)
    return out


def _matches(query: str, doc_tokens: set) -> bool:
    if query in doc_tokens:
        return True
    if len(query) >= 4:
        return any(d.startswith(query) or (len(d) >= 4 and query.startswith(d)) for d in doc_tokens)
    return False


def _readable(db: Session, user_id: int) -> bool:
    try:
        from backend.app.services.i6.consent_service import PERM_READ, has_permission_readonly

        return bool(has_permission_readonly(db, user_id, PERM_READ))
    except Exception:
        return False


def _snippet(text: str) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= MAX_SNIPPET_CHARS else one[: MAX_SNIPPET_CHARS - 1].rstrip() + "…"


def recall_snippets(db: Session, user_id: int, message: str, *, limit: int = MAX_SNIPPETS) -> list[dict]:
    """[{day, text, score}] best first. Empty when the message carries no content word, the user has not allowed memory
    reading, nothing older matches, or anything goes wrong."""
    try:
        query = _tokens(message)[:MAX_QUERY_TOKENS]
        if not query or not _readable(db, user_id):
            return []
        from backend.app.services.i7.memory_explorer import _local_day, _zone
        from backend.app.services.i7.retention import query_eligible_raw

        rows = query_eligible_raw(db, user_id, limit=SCAN_CAP)  # newest first
        rows = list(rows)[SKIP_LATEST_TURNS:]
        if not rows:
            return []
        docs = [(row, set(_tokens(str(row.user_message or "")))) for row in rows]
        total = len(docs)
        weight: dict = {}
        for q in query:
            df = sum(1 for _row, toks in docs if _matches(q, toks))
            weight[q] = (math.log(1.0 + total / (1.0 + df)) * (0.6 + 0.1 * min(len(q), 8)), df)  # rarer and longer words say more
        scored: list = []
        for position, (row, toks) in enumerate(docs):  # position 0 = newest: recency breaks ties
            hit = [q for q in query if _matches(q, toks)]
            if not hit:
                continue
            strong_single = len(hit) == 1 and weight[hit[0]][1] <= 3 and len(hit[0]) >= 5
            if len(hit) < 2 and not strong_single:
                continue
            scored.append((sum(weight[q][0] for q in hit), -position, row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        zone, _tz = _zone(db, user_id)
        out: list[dict] = []
        seen_text: set = set()
        for score, _neg, row in scored:
            text = _snippet(row.user_message)
            key = _norm(text)
            if key in seen_text:
                continue
            seen_text.add(key)
            day = _local_day(row.created_at, zone)
            out.append({"day": day.isoformat() if day else "", "text": text, "score": round(float(score), 3)})
            if len(out) >= limit:
                break
        return out
    except Exception:
        logger.exception("[R-054] recall skipped")
        return []


def build_recall_block(db: Session, user_id: int, message: str, language: Optional[str] = None) -> Optional[str]:
    """One system block for the model, or None. The instruction text is for the model (English); the snippets are the user's own
    words in whatever language they used."""
    found = recall_snippets(db, user_id, message)
    if not found:
        return None
    lines = [
        "[MEMORY_RECALL]",
        "These are things the user told you on EARLIER days (their own words, dates in their local time). Use one only when it truly bears "
        "on what they say now; say it as something you remember, naturally and briefly, never quote it back word for word unless asked; "
        "never add facts beyond it; if it disagrees with what they say now, trust the present message and check gently.",
    ]
    lines.extend(f"- {item['day']}: {item['text']}" for item in found)
    return "\n".join(lines)
