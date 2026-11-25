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
from typing import Any, Callable, Optional, Sequence

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

# R-114/R-116 (Javad: «what is ready for labs and clinics?»): the same measurement for the NON-doctor entities. The service is the
# specialty/service word the chat passes (None = a plain laboratory / hospital request).
ENTITY_SERVICES = {
    "LABORATORY": (None, "تشخیص طبی", "پاتولوژی"),
    "SPECIALTY_CENTER": ("فیزیوتراپی", "دندانپزشکی", "زنان", "پوست", "چشم", "روانشناسی"),
    "HOSPITAL": (None,),
}
# what a result of that kind calls itself (name or specialty text): the yardstick of «this is a laboratory / clinic / hospital»
KIND_WORDS = {
    "LABORATORY": ("آزمایشگاه", "ازمایشگاه", "لابراتوار", "پاتولوژی", "laborator"),
    "SPECIALTY_CENTER": ("کلینیک", "درمانگاه", "مرکز", "بیمارستان", "مطب", "clinic", "center", "centre"),
    "HOSPITAL": ("بیمارستان", "hospital"),
}


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


def golden_set_entity(entity: str, limit: int) -> list[dict[str, Any]]:
    """Laboratory / clinic / hospital golden set: service x place, interleaved by place like the doctor set so any prefix covers every place."""
    services = ENTITY_SERVICES.get(entity, (None,))
    per_place = [[{"specialty": svc, "area": area, "city": city, "province": province} for svc in services] for (area, city, province) in PLACES]
    rows: list[dict[str, Any]] = []
    for rank in range(max(len(x) for x in per_place)):
        for items in per_place:
            if rank < len(items):
                rows.append(items[rank])
    return rows[: max(1, limit)]


def kind_match(row: dict[str, Any], entity: str) -> bool:
    """The result calls itself that kind of place (laboratory / clinic or centre / hospital) in its name or specialty text."""
    text = _norm(f"{row.get('name') or ''} {row.get('specialty') or ''}")
    return any(_norm(w) in text for w in KIND_WORDS.get(entity, ()))


def service_match(row: dict[str, Any], service: Optional[str]) -> bool:
    return bool(service) and _norm(service) in _norm(f"{row.get('name') or ''} {row.get('specialty') or ''}")


