"""R-083 phase 2: whole open BOOKS as lane-less CANDIDATE sources, listed from the publisher's own sitemap (offline, fakes)."""
from __future__ import annotations

import copy
from urllib import robotparser

import pytest

from backend.app.services.i5 import link_discovery as ld
from backend.app.services.i5.governed_specialized_entity_eligibility import specialized_allowed_entities_for_source
from backend.app.services.i5.trusted_source_manifest import active_manifest_rows, manifest_row_for_key

BOOKS = ("openstax_anatomy_physiology_2e", "openstax_sociology_3e")
SITEMAP = "https://openstax.org/rex/sitemaps/anatomy-and-physiology-2e.xml"
BASE = "https://openstax.org/books/anatomy-and-physiology-2e/pages/"


def _sitemap_xml(n: int, extra: str = "") -> str:
    locs = "".join(f"<url><loc>{BASE}{i}-chapter-page</loc></url>" for i in range(1, n + 1))
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}{extra}</urlset>'


def _robots(disallow=()):
    p = robotparser.RobotFileParser()
    p.parse(["User-agent: *"] + [f"Disallow: {d}" for d in disallow])
    return p


def _fetch(xml: str, ctype="application/xml"):
    calls = []

    def fetch(url, domain):
        calls.append(url)
        return 200, ctype, xml.encode("utf-8"), url

    fetch.calls = calls
    return fetch


def _row():
    return copy.deepcopy(manifest_row_for_key("openstax_anatomy_physiology_2e"))


# ---- sitemap parsing ------------------------------------------------------------------------------------------------------
def test_sitemap_urls_are_absolute_https_without_query_fragment_and_deduplicated():
    xml = "<urlset><url><loc> https://openstax.org/a?x=1#f </loc></url><url><loc>https://openstax.org/a</loc></url><url><loc>http://openstax.org/b</loc></url><url><loc>/relative</loc></url></urlset>"
    assert ld.extract_sitemap_urls(xml, "https://openstax.org/s.xml") == ["https://openstax.org/a", "https://openstax.org/relative"]
    assert ld.extract_sitemap_urls("", "https://x") == [] and ld.extract_sitemap_urls("<loc>", "https://x") == []


@pytest.mark.parametrize(
    "url,ctype,expected",
    [(SITEMAP, "", True), ("https://x.org/hub", "application/xml", True), ("https://x.org/hub", "text/xml; charset=utf-8", True), ("https://x.org/hub", "text/html", False), ("https://x.org/hub/", "", False)],
)
def test_sitemap_hub_detection(url, ctype, expected):
    assert ld.is_sitemap_hub(url, ctype) is expected


# ---- config ceilings ---------------------------------------------------------------------------------------------------------
def test_book_sources_get_their_own_higher_ceilings_and_lane_sources_keep_the_old_ones():
    row = _row()
    row["link_discovery"]["max_new_urls_per_cycle"] = 9999
    row["link_discovery"]["max_discovered_urls"] = 9999
    cfg = ld.discovery_config(row)
    assert cfg.candidate_only is True
    assert cfg.max_new_urls_per_cycle == ld.MAX_BOOK_NEW_URLS_PER_CYCLE and cfg.max_discovered_urls == ld.MAX_BOOK_DISCOVERED_URLS
    lane = copy.deepcopy(row)
    lane["link_discovery"]["candidate_only"] = False
    lane_cfg = ld.discovery_config(lane)
    assert lane_cfg.candidate_only is False
    assert lane_cfg.max_new_urls_per_cycle == ld.MAX_NEW_URLS_PER_RUN and lane_cfg.max_discovered_urls == 200


def test_candidate_only_must_be_the_boolean_true():
    for bad in ("true", 1, "yes", None):
        row = _row()
        row["link_discovery"]["candidate_only"] = bad
        assert ld.discovery_config(row).candidate_only is False


