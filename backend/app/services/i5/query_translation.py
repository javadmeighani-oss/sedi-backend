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
MAX_ALTERNATIVES = 4
_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_CACHE_MAX = 512
_NON_LATIN = re.compile(r"[\u0600-\u06FF]")
_INSTRUCTIONS = (
    "You translate health questions (Persian, Arabic or other) into ENGLISH keyword search queries for "
    "official medical sources. The output MUST be in English using Latin letters only, never in the "
    "user's language. Output up to 4 alternative queries, one per line. Each query is the condition or "
    "topic name only (1 to 3 words), no question words, no filler. Official sources name the same condition "
    "differently (US: amyotrophic lateral sclerosis; UK: motor neurone disease), so use the different names "
    "in different queries. If the question asks about a specific aspect (symptoms, treatment, care, "
    "prevention, diet, exercise), make the first two queries topic+aspect using two different names, then "
    "the topic alone using each name. If the question is general (explain, tell me about, complete "
    "explanation), output: the topic, then the topic with symptoms, with treatment, and with causes. "
    "No numbering, no quotes, no explanation. Do not answer the question."
    "\nExamples:\n"
    "Question: مراقبت و درمان ای ال اس -> motor neurone disease treatment\namyotrophic lateral sclerosis treatment\nmotor neurone disease\namyotrophic lateral sclerosis\n"
    "Question: علائم و درمان ام اس چیست؟ -> multiple sclerosis symptoms\nmultiple sclerosis treatment\nmultiple sclerosis\n"
    "Question: برای اضطراب چه کنم؟ -> anxiety\nstress management\nmental health\n"
    "Question: چقدر باید ورزش کنم؟ -> physical activity guidelines\nphysical activity\nexercise\n"
    "Question: ما هو مرض السكري؟ -> diabetes\nblood sugar\n"
)


def translation_enabled() -> bool:
    return os.getenv(DISABLE_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


def needs_translation(query: str, language: Optional[str]) -> bool:
    lang = (language or "").lower()
    return bool(query and query.strip()) and not lang.startswith("en") and bool(_NON_LATIN.search(query))


def _merge_additive(model: list[str], official: list[str]) -> list[str]:
    """Model's first two queries, then the lexicon's official names, then the rest of the model's; unique, at most 4."""
    out: list[str] = []
    seen: set[str] = set()
    for cand in model[:2] + official + model[2:]:
        if cand.lower() not in seen:
            seen.add(cand.lower())
            out.append(cand)
        if len(out) == MAX_ALTERNATIVES:
            break
    return out


def _bridge_only(text: str) -> list[str]:
    """Model unavailable / empty: the lexicon alone (with breadth padding). Not cached (the failure is transient)."""
    from backend.app.services.i5.health_query_bridge import health_bridge_alternatives

    return health_bridge_alternatives(text)


def translate_query_alternatives(query: str, language: Optional[str], client: Any = None) -> list[str]:
    """Up to 3 English keyword queries (specific → general), [] when disabled/unavailable. Never raises."""
    if not translation_enabled() or not needs_translation(query, language):
        return []
    text = " ".join(query.split())[:MAX_QUERY_CHARS]
    if text in _CACHE:
        _CACHE.move_to_end(text)
        return list(_CACHE[text])
    # R-044: clear psychology / wellbeing questions are bridged instantly and exactly (no model call, no 2-4 s wait).
    from backend.app.services.i5.psychology_query_bridge import bridge_alternatives, matches_any_topic

    bridged = bridge_alternatives(text)
    if bridged:
        return bridged
    # R-074 step 8a v2 (additive): the model keeps writing the broad queries (measured: replacing it lost fa coverage 0.63 -> 0.60);
    # the lexicon only ADDS the official English names it knows. A question that ALSO names a psychology topic stays model-only.
    official: list[str] = []
    if not matches_any_topic(text):
        from backend.app.services.i5.health_query_bridge import health_bridge_alternatives

        official = health_bridge_alternatives(text, pad=False)
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        resp = client.chat.completions.create(
            model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
            messages=[{"role": "system", "content": _INSTRUCTIONS}, {"role": "user", "content": "Question: " + text + " ->"}],
            temperature=0,
            max_tokens=100,
        )
        raw = str(resp.choices[0].message.content or "")
    except Exception:  # noqa: BLE001 — retrieval aid only
        return _bridge_only(text) if official else []
    out: list[str] = []
    for line in raw.splitlines():
        cand = " ".join(re.sub(r'^[\s\-\*\d\.\)]+', "", line).replace('"', " ").split())[:MAX_OUT_CHARS]
        if len(cand) >= 3 and not _NON_LATIN.search(cand) and cand.lower() not in {c.lower() for c in out}:
            out.append(cand)
        if len(out) == MAX_ALTERNATIVES:
            break
    if not out:
        return _bridge_only(text) if official else []
    if official:
        out = _merge_additive(out, official)
    _CACHE[text] = tuple(out)
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return out


def translate_query_to_english(query: str, language: Optional[str], client: Any = None) -> Optional[str]:
    """First (most specific) English keyword query, or None."""
    alts = translate_query_alternatives(query, language, client)
    return alts[0] if alts else None
