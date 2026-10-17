"""Cross-language retrieval aid for the governed I5 knowledge plane (D-017).

The governed knowledge base is English (official sources). A Persian/Arabic question has no
verified concept label for most topics, so the same-language gate returned nothing and chat
refused. This module turns the question into a short English *search query* only. The query is
a non-authoritative retrieval hint: evidence still comes from governed, eligible knowledge units;
nothing the model writes here is ever served as knowledge.

Recipient is unchanged (OpenAI already handles the chat message). Kill switch:
SEDI_I5_QUERY_TRANSLATION_DISABLED=true.
"""
from __future__ import annotations

import os
import re
from collections import OrderedDict
from typing import Any, Optional

DISABLE_ENV = "SEDI_I5_QUERY_TRANSLATION_DISABLED"
MODEL_ENV = "SEDI_I5_QUERY_TRANSLATION_MODEL"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_QUERY_CHARS = 400
MAX_OUT_CHARS = 200
_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_CACHE_MAX = 512
_NON_LATIN = re.compile(r"[\u0600-\u06FF]")
_INSTRUCTIONS = (
    "You translate health questions (Persian, Arabic or other) into ENGLISH keyword search queries for "
    "official medical sources. The output MUST be in English using Latin letters only, never in the "
    "user's language. Output up to 3 alternative queries, one per line, from most specific to most "
    "general. Each query is the condition or topic name only (expand abbreviations), 1 to 3 words, no "
    "question words, no filler. No numbering, no quotes, no explanation. Do not answer the question."
    "\nExamples:\n"
    "Question: علائم و درمان ام اس چیست؟ -> multiple sclerosis\nneurological disease\n"
    "Question: برای اضطراب چه کنم؟ -> anxiety\nstress management\nmental health\n"
    "Question: چقدر باید ورزش کنم؟ -> physical activity\nexercise\n"
    "Question: ما هو مرض السكري؟ -> diabetes\nblood sugar\n"
)


def translation_enabled() -> bool:
    return os.getenv(DISABLE_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def needs_translation(query: str, language: Optional[str]) -> bool:
    lang = (language or "").lower()
    return bool(query and query.strip()) and not lang.startswith("en") and bool(_NON_LATIN.search(query))


def translate_query_alternatives(query: str, language: Optional[str], client: Any = None) -> list[str]:
    """Up to 3 English keyword queries (specific → general), [] when disabled/unavailable. Never raises."""
    if not translation_enabled() or not needs_translation(query, language):
        return []
    text = " ".join(query.split())[:MAX_QUERY_CHARS]
    if text in _CACHE:
        _CACHE.move_to_end(text)
        return list(_CACHE[text])
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        resp = client.chat.completions.create(
            model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
            messages=[{"role": "system", "content": _INSTRUCTIONS}, {"role": "user", "content": "Question: " + text + " ->"}],
            temperature=0,
            max_tokens=80,
        )
        raw = str(resp.choices[0].message.content or "")
    except Exception:  # noqa: BLE001 — retrieval aid only
        return []
    out: list[str] = []
    for line in raw.splitlines():
        cand = " ".join(re.sub(r'^[\s\-\*\d\.\)]+', "", line).replace('"', " ").split())[:MAX_OUT_CHARS]
        if len(cand) >= 3 and not _NON_LATIN.search(cand) and cand.lower() not in {c.lower() for c in out}:
            out.append(cand)
        if len(out) == 3:
            break
    if not out:
        return []
    _CACHE[text] = tuple(out)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return out


def translate_query_to_english(query: str, language: Optional[str], client: Any = None) -> Optional[str]:
    """First (most specific) English keyword query, or None."""
    alts = translate_query_alternatives(query, language, client)
    return alts[0] if alts else None
