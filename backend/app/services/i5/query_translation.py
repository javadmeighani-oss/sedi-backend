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
_CACHE: "OrderedDict[str, str]" = OrderedDict()
_CACHE_MAX = 512
_NON_LATIN = re.compile(r"[\u0600-\u06FF]")
_INSTRUCTIONS = (
    "Rewrite the user's health question as a short English search query for official medical sources "
    "(condition, treatment, care, prevention, nutrition, exercise or mental-health topic names in English). "
    "Output only the query, no explanation, no quotes. Do not answer the question."
)


def translation_enabled() -> bool:
    return os.getenv(DISABLE_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def needs_translation(query: str, language: Optional[str]) -> bool:
    lang = (language or "").lower()
    return bool(query and query.strip()) and not lang.startswith("en") and bool(_NON_LATIN.search(query))


def translate_query_to_english(query: str, language: Optional[str], client: Any = None) -> Optional[str]:
    """English search query, or None when disabled/unavailable. Never raises."""
    if not translation_enabled() or not needs_translation(query, language):
        return None
    text = " ".join(query.split())[:MAX_QUERY_CHARS]
    if text in _CACHE:
        _CACHE.move_to_end(text)
        return _CACHE[text]
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        resp = client.chat.completions.create(
            model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
            messages=[{"role": "system", "content": _INSTRUCTIONS}, {"role": "user", "content": text}],
            temperature=0,
            max_tokens=60,
        )
        out = " ".join(str(resp.choices[0].message.content or "").replace('"', " ").split())[:MAX_OUT_CHARS]
    except Exception:  # noqa: BLE001 — retrieval aid only
        return None
    if not out or _NON_LATIN.search(out) or len(out) < 3:
        return None
    _CACHE[text] = out
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return out
