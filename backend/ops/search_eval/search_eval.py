"""R-114 am.1 (PR-A2a): READ-ONLY measurement of the provider web search - how well it finds a suitable doctor in a place.

Run INSIDE the production container by the read-only ops workflow (``i5-search-eval-readonly.yml``):
    docker exec -i sedi-backend python - < backend/ops/search_eval/search_eval.py

What it does: a fixed golden set of (specialty x place) queries goes through the SAME functions the chat uses
(``directory_web_lookup.search_web_providers`` -> validate -> page verification -> ranking) and, for a few origins, the nearest-places
helper. Nothing is written (no DB, no env, no files); queries are synthetic structured fields (specialty + place), never user data.
Output: ``EVAL|...`` lines (JSON), one per query + an aggregate, so a before / after comparison (query wording, suitability filter,
model, ring chain) rests on numbers. A secret is never printed.

Environment knobs (all optional): ``SEDI_EVAL_MAX_QUERIES`` (default 24), ``SEDI_DIRECTORY_WEB_LOOKUP_MODEL`` (model under test),
``SEDI_EVAL_SET`` (label echoed in the output, e.g. baseline / after).
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from typing import Any, Callable, Optional

SPECIALTIES = ("گوارش", "داخلی", "پوست", "زنان", "ارتوپدی", "قلب", "گوش و حلق و بینی", "چشم", "اورولوژی", "مغز و اعصاب", "روانپزشکی", "غدد")
# (area, city, province) - the pilot place (Boumehen), its nearest towns/areas, a big-city neighbourhood and two controls
PLACES = (
    (None, "بومهن", "تهران"),
    (None, "پردیس", "تهران"),
    (None, "رودهن", "تهران"),
    ("تهرانپارس", "تهران", "تهران"),
    ("پیروزی", "تهران", "تهران"),
    (None, "شیراز", "فارس"),
)
NEARBY_ORIGINS = ("بومهن", "پردیس", "تهرانپارس")


def golden_set(limit: int) -> list[dict[str, Any]]:
    """Deterministic spread: every place meets several specialties; the pilot place gets the most."""
    rows: list[dict[str, Any]] = []
    for pi, (area, city, province) in enumerate(PLACES):
        for si, spec in enumerate(SPECIALTIES):
            if (si + pi * 2) % 3 == 0 or (pi == 0 and si < 6):
                rows.append({"specialty": spec, "area": area, "city": city, "province": province})
    return rows[: max(1, limit)]


def _norm(text: Any) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def suitable(row: dict[str, Any], specialty: str) -> bool:
    """The result is that specialty: the specialty field (or the name) carries the specialty's stem."""
    stem = _norm(specialty)[:4]
    return bool(stem) and (stem in _norm(row.get("specialty")) or stem in _norm(row.get("name")))


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def measure(item: dict[str, Any], search_fn: Callable[..., list], build_query_fn: Callable[..., Optional[str]]) -> dict[str, Any]:
    started = time.time()
    try:
        results = search_fn(entity="SPECIALIST", specialty=item["specialty"], city=item["city"], province=item["province"], area=item["area"], qualifiers=())
        error = None
    except Exception as exc:  # noqa: BLE001 - a failing query is a data point, not a crash
        results, error = [], type(exc).__name__
    elapsed = round(time.time() - started, 2)
    rows = [r for r in results if isinstance(r, dict)]
    return {
        "specialty": item["specialty"], "place": " ".join(x for x in (item["area"], item["city"]) if x),
        "query": build_query_fn("SPECIALIST", item["specialty"], item["city"], item["province"], area=item["area"]),
        "results": len(rows),
        "suitable": sum(1 for r in rows if suitable(r, item["specialty"])),
        "trusted": sum(1 for r in rows if r.get("trusted")),
        "page_read": sum(1 for r in rows if r.get("page_read")),
        "phone_verified": sum(1 for r in rows if r.get("phone_status") == "verified"),
        "address_verified": sum(1 for r in rows if r.get("address_verified")),
        "with_rating": sum(1 for r in rows if r.get("rating_avg")),
        "domains": sorted({_host(r.get("source_url", "")) for r in rows if r.get("source_url")}),
        "seconds": elapsed, "error": error,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    secs = [r["seconds"] for r in rows] or [0]
    domains: dict[str, int] = {}
    for r in rows:
        for d in r["domains"]:
            domains[d] = domains.get(d, 0) + 1
    return {
        "queries": len(rows),
        "pct_with_any_result": round(100 * sum(1 for r in rows if r["results"]) / n, 1),
        "pct_with_suitable_result": round(100 * sum(1 for r in rows if r["suitable"]) / n, 1),
        "avg_results": round(sum(r["results"] for r in rows) / n, 2),
        "pct_results_suitable": round(100 * sum(r["suitable"] for r in rows) / max(1, sum(r["results"] for r in rows)), 1),
        "pct_results_trusted_site": round(100 * sum(r["trusted"] for r in rows) / max(1, sum(r["results"] for r in rows)), 1),
        "pct_results_phone_verified": round(100 * sum(r["phone_verified"] for r in rows) / max(1, sum(r["results"] for r in rows)), 1),
        "pct_results_address_verified": round(100 * sum(r["address_verified"] for r in rows) / max(1, sum(r["results"] for r in rows)), 1),
        "errors": sum(1 for r in rows if r["error"]),
        "seconds_p50": round(statistics.median(secs), 2), "seconds_max": max(secs),
        "domains": dict(sorted(domains.items(), key=lambda kv: -kv[1])[:15]),
    }


def run(search_fn: Callable[..., list], build_query_fn: Callable[..., Optional[str]], nearby_fn: Optional[Callable[[str], list]],
        *, limit: int = 24, label: str = "baseline", model: str = "", out: Callable[[str], None] = print) -> dict[str, Any]:
    items = golden_set(limit)
    rows = []
    for item in items:
        row = measure(item, search_fn, build_query_fn)
        rows.append(row)
        out("EVAL|query|" + json.dumps(row, ensure_ascii=False))
    nearby: dict[str, Any] = {}
    if nearby_fn is not None:
        for origin in NEARBY_ORIGINS:
            try:
                nearby[origin] = list(nearby_fn(origin))
            except Exception as exc:  # noqa: BLE001
                nearby[origin] = "ERR:" + type(exc).__name__
        out("EVAL|nearby|" + json.dumps(nearby, ensure_ascii=False))
    agg = aggregate(rows)
    agg.update(set=label, model=model or "default")
    out("EVAL|aggregate|" + json.dumps(agg, ensure_ascii=False))
    out("EVAL|phase_search_eval|PASS")
    return agg


def main() -> int:
    from backend.app.services.i5 import directory_web_lookup as web
    from backend.app.services.i5 import nearby_places as nearby

    if not web.web_lookup_enabled():
        print("EVAL|web_lookup|DISABLED")
        return 3
    limit = int(os.getenv("SEDI_EVAL_MAX_QUERIES", "24") or 24)
    run(web.search_web_providers, web.build_query, nearby.nearby_places, limit=limit,
        label=os.getenv("SEDI_EVAL_SET", "baseline"), model=os.getenv(web.MODEL_ENV, web.DEFAULT_MODEL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