class FailureProbe:
    """The production search wrapper is fail-open (it returns [] on a provider error), so an outage looks like «no result». The probe wraps the
    provider call and records the exception classes before the wrapper swallows them."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.messages: list[str] = []

    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        def inner(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                self.errors.append(type(exc).__name__)
                self.messages.append(" ".join(str(exc).split())[:160])
                raise

        return inner


def _norm(text: Any) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def suitable(row: dict[str, Any], specialty: str) -> bool:
    """The result is that specialty: the FIRST text (the result's specialty field, then its name) that names a specialty decides, by the
    lexicon's longest-match ``find_specialty``. Where the image has the chat's own filter (``result_matches_specialty``, PR #213) it is used, so the eval agrees with production; an older image
    falls back to ``find_specialty`` (present in EVERY image) so the BEFORE baseline does not crash."""
    from backend.app.services.i5 import specialty_lexicon as lexicon

    matcher = getattr(lexicon, "result_matches_specialty", None)
    if matcher is not None:  # newer images: the chat's own filter - a base specialty AND a subspecialty both count (Codex P2, PR 218)
        return bool(matcher(specialty, row.get("specialty"), row.get("name")))
    for text in (row.get("specialty"), row.get("name")):
        found = lexicon.find_specialty(" ".join("".join(ch if ch.isalnum() or ch.isspace() else " " for ch in str(text or "")).split()))
        if found:
            return found == specialty
    return False


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def measure(item: dict[str, Any], search_fn: Callable[..., list], build_query_fn: Callable[..., Optional[str]], probe: Optional[FailureProbe] = None,
            entity: str = "SPECIALIST") -> dict[str, Any]:
    started = time.time()
    seen = len(probe.errors) if probe is not None else 0
    try:
        results = search_fn(entity=entity, specialty=item["specialty"], city=item["city"], province=item["province"], area=item["area"], qualifiers=())
        error = None
    except Exception as exc:  # noqa: BLE001 - a failing query is a data point, not a crash
        results, error = [], type(exc).__name__
    if error is None and probe is not None and len(probe.errors) > seen:
        error = probe.errors[-1]  # swallowed by the fail-open wrapper: still a provider failure, not an empty answer
    elapsed = round(time.time() - started, 2)
    rows = [r for r in results if isinstance(r, dict)]
    return {
        "entity": entity, "specialty": item["specialty"], "place": " ".join(x for x in (item["area"], item["city"]) if x),
        "query": build_query_fn(entity, item["specialty"], item["city"], item["province"], area=item["area"]),
        "results": len(rows),
        "suitable": sum(1 for r in rows if (suitable(r, item["specialty"]) if entity == "SPECIALIST" else kind_match(r, entity))),
        "service_match": sum(1 for r in rows if service_match(r, item["specialty"])) if entity != "SPECIALIST" else 0,
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
        "results_service_match": sum(r.get("service_match", 0) for r in rows),
        "seconds_p50": round(statistics.median(secs), 2), "seconds_max": max(secs),
        "domains": dict(sorted(domains.items(), key=lambda kv: -kv[1])[:15]),
    }


def run(search_fn: Callable[..., list], build_query_fn: Callable[..., Optional[str]], nearby_fn: Optional[Callable[[str], list]],
        *, limit: int = 24, label: str = "baseline", model: str = "", out: Callable[[str], None] = print, probe: Optional[FailureProbe] = None,
        entity: str = "SPECIALIST") -> dict[str, Any]:
    items = golden_set(limit) if entity == "SPECIALIST" else golden_set_entity(entity, limit)
    if entity != "SPECIALIST":
        nearby_fn = None  # the nearby-places helper is about neighbourhoods, not about the kind of provider
    rows = []
    for item in items:
        row = measure(item, search_fn, build_query_fn, probe, entity)
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
    agg.update(set=label, model=model or "default", entity=entity)
    out("EVAL|aggregate|" + json.dumps(agg, ensure_ascii=False))
    # an eval where EVERY query failed at the provider says nothing about search quality: fail it instead of reporting a false baseline
    out("EVAL|phase_search_eval|" + ("FAIL" if rows and agg["errors"] == len(rows) else "PASS"))
    return agg


def _from_site(row: dict[str, Any], site: str) -> bool:
    host = _host(str(row.get("source_url") or ""))
    site = str(site).lower().removeprefix("www.")  # result hosts are www-stripped: the requested site must be too (Codex P2, PR 217)
    return host == site or host.endswith("." + site)


def run_sites(sites: list, per_site: int, search_fn: Callable[..., list], web_module: Any, *, out: Callable[[str], None] = print,
              probe: Optional[FailureProbe] = None) -> list:
    """R-114 am.1 (Javad: «these sites must be examined»): for EACH booking site the golden set is searched with the provider web_search tool
    RESTRICTED to that domain (``allowed_domains``, in this process only; the first wording only) and the result counts how many results truly came from that site, how many are the
    requested specialty, and how many had phone / address confirmed by the result's own page. Read-only, like the rest of the eval."""
    summary = []
    for site in [str(x).strip().lower().removeprefix("www.") for x in sites]:
        original_call = web_module._call_web_search
        getattr(web_module, "_cache", {}).clear()  # the lookup caches per QUERY text: another site must not be answered from the previous site's results
        getattr(web_module, "_usage", {}).clear()  # the process-local daily provider quota is per SITE here: an exhausted quota must not make later sites look empty

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
                    first_error = first_error or (probe.errors[-1] + ": " + probe.messages[-1])
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


def fetch_probe(urls: list, fetch_fn: Callable[[str], Any], *, out: Callable[[str], None] = print) -> list:
    """R-114 am.1: can Sedi's OWN page reader (``safe_fetch.fetch_page``: public https only, robots honoured, size/time capped) read these
    pages FROM THE SERVER, and what structured data do they expose? Reports per URL: ok / reason / status / bytes, JSON-LD types, the
    embedded Next.js data, and which useful fields exist - never the page content itself (counts and field names only)."""
    import re

    rows = []
    for url in urls:
        try:
            fr = fetch_fn(url)
        except Exception as exc:  # noqa: BLE001
            rows.append({"url": url, "ok": False, "reason": type(exc).__name__})
            out("EVAL|fetch|" + json.dumps(rows[-1], ensure_ascii=False))
            continue
        row: dict[str, Any] = {"url": url, "ok": bool(fr.ok), "reason": getattr(fr, "reason", ""), "status": getattr(fr, "status", 0),
                               "final_host": _host(getattr(fr, "url", "") or ""), "bytes": len(getattr(fr, "body", b"") or b"")}
        if fr.ok:
            html = fr.body.decode("utf-8", "replace")
            types: list = []
            for block in re.findall(r"<script[^>]*application/ld[+]json[^>]*>(.*?)</script>", html, re.S):
                try:
                    data = json.loads(block)
                except ValueError:
                    types.append("badjson")
                    continue
                for item in data if isinstance(data, list) else [data]:
                    if isinstance(item, dict):
                        types.append(item.get("@type"))
                        if item.get("@type") == "Physician":
                            row["physician_fields"] = sorted(k for k, v in item.items() if v not in (None, "", [], {}))[:24]
            row["jsonld_types"] = types[:6]
            row["next_data"] = "__NEXT_DATA__" in html
            try:  # a listing page's embedded result summary (counts only): helps tell «no doctors» from «the page came back without data»
                m = re.search(r"<script id=.__NEXT_DATA__.[^>]*>", html)
                queries = json.loads(html[m.end():][: html[m.end():].index("</script>")])["props"]["pageProps"]["dehydratedState"]["queries"] if m else []
                found = []
                for q in queries:
                    data = (q.get("state") or {}).get("data")
                    if isinstance(data, dict) and isinstance(data.get("search"), dict):
                        srch = data["search"]
                        found.append({"degraded": srch.get("degraded"), "total": srch.get("total"), "result_len": len(srch.get("result") or [])})
                if found:
                    row["search_summary"] = found[:3]
            except Exception:  # noqa: BLE001
                pass
            row["tel_like"] = bool(re.search(r"0[0-9]{2,3}[- ]?[0-9]{7,8}", html))
            row["visible_chars"] = len(re.sub(r"<[^>]+>", " ", html))
        rows.append(row)
        out("EVAL|fetch|" + json.dumps(row, ensure_ascii=False))
    return rows


READER_SPECIALTIES = ("گوارش", "پوست", "قلب", "ارتوپدی", "زنان", "اورولوژی", "غدد", "چشم")
READER_CITIES = ("تهران", "شیراز", "مشهد", "اصفهان", "کرج", "پردیس", "بومهن")


def readers_probe(mod: Any, specialties: Sequence = READER_SPECIALTIES, cities: Sequence = READER_CITIES, *, out: Callable[[str], None] = print,
                  delay: float = 0.0) -> dict:
    """R-114 am.1: run the site READERS (``i5/site_readers``: Doctoreto + Paziresh24 listing pages, parsed and ranked) for specialty x city and
    report per combination: which sites were read (ok / reason / count / seconds), how many providers, how many with reviews, the average of the
    top-five ratings, the number of top-five providers that have coordinates + a profile link. Counts only - never a name or an address."""
    rows = []
    first = True
    for spec in specialties:
        for city in cities:
            if delay and not first:
                time.sleep(delay)  # be a polite reader: a burst of requests can make a site answer with empty pages
            first = False
            started = time.time()
            report = mod.read_sites(spec, city)
            ranked = mod.rank(report.providers)
            top = mod.page(ranked, 1)
            rated = [p for p in top if p.rating is not None]
            row = {
                "specialty": spec, "city": city, "urls": len(mod.listing_urls(spec, city)),
                "sites": {k: {"ok": v["ok"], "reason": v["reason"], "count": v["count"], "seconds": v["seconds"]} for k, v in report.sites.items()},
                "providers": len(report.providers), "ranked": len(ranked), "top": len(top), "top_with_reviews": len(rated),
                "top_avg_rating": round(sum(p.rating for p in rated) / len(rated), 2) if rated else None,
                "top_review_counts": [p.rating_count for p in top], "top_with_coords": sum(1 for p in top if p.lat is not None),
                "top_with_link": sum(1 for p in top if str(p.url).startswith("https://")),
                "top_with_address": sum(1 for p in top if p.address), "nearby_listed": len(report.nearby), "seconds": round(time.time() - started, 2),
            }
            rows.append(row)
            out("EVAL|readers|" + json.dumps(row, ensure_ascii=False))
    combos = [r for r in rows if r["urls"]]
    agg = {
        "combos": len(rows), "combos_with_urls": len(combos),
        "pct_with_5": round(100 * sum(1 for r in combos if r["top"] >= 5) / (len(combos) or 1), 1),
        "pct_with_any": round(100 * sum(1 for r in combos if r["top"] >= 1) / (len(combos) or 1), 1),
        "pct_top_with_reviews": round(100 * sum(r["top_with_reviews"] for r in combos) / (sum(r["top"] for r in combos) or 1), 1),
        "pct_top_with_link": round(100 * sum(r["top_with_link"] for r in combos) / (sum(r["top"] for r in combos) or 1), 1),
        "pct_top_with_address": round(100 * sum(r["top_with_address"] for r in combos) / (sum(r["top"] for r in combos) or 1), 1),
        "pct_top_with_coords": round(100 * sum(r["top_with_coords"] for r in combos) / (sum(r["top"] for r in combos) or 1), 1),
        "site_failures": sum(1 for r in rows for v in r["sites"].values() if not v["ok"]),
        "site_reads_ok": sum(1 for r in rows for v in r["sites"].values() if v["ok"]),
        "seconds_p50": round(statistics.median([r["seconds"] for r in combos] or [0]), 2), "seconds_max": max([r["seconds"] for r in rows] or [0]),
    }
    out("EVAL|readers_aggregate|" + json.dumps(agg, ensure_ascii=False))
    return agg


def _load_readers(source_b64: str) -> Any:
    """The readers module from its source (sent next to the script): the running image may predate it. Same code as the repo file."""
    import base64
    import types

    mod = types.ModuleType("site_readers_eval")
    sys.modules["site_readers_eval"] = mod  # dataclasses look their module up here
    exec(compile(base64.b64decode(source_b64).decode("utf-8"), "site_readers.py", "exec"), mod.__dict__)  # noqa: S102 - the repo's own reviewed file
    return mod


def main() -> int:
    from backend.app.services.i5 import directory_web_lookup as web
    from backend.app.services.i5 import nearby_places as nearby

    if not web.web_lookup_enabled():
        print("EVAL|web_lookup|DISABLED")
        return 3
    limit = int(os.getenv("SEDI_EVAL_MAX_QUERIES", "24") or 24)
    probe = FailureProbe()
    web._call_web_search = probe.wrap(web._call_web_search)  # in this process only; nothing is written anywhere
    readers_src = os.getenv("SEDI_EVAL_READERS_SRC_B64", "")
    if readers_src:  # readers mode: the site readers on specialty x city, from the server (no model)
        agg = readers_probe(_load_readers(readers_src), delay=float(os.getenv("SEDI_EVAL_READERS_DELAY", "3") or 3))
        # URLs that could be built say nothing if EVERY read failed
        print("EVAL|phase_search_eval|" + ("PASS" if agg["combos_with_urls"] and agg["site_reads_ok"] else "FAIL"))
        return 0
    fetch_urls = [x.strip() for x in (os.getenv("SEDI_EVAL_FETCH_URLS", "") or "").split(",") if x.strip().startswith("https://")]
    if fetch_urls:  # fetch mode: can the server's own page reader read these pages? (no search, no model)
        from backend.app.services.i5 import safe_fetch

        fetch_probe(fetch_urls[:12], safe_fetch.fetch_page)
        print("EVAL|phase_search_eval|PASS")
        return 0
    sites = [x.strip().lower() for x in (os.getenv("SEDI_EVAL_SITES", "") or "").split(",") if x.strip()]
    if sites:  # site mode: examine each named site on a small golden subset instead of the general run
        entries = run_sites(sites, limit, web.search_web_providers, web, probe=probe)
        print("EVAL|phase_search_eval|" + ("FAIL" if entries and all(e["errors"] >= e["queries"] for e in entries) else "PASS"))
        return 0
    entity = (os.getenv("SEDI_EVAL_ENTITY") or "SPECIALIST").strip().upper()
    if entity not in ("SPECIALIST", *ENTITY_SERVICES):
        entity = "SPECIALIST"
    agg = run(web.search_web_providers, web.build_query, nearby.nearby_places, limit=limit, entity=entity,
              label=os.getenv("SEDI_EVAL_SET", "baseline"), model=(web.search_model() if hasattr(web, "search_model") else os.getenv(web.MODEL_ENV, web.DEFAULT_MODEL)), probe=probe)
    return 0 if agg["errors"] < agg["queries"] else 4


if __name__ == "__main__":
    sys.exit(main())