# ---- admission ----------------------------------------------------------------------------------------------------------------
def test_candidate_only_admits_book_pages_without_a_lane_but_keeps_every_other_gate():
    row = _row()
    ok = lambda u, **k: ld.admit_discovered_url(u, row, allowed_entities=set(), candidate_only=True, **k)  # noqa: E731
    assert ok(BASE + "1-introduction") == (True, "ADMITTED", ld.CANDIDATE_ONLY_LANE)
    assert ok("http://openstax.org/books/anatomy-and-physiology-2e/pages/x")[:2] == (False, "NOT_HTTPS")
    assert ok("https://example.org/books/anatomy-and-physiology-2e/pages/x")[:2] == (False, "DOMAIN_NOT_ALLOWED")
    assert ok("https://openstax.org/books/psychology-2e/pages/x")[:2] == (False, "PATTERN_NOT_ALLOWED")
    assert ok(BASE + "9-emergency-and-suicide")[1] in {"CONTENT_DENY", "ADMITTED"}  # the fixed deny list still applies
    assert ok(BASE + "1-introduction", known_keys={ld.url_key(BASE + "1-introduction")})[:2] == (False, "ALREADY_KNOWN")


def test_without_the_flag_a_lane_less_page_is_still_rejected():
    ok, reason, _ = ld.admit_discovered_url(BASE + "1-introduction", _row(), allowed_entities=set())
    assert (ok, reason) == (False, "NO_SAFETY_LANE")


# ---- discovery from a sitemap -------------------------------------------------------------------------------------------------
def test_a_book_is_listed_from_its_sitemap_within_the_budget():
    row = _row()
    fetch = _fetch(_sitemap_xml(120))
    res = ld.discover_for_row(row, known_keys=set(), budget=60, fetch_page=fetch, load_robots=lambda h: _robots())
    assert res.status == "OK" and res.hubs_checked == 1 and len(res.admitted) == 60
    assert all(a["entity_id"] == ld.CANDIDATE_ONLY_LANE and a["via"] == SITEMAP for a in res.admitted)
    assert fetch.calls == [SITEMAP]  # only the sitemap is fetched during discovery


def test_the_sitemap_is_followed_when_the_server_says_xml_or_nothing():
    for ctype in ("application/xml", "text/xml", ""):
        res = ld.discover_for_row(_row(), known_keys=set(), budget=5, fetch_page=_fetch(_sitemap_xml(8), ctype), load_robots=lambda h: _robots())
        assert len(res.admitted) == 5, ctype


def test_robots_and_the_pattern_filter_the_sitemap_entries():
    xml = _sitemap_xml(3, extra="<url><loc>https://openstax.org/books/psychology-2e/pages/zzz</loc></url><url><loc>https://openstax.org/details/books/x</loc></url>")
    res = ld.discover_for_row(_row(), known_keys=set(), budget=50, fetch_page=_fetch(xml), load_robots=lambda h: _robots(("/books/anatomy-and-physiology-2e/pages/2-",)))
    urls = {a["url"] for a in res.admitted}
    assert BASE + "1-chapter-page" in urls and BASE + "3-chapter-page" in urls and BASE + "2-chapter-page" not in urls
    assert res.rejected.get("ROBOTS_DISALLOW") == 1 and res.rejected.get("PATTERN_NOT_ALLOWED", 0) >= 2


def test_unreachable_robots_skip_the_source_fail_closed():
    res = ld.discover_for_row(_row(), known_keys=set(), budget=5, fetch_page=_fetch(_sitemap_xml(3)), load_robots=lambda h: None)
    assert res.status == "ROBOTS_UNAVAILABLE" and res.admitted == []


def test_a_lane_source_without_a_lane_still_does_not_discover():
    row = _row()
    row["link_discovery"]["candidate_only"] = False
    res = ld.discover_for_row(row, known_keys=set(), budget=5, fetch_page=_fetch(_sitemap_xml(3)), load_robots=lambda h: _robots())
    assert res.status == "NO_SAFETY_LANE_FOR_SOURCE"


def test_stored_book_discoveries_are_refetched_while_the_flag_is_on_and_dropped_when_it_is_off(monkeypatch):
    row = _row()
    policy = {"discovered_urls": [{"url": BASE + "1-introduction"}, {"url": "https://example.org/x"}]}
    monkeypatch.setattr(ld, "link_discovery_enabled", lambda: True)
    assert ld.discovered_urls_for_cycle(row, policy) == [BASE + "1-introduction"]
    monkeypatch.setattr(ld, "link_discovery_enabled", lambda: False)
    assert ld.discovered_urls_for_cycle(row, policy) == []


