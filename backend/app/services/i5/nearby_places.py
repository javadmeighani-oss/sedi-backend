"""R-106 (Javad 2026-11-20): when nothing is found in the confirmed place, Sedi finds the provider in the NEAREST area and says so.

No hand-made neighbour list (Javad 2026-11-19): the nearest places come from the model's geographic knowledge, ONE short structured
call per place (no user data, no personal details - only a place name), cached and capped like the web lookup it serves; every result
is then verified by the same governed pipeline (page-verified phone/address, J3-b) in the nearby place - nothing is invented.
Guarded by the web-lookup flag and daily cap; fail-open (empty list = the ordinary answer).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional

from backend.app.services.i5 import directory_web_lookup as _web

logger = logging.getLogger(__name__)

MAX_PLACES = 3
_CACHE_TTL = 7 * 24 * 3600
_CACHE_MAX = 256
_cache: dict[str, tuple[float, list[str]]] = {}
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["places"],
    "properties": {"places": {"type": "array", "items": {"type": "string"}}},
}
_INSTRUCTIONS = (
    "You are a geography helper for Iran. Given a place (a city or a neighbourhood, in Persian), return up to {n} DIFFERENT real places "
    "that are the closest to it, nearest first: neighbouring neighbourhoods when it is a neighbourhood, adjacent towns/cities when it "
    "is a city or a small town. Use the common Persian names only. Never repeat the given place. No explanations."
)


def _key(place: str) -> str:
    return re.sub(r"[\s‌]+", "", (place or "").lower())


def _clean(names: Any, origin: str) -> list[str]:
    out: list[str] = []
    seen = {_key(origin)}
    for raw in names if isinstance(names, list) else []:
        name = " ".join(str(raw or "").split()).strip(" ،,.«»\"'")
        if not (2 <= len(name) <= 30) or re.search(r"[0-9۰-۹/:@]|https?|www\.", name) or _key(name) in seen:
            continue
        seen.add(_key(name))
        out.append(name)
        if len(out) >= MAX_PLACES:
            break
    return out


def nearby_places(place: str, *, client: Optional[Any] = None) -> list[str]:
    """Up to three places nearest to ``place`` (nearest first); [] when disabled, over the cap, or on any error."""
    try:
        place = " ".join((place or "").split())
        if not place or not _web.web_lookup_enabled():
            return []
        now = time.time()
        hit = _cache.get(_key(place))
        if hit and now - hit[0] < _CACHE_TTL:
            return list(hit[1])
        if not _web._take_quota():
            return []
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        resp = client.responses.create(
            model=os.getenv(_web.MODEL_ENV, _web.DEFAULT_MODEL),
            instructions=_INSTRUCTIONS.format(n=MAX_PLACES),
            input=place,
            text={"format": {"type": "json_schema", "name": "places", "schema": _SCHEMA, "strict": True}},
        )
        names = _clean(json.loads(getattr(resp, "output_text", "") or "{}").get("places"), place)
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[_key(place)] = (now, names)
        return list(names)
    except Exception:  # noqa: BLE001 - optional enrichment; the ordinary answer stays
        logger.exception("[R-106] nearby places skipped")
        return []
