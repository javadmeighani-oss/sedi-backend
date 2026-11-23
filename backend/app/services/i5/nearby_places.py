"""R-106 / R-114 am.1 (Javad): when nothing suitable is found in the user's place, Sedi looks in the NEAREST places as a RING CHAIN
(Boumehen -> Pardis -> the nearest part of Tehran ...), nearest first, and says so.

No hand-made neighbour list (Javad 2026-11-19). Geography comes from the model's knowledge - ONE short structured call per place (no user
data, only a place name), cached 7 days - but it is not trusted blindly (Javad E3, «the best solution»): the model returns approximate
coordinates, and THE CODE decides nearness: distances are computed (haversine), the candidates are ordered by them, coordinates outside
Iran or an impossible distance reject the candidate, and every ring has a distance cap (so «west Tehran» never comes before something
near, and nothing absurdly far is offered). Rings of up to three places: ring 1 = the nearest, ring 2 = the next, ring 3 = the next.
Every result found in a ring is then verified by the same governed pipeline in that place - nothing is invented.
Guarded by the web-lookup flag, the daily cap and the per-request budget; fail-open (empty list = the ordinary answer).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from typing import Any, Optional

from backend.app.services.i5 import directory_web_lookup as _web

logger = logging.getLogger(__name__)

MAX_PLACES = 3  # per ring
MAX_RINGS = 3
CANDIDATES = MAX_PLACES * MAX_RINGS
RING_MAX_KM = (25.0, 45.0, 70.0)  # distance cap per ring (km); a candidate beyond the cap of the ring it would fill is dropped
MIN_KM = 0.3  # the origin itself / a duplicate under another name
_IRAN_LAT = (24.0, 40.5)
_IRAN_LON = (43.5, 64.0)
_CACHE_TTL = 7 * 24 * 3600
_CACHE_MAX = 256
_cache: dict[str, tuple[float, list[tuple[str, Optional[float]]], bool, dict]] = {}
_COORD = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lat", "lon"],
    "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
}
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["origin", "places"],
    "properties": {
        "origin": _COORD,
        "places": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "city", "lat", "lon"],
                "properties": {"name": {"type": "string"}, "city": {"type": "string"}, "lat": {"type": "number"}, "lon": {"type": "number"}},
            },
        },
    },
}
_INSTRUCTIONS = (
    "You are a geography helper for Iran. Given a place (a city or a neighbourhood, in Persian), return its approximate centre (origin: lat, lon "
    "in WGS84 decimal degrees) and up to {n} DIFFERENT real places that are the closest to it, nearest first, each with its approximate centre "
    "(lat, lon) and the city it belongs to (city; for a town or city itself, its own name): neighbouring neighbourhoods when it is a neighbourhood, adjacent towns/cities (and the nearest neighbourhoods of a big city "
    "next to it) when it is a city or a small town. Use the common Persian names only. Never repeat the given place. No explanations."
)


def _key(place: str) -> str:
    return re.sub(r"[\s‌]+", "", (place or "").lower())


def _valid_coord(lat: Any, lon: Any) -> bool:
    try:
        return _IRAN_LAT[0] <= float(lat) <= _IRAN_LAT[1] and _IRAN_LON[0] <= float(lon) <= _IRAN_LON[1]
    except (TypeError, ValueError):
        return False


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _name_ok(raw: Any, origin: str, seen: set) -> Optional[str]:
    name = " ".join(str(raw or "").split()).strip(" ،,.«»\"'")
    if not (2 <= len(name) <= 30) or re.search(r"[0-9۰-۹/:@]|https?|www\.", name) or _key(name) in seen:
        return None
    return name


def _clean(names: Any, origin: str) -> list[str]:
    """The legacy shape (a plain list of names, trusted in the model's order): at most one ring."""
    out: list[str] = []
    seen = {_key(origin)}
    for raw in names if isinstance(names, list) else []:
        name = _name_ok(raw if not isinstance(raw, dict) else raw.get("name"), origin, seen)
        if name is None:
            continue
        seen.add(_key(name))
        out.append(name)
        if len(out) >= MAX_PLACES:
            break
    return out


def rank_places(data: Any, origin: str, cities: Optional[dict] = None) -> tuple[list[tuple[str, Optional[float]]], bool]:
    """([(name, km)], validated): the candidates ordered by COMPUTED distance from the model's origin coordinates; a candidate whose
    coordinates are outside Iran or equal the origin is rejected. Without usable origin coordinates the model's own order is kept
    (validated=False, km None) - never worse than before."""
    places = data.get("places") if isinstance(data, dict) else None
    places = places if isinstance(places, list) else []
    o = data.get("origin") if isinstance(data, dict) else None
    origin_ok = isinstance(o, dict) and _valid_coord(o.get("lat"), o.get("lon"))
    seen = {_key(origin)}
    ranked: list[tuple[str, Optional[float]]] = []
    if origin_ok:
        here = (float(o["lat"]), float(o["lon"]))
        scored: list[tuple[float, str]] = []
        for item in places:
            if not isinstance(item, dict) or not _valid_coord(item.get("lat"), item.get("lon")):
                continue
            name = _name_ok(item.get("name"), origin, seen)
            if name is None:
                continue
            km = haversine_km(here, (float(item["lat"]), float(item["lon"])))
            if km < MIN_KM:
                continue
            seen.add(_key(name))
            scored.append((km, name))
            if cities is not None and str(item.get("city") or "").strip():
                cities[_key(name)] = " ".join(str(item["city"]).split())[:30]
        scored.sort()
        ranked = [(n, round(km, 1)) for km, n in scored[:CANDIDATES]]
        return ranked, True
    for name in _clean([p.get("name") if isinstance(p, dict) else p for p in places], origin):
        ranked.append((name, None))
    return ranked, False


def build_rings(ranked: list[tuple[str, Optional[float]]], validated: bool) -> list[list[str]]:
    """Fill the rings in order of distance: three places per ring, a ring takes only places within its own distance cap (so the chain
    is monotonic: nothing far is offered before something near, and nothing beyond the last cap is offered at all)."""
    if not validated:
        return [[n for n, _ in ranked[:MAX_PLACES]]] if ranked else []
    rings: list[list[str]] = [[]]
    for name, km in ranked:
        while len(rings) <= MAX_RINGS:
            ring = len(rings) - 1
            if km is not None and km > RING_MAX_KM[ring]:
                if ring + 1 >= MAX_RINGS:
                    return [r for r in rings if r]
                rings.append([])
                continue
            if len(rings[ring]) >= MAX_PLACES:
                if ring + 1 >= MAX_RINGS:
                    return [r for r in rings if r]
                rings.append([])
                continue
            rings[ring].append(name)
            break
    return [r for r in rings if r]


def _ranked(place: str, client: Optional[Any]) -> tuple[list[tuple[str, Optional[float]]], bool]:
    place = " ".join((place or "").split())
    if not place or not _web.web_lookup_enabled():
        return [], False
    now = time.time()
    hit = _cache.get(_key(place))
    if hit and now - hit[0] < _CACHE_TTL:
        return list(hit[1]), hit[2]
    if not _web._take_quota() or not _web._take_request_budget():
        return [], False
    if client is None:
        from openai import OpenAI

        client = OpenAI()
    resp = client.responses.create(
        model=_web.search_model(),
        instructions=_INSTRUCTIONS.format(n=CANDIDATES),
        input=place,
        text={"format": {"type": "json_schema", "name": "places", "schema": _SCHEMA, "strict": True}},
        **_web.call_options(),
    )
    cities: dict = {}
    ranked, validated = rank_places(json.loads(getattr(resp, "output_text", "") or "{}"), place, cities)
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[_key(place)] = (now, ranked, validated, cities)
    return list(ranked), validated


def nearby_rings(place: str, *, client: Optional[Any] = None) -> list[list[str]]:
    """The nearest places to ``place`` as rings (nearest ring first, up to three places each); [] when disabled, over the cap, or on any error."""
    try:
        ranked, validated = _ranked(place, client)
        return build_rings(ranked, validated)
    except Exception:  # noqa: BLE001 - optional enrichment; the ordinary answer stays
        logger.exception("[R-114] nearby rings skipped")
        return []


def nearby_places(place: str, *, client: Optional[Any] = None) -> list[str]:
    """Up to three places nearest to ``place`` (the first ring); [] when disabled, over the cap, or on any error."""
    rings = nearby_rings(place, client=client)
    return list(rings[0]) if rings else []


def city_of(place: str, name: str) -> Optional[str]:
    """The city the geography says ``name`` (one of ``place``'s nearest places) belongs to, from the same cached answer; None when unknown."""
    try:
        hit = _cache.get(_key(" ".join((place or "").split())))
        return (hit[3] or {}).get(_key(name)) if hit else None
    except Exception:  # noqa: BLE001
        return None