# ---- manifest guards (the structural promise: book candidates are never served) ------------------------------------------------
def test_the_two_book_rows_exist_and_are_active():
    keys = {r["source_key"] for r in active_manifest_rows()}
    assert set(BOOKS) <= keys


@pytest.mark.parametrize("key", BOOKS)
def test_a_candidate_only_row_holds_no_serving_lane_at_all(key):
    row = manifest_row_for_key(key)
    assert row["link_discovery"]["candidate_only"] is True
    assert str(row.get("governed_low_risk_eligibility") or "NO").upper() == "NO"
    assert not (row.get("specialized_serving_eligibility") or [])
    assert specialized_allowed_entities_for_source(key) == set()
    assert row["retention"] == "RAW_MINIMAL_EVIDENCE_ONLY" and row["robots_access_state"] == "ALLOWED"


def test_every_candidate_only_row_in_the_manifest_obeys_the_guard():
    for row in active_manifest_rows():
        cfg = row.get("link_discovery") or {}
        if cfg.get("candidate_only") is True:
            assert str(row.get("governed_low_risk_eligibility") or "NO").upper() == "NO", row["source_key"]
            assert not (row.get("specialized_serving_eligibility") or []), row["source_key"]


@pytest.mark.parametrize("key", BOOKS)
def test_the_sitemap_hub_is_inside_the_row_patterns_and_the_book_scope(key):
    row = manifest_row_for_key(key)
    cfg = ld.discovery_config(row)
    assert cfg is not None and len(cfg.hub_urls) == 1 and cfg.hub_urls[0].endswith(".xml")
    assert row["allowed_domain"] == "openstax.org"
    assert all(u.startswith("https://openstax.org/rex/sitemaps/") for u in cfg.hub_urls)


# ---- taxonomy (Codex P2): a book candidate is not filed under lifestyle/sleep ------------------------------------------------------
@pytest.mark.parametrize(
    "url,domain",
    [(BASE + "1-introduction", "anatomy_physiology"), ("https://openstax.org/books/introduction-sociology-3e/pages/5-1-x", "sociology_behavioral_science")],
)
def test_book_candidates_are_filed_under_their_declared_domain(url, domain):
    assert ld.candidate_taxonomy_for_url(url) == (domain, domain, "US")


@pytest.mark.parametrize("url", ["https://openstax.org/books/psychology-2e/pages/1-introduction", "https://www.nhs.uk/conditions/insomnia/", "https://example.org/x"])
def test_other_urls_have_no_book_taxonomy(url):
    assert ld.candidate_taxonomy_for_url(url) is None


def test_the_weekly_orchestrator_uses_the_book_taxonomy_before_the_lifestyle_fallback():
    import inspect

    from backend.app.services.i5 import weekly_orchestrator as wo

    src = inspect.getsource(wo)
    assert src.index("candidate_taxonomy_for_url(entity_url)") > src.index("resolve_wave02_coverage_from_url(entity_url)")


# ---- speed (Javad: a whole book in about 3 weeks) --------------------------------------------------------------------------------------
BOOK_PAGES = {"openstax_anatomy_physiology_2e": 336, "openstax_sociology_3e": 243}  # measured on production, 2026-11-08


@pytest.mark.parametrize("key,pages", sorted(BOOK_PAGES.items()))
def test_a_whole_book_is_listed_within_three_weekly_cycles(key, pages):
    import math

    cfg = ld.discovery_config(manifest_row_for_key(key))
    assert math.ceil(pages / cfg.max_new_urls_per_cycle) <= 3
    assert cfg.max_discovered_urls >= pages


def test_the_per_run_book_budget_covers_all_book_sources_at_their_cycle_rate():
    rows = [manifest_row_for_key(k) for k in BOOK_PAGES]
    assert sum(ld.discovery_config(r).max_new_urls_per_cycle for r in rows) <= ld.MAX_BOOK_URLS_PER_RUN

