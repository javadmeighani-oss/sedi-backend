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
    """Deterministic spread, INTERLEAVED by place so any prefix (the default 24) still covers every place including the controls;
    the pilot place gets the most specialties."""
    per_place: list[list[dict[str, Any]]] = []
    for pi, (area, city, province) in enumerate(PLACES):
        items = [
            {"specialty": spec, "area": area, "city": city, "province": province}
            for si, spec in enumerate(SPECIALTIES)
            if (si + pi * 2) % 3 == 0 or (pi == 0 and si < 6)
        ]
        per_place.append(items)
    rows: list[dict[str, Any]] = []
    for rank in range(max(len(x) for x in per_place)):
        for items in per_place:
            if rank < len(items):
                rows.append(items[rank])
    return rows[: max(1, limit)]


class FailureProbe:
    """The production search wrapper is fail-open (it returns [] on a provider error), so an outage looks like «no result». The probe wraps the
    provider call and records the exception classes before the wrapper swallows them."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        def inner(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(type(exc).__name__)
                raise

        return inner


def _norm(text: Any) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def suitable(row: dict[str, Any], specialty: str) -> bool:
    """The result is that specialty: the FIRST text (the result's specialty field, then its name) that names a specialty decides, by the
    lexicon's longest-match ``find_specialty``. Deliberately only ``find_specialty`` (present in EVERY image): the same yardstick measures the
    image BEFORE and AFTER the search polish (the chat's own filter, ``result_matches_specialty``, exists only after PR #213 - using it made the
    baseline on the older image crash)."""
    from backend.app.services.i5 import specialty_lexicon as lexicon

    for text in (row.get("specialty"), row.get("name")):
        found = lexicon.find_specialty(" ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in str(text or "")).split()))
        if found:
            return found == specialty
    return False


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def measure(item: dict[str, Any], search_fn: Callable[..., list], build_query_fn: Callable[..., Optional[str]], probe: Optional[FailureProbe] = None) -> dict[str, Any]:
    started = time.time()
    seen = len(probe.errors) if probe is not None else 0
    try:
        results = search_fn(entity="SPECIALIST", specialty=item["specialty"], city=item["city"], province=item["province"], area=item["area"], qualifiers=())
        error = None
    except Exception as exc:  # noqa: BLE001 - a failing query is a data point, not a crash
        results, error = [], type(exc).__name__
    if error is None and probe is not None and len(probe.errors) > seen:
        error = probe.errors[-1]  # swallowed by the fail-open wrapper: still a provider failure, not an empty answer
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
        *, limit: int = 24, label: str = "baseline", model: str = "", out: Callable[[str], None] = print, probe: Optional[FailureProbe] = None) -> dict[str, Any]:
    items = golden_set(limit)
    rows = []
    for item in items:
        row = measure(item, search_fn, build_query_fn, probe)
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
    # an eval where EVERY query failed at the provider says nothing about search quality: fail it instead of reporting a false baseline
    out("EVAL|phase_search_eval|" + ("FAIL" if rows and agg["errors"] == len(rows) else "PASS"))
    return agg


def _from_site(row: dict[str, Any], site: str) -> bool:
    host = _host(str(row.get("source_url") or ""))
    return host == site or host.endswith("." + site)


def run_sites(sites: list, per_site: int, search_fn: Callable[..., list], web_module: Any, *, out: Callable[[str], None] = print,
              probe: Optional[FailureProbe] = None) -> list:
    """R-114 am.1 (Javad: «these sites must be examined»): for EACH booking site the golden set is searched with the provider web_search tool
    RESTRICTED to that domain (``allowed_domains``, in this process only; the first wording only) and the result counts how many results truly came from that site, how many are the
    requested specialty, and how many had phone / address confirmed by the result's own page. Read-only, like the rest of the eval."""
    summary = []
    for site in sites:
        original_call = web_module._call_web_search

        def restricted_call(query: str, country: str, client: Any = None, _site=site, _inner=original_call) -> list:
            """The SAME provider call, but the web_search tool is restricted to ONE domain (the tool's own ``allowed_domains`` filter) - naming a
            site in the query text did not work (every site returned nothing)."""
            import json as _json

            if client is None:
                from openai import OpenAI

                client = OpenAI()
            resp = client.responses.create(
                model=os.getenv(web_module.MODEL_ENV, web_module.DEFAULT_MODEL),
                tools=[{"type": "web_search", "filters": {"allowed_domains": [_site]}}],
                instructions=web_module._instructions(country),
                input=query,
                text={"format": {"type": "json_schema", "name": "providers", "schema": web_module._SCHEMA, "strict": True}},
            )
            data = _json.loads(getattr(resp, "output_text", "") or "{}")
            return [r for r in (data.get("results") or []) if isinstance(r, dict)]

        web_module._call_web_search = probe.wrap(restricted_call) if probe is not None else restricted_call
        rows, errors, first_error = [], 0, ""
        try:
            for item in golden_set(per_site):
                seen = len(probe.errors) if probe is not None else 0
                try:
                    results = [r for r in search_fn(entity="SPECIALIST", specialty=item["specialty"], city=item["city"], province=item["province"],
                                                    area=item["area"], qualifiers=()) if isinstance(r, dict)]
                except Exception as exc:  # noqa: BLE001
                    results = []
                    errors += 1
                    first_error = first_error or (type(exc).__name__ + ": " + " ".join(str(exc).split())[:160])
                if probe is not None and len(probe.errors) > seen:
                    errors += 1
                rows.append((item, results))
        finally:
            web_module._call_web_search = original_call
        total = sum(len(r) for _, r in rows)
        mine = [(i, r) for i, res in rows for r in res if _from_site(r, site)]
        entry = {
            "site": site, "queries": len(rows), "errors": errors, "first_error": first_error, "results": total,
            "results_from_site": len(mine),
            "queries_with_site_result": len({id(i) for i, _ in mine}),
            "suitable_from_site": sum(1 for i, r in mine if suitable(r, i["specialty"])),
            "page_read_from_site": sum(1 for _, r in mine if r.get("page_read")),
            "phone_verified_from_site": sum(1 for _, r in mine if r.get("phone_status") == "verified"),
            "address_verified_from_site": sum(1 for _, r in mine if r.get("address_verified")),
            "with_rating_from_site": sum(1 for _, r in mine if r.get("rating_avg")),
            "trusted_flag": sum(1 for _, r in mine if r.get("trusted")),
            "other_domains": sorted({_host(str(r.get("source_url") or "")) for _, res in rows for r in res if not _from_site(r, site)})[:8],
        }
        summary.append(entry)
        out("EVAL|site|" + json.dumps(entry, ensure_ascii=False))
    return summary


def main() -> int:
    from backend.app.services.i5 import directory_web_lookup as web
    from backend.app.services.i5 import nearby_places as nearby

    if not web.web_lookup_enabled():
        print("EVAL|web_lookup|DISABLED")
        return 3
    limit = int(os.getenv("SEDI_EVAL_MAX_QUERIES", "24") or 24)
    probe = FailureProbe()
    web._call_web_search = probe.wrap(web._call_web_search)  # in this process only; nothing is written anywhere
    sites = [x.strip().lower() for x in (os.getenv("SEDI_EVAL_SITES", "") or "").split(",") if x.strip()]
    if sites:  # site mode: examine each named site on a small golden subset instead of the general run
        entries = run_sites(sites, limit, web.search_web_providers, web, probe=probe)
        print("EVAL|phase_search_eval|" + ("FAIL" if entries and all(e["errors"] >= e["queries"] for e in entries) else "PASS"))
        return 0
    agg = run(web.search_web_providers, web.build_query, nearby.nearby_places, limit=limit,
              label=os.getenv("SEDI_EVAL_SET", "baseline"), model=os.getenv(web.MODEL_ENV, web.DEFAULT_MODEL), probe=probe)
    return 0 if agg["errors"] < agg["queries"] else 4


if __name__ == "__main__":
    sys.exit(main())
