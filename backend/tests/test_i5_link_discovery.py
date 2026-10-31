"""R-044 step 1: controlled link discovery finds new pages ONLY inside reviewed safety lanes.

No network: hub fetch and robots.txt are injected fakes. A found link is admitted only when it stays in the source's
URL patterns, is not a crisis / medication / chrome page, resolves to an entity the source is authorised for (D23 for
psychology), robots allows it and the budget is not spent. Flag OFF = nothing discovered and nothing stored is fetched.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from urllib import robotparser

import pytest

from backend.app.services.i5 import link_discovery as ld
from backend.app.services.i5.adapters.base import AdapterFrameworkError
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    _d23_mh_edu_content_blocked,
    resolve_specialized_entity_from_url,
)
from backend.app.services.i5.trusted_source_manifest import active_manifest_rows, manifest_row_for_key

NHS = "https://www.nhs.uk"
EMM_HUB = NHS + "/every-mind-matters/lifes-challenges/"
COND_HUB = NHS + "/mental-health/conditions/"
HUB_HTML = f"""
<html><body><header><a href="/every-mind-matters/accessibility/">Accessibility</a></header><main>
<a href="/every-mind-matters/lifes-challenges/money-worries-mental-health/">Money worries</a>
<a href="{NHS}/every-mind-matters/lifes-challenges/life-changes/?utm=x#top">Life changes</a>
<a href="/every-mind-matters/lifes-challenges/life-changes/">Life changes again</a>
<a href="/every-mind-matters/urgent-support/">Urgent support</a>
<a href="/mental-health/conditions/psychosis/">Psychosis</a>
<a href="/every-mind-matters/lifes-challenges/loneliness/">Loneliness (already a manifest URL)</a>
<a href="/conditions/insomnia/">Insomnia (another source)</a>
<a href="https://example.org/every-mind-matters/x/">Other domain</a>
<a href="mailto:someone@nhs.uk">Mail</a>
<a href="/every-mind-matters/your-mind-plan-quiz/">Quiz</a>
</main></body></html>
"""
UK_ROUTE = (
    "Health anxiety means worrying a lot about your health. If you feel you cannot cope, call 999 or contact "
    "Samaritans on 116 123. Talking to someone you trust about your worries and anxiety can help you feel calmer."
)


def _row():
    return copy.deepcopy(manifest_row_for_key("nhs_uk_mental_health"))


def _robots(disallow: tuple[str, ...] = ()) -> robotparser.RobotFileParser:
    parser = robotparser.RobotFileParser()
    parser.parse(["User-agent: *"] + [f"Disallow: {p}" for p in disallow])
    return parser


def _fetch(pages: dict[str, tuple[int, str, str]]):
    calls: list[str] = []

    def fetch(url: str, domain: str):
        calls.append(url)
        status, ctype, html = pages.get(url, (404, "text/html", ""))
        return status, ctype, html.encode("utf-8"), url

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def _known(row) -> set[str]:
    return {ld.url_key(u) for u in [row["exact_url"], *row["additional_urls"]]}


def _discover(row, pages, *, budget=10, robots=None):
    return ld.discover_for_row(
        row,
        known_keys=_known(row),
        budget=budget,
        fetch_page=_fetch(pages),
        load_robots=lambda host: robots if robots is not None else _robots(),
    )


# ---- pure rules -------------------------------------------------------------------------------------------------


def test_extract_links_absolute_https_without_query_fragment_and_deduplicated():
    links = ld.extract_links(HUB_HTML, EMM_HUB)
    assert NHS + "/every-mind-matters/lifes-challenges/life-changes/" in links
    assert links.count(NHS + "/every-mind-matters/lifes-challenges/life-changes/") == 1
    assert not any("?" in u or "#" in u or u.startswith("mailto") for u in links)
    assert ld.extract_links("<a href='", EMM_HUB) == []


@pytest.mark.parametrize(
    "url, reason",
    [
        (NHS + "/every-mind-matters/lifes-challenges/money-worries-mental-health/", "ADMITTED"),
        (NHS + "/mental-health/conditions/health-anxiety/", "ADMITTED"),
        (NHS + "/mental-health/conditions/psychosis/", "CONTENT_DENY"),
        (NHS + "/mental-health/feelings-symptoms-behaviours/behaviours/self-harm/", "CONTENT_DENY"),
        (NHS + "/every-mind-matters/urgent-support/", "CONTENT_DENY"),
        (NHS + "/mental-health/conditions/anorexia/", "CONTENT_DENY"),
        (NHS + "/every-mind-matters/privacy-policy/", "CHROME_DENY"),
        (NHS + "/conditions/insomnia/", "PATTERN_NOT_ALLOWED"),
        ("https://example.org/every-mind-matters/x/", "DOMAIN_NOT_ALLOWED"),
        ("http://www.nhs.uk/every-mind-matters/x/", "NOT_HTTPS"),
    ],
)
def test_admission_rules(url, reason):
    ok, got, entity = ld.admit_discovered_url(url, _row(), allowed_entities={"D23"})
    assert got == reason
    assert ok is (reason == "ADMITTED")
    if ok:
        assert entity == "D23"


def test_a_page_outside_every_reviewed_lane_is_never_admitted():
    row = _row()
    row["allowed_url_patterns"] = ["^https://www\\.nhs\\.uk/.*"]
    ok, reason, _ = ld.admit_discovered_url(NHS + "/live-well/exercise/running/", row, allowed_entities={"D23"})
    assert (ok, reason) == (False, "NO_SAFETY_LANE")


def test_a_lane_the_source_is_not_authorised_for_is_refused():
    url = NHS + "/every-mind-matters/lifes-challenges/life-changes/"
    assert ld.admit_discovered_url(url, _row(), allowed_entities={"D18"})[1] == "NO_SAFETY_LANE"


def test_already_known_pages_are_not_admitted_twice():
    url = NHS + "/every-mind-matters/lifes-challenges/loneliness"
    assert ld.admit_discovered_url(url, _row(), allowed_entities={"D23"}, known_keys=_known(_row()))[1] == "ALREADY_KNOWN"


def test_source_exclude_tokens_apply_on_top_of_the_fixed_lists():
    url = NHS + "/every-mind-matters/supporting-others/childrens-mental-health/"
    got = ld.admit_discovered_url(url, _row(), allowed_entities={"D23"}, exclude_url_tokens=("childrens",))
    assert got[1] == "SOURCE_EXCLUDE"


# ---- manifest contract ------------------------------------------------------------------------------------------


def test_manifest_discovery_hubs_are_inside_the_source_patterns_and_bounded():
    cfg = ld.discovery_config(_row())
    assert cfg is not None and len(cfg.hub_urls) == len(_row()["link_discovery"]["hub_urls"])
    assert cfg.max_new_urls_per_cycle <= ld.MAX_NEW_URLS_PER_RUN
    assert cfg.hub_urls[0].startswith(NHS + "/every-mind-matters/")  # everyday wellbeing first


def test_no_low_risk_source_declares_discovery_and_every_discovering_source_has_a_lane():
    for row in active_manifest_rows():
        if not row.get("link_discovery"):
            continue
        assert str(row.get("governed_low_risk_eligibility")).upper() not in {"YES", "TRUE", "1"}, row["source_key"]
        assert row.get("specialized_serving_eligibility"), row["source_key"]


def test_hub_outside_the_source_patterns_is_dropped_from_the_config():
    row = _row()
    row["link_discovery"] = {"hub_urls": [NHS + "/conditions/", "https://example.org/"]}
    assert ld.discovery_config(row) is None


def test_low_risk_source_never_discovers_even_if_configured():
    row = copy.deepcopy(manifest_row_for_key("nhs_uk_live_well"))
    row["link_discovery"] = {"hub_urls": [NHS + "/mental-health/self-help/"]}
    assert _discover(row, {}).status == "NO_SAFETY_LANE_FOR_SOURCE"


# ---- reading hubs -----------------------------------------------------------------------------------------------


def test_discover_admits_only_safe_new_pages_and_counts_the_rest():
    row = _row()
    row["link_discovery"] = {"hub_urls": [EMM_HUB]}
    result = _discover(row, {EMM_HUB: (200, "text/html; charset=utf-8", HUB_HTML)})
    urls = [a["url"] for a in result.admitted]
    assert urls == [
        NHS + "/every-mind-matters/lifes-challenges/money-worries-mental-health/",
        NHS + "/every-mind-matters/lifes-challenges/life-changes/",
    ]
    assert all(a["entity_id"] == "D23" and a["via"] == EMM_HUB for a in result.admitted)
    assert result.rejected["CONTENT_DENY"] == 2  # urgent-support, psychosis
    assert result.rejected["CHROME_DENY"] == 2  # accessibility, quiz
    assert result.rejected["ALREADY_KNOWN"] == 1
    assert result.status == "OK" and result.hubs_checked == 1


def test_budget_is_respected():
    row = _row()
    row["link_discovery"] = {"hub_urls": [EMM_HUB, COND_HUB]}
    fetch_pages = {EMM_HUB: (200, "text/html", HUB_HTML), COND_HUB: (200, "text/html", HUB_HTML)}
    assert len(_discover(row, fetch_pages, budget=1).admitted) == 1
    assert _discover(row, fetch_pages, budget=0).status == "BUDGET_EXHAUSTED"


def test_robots_disallow_and_unreachable_robots_fail_closed():
    row = _row()
    row["link_discovery"] = {"hub_urls": [EMM_HUB]}
    pages = {EMM_HUB: (200, "text/html", HUB_HTML)}
    blocked = _discover(row, pages, robots=_robots(("/every-mind-matters/lifes-challenges/money-worries",)))
    assert [a["url"] for a in blocked.admitted] == [NHS + "/every-mind-matters/lifes-challenges/life-changes/"]
    assert blocked.rejected["ROBOTS_DISALLOW"] == 1
    hub_blocked = _discover(row, pages, robots=_robots(("/every-mind-matters/",)))
    assert hub_blocked.admitted == [] and hub_blocked.rejected == {"HUB_ROBOTS_DISALLOW": 1}
    unavailable = ld.discover_for_row(
        row, known_keys=set(), budget=5, fetch_page=_fetch(pages), load_robots=lambda host: None
    )
    assert unavailable.status == "ROBOTS_UNAVAILABLE" and unavailable.admitted == []


def test_broken_or_non_html_hubs_are_counted_not_raised():
    row = _row()
    row["link_discovery"] = {"hub_urls": [EMM_HUB, COND_HUB]}

    def fetch(url, domain):
        if url == EMM_HUB:
            raise AdapterFrameworkError("TIMEOUT", "slow")
        return 200, "application/pdf", b"%PDF", url

    result = ld.discover_for_row(row, known_keys=set(), budget=5, fetch_page=fetch, load_robots=lambda h: _robots())
    assert result.admitted == []
    assert result.rejected == {"HUB_TIMEOUT": 1, "HUB_HTTP_200": 1}


# ---- stored discoveries -----------------------------------------------------------------------------------------


def _policy(*urls: str) -> dict:
    return {
        "controlled_urls": [_row()["exact_url"]],
        "discovered_urls": [{"url": u, "entity_id": "D23"} for u in urls],
    }


def test_flag_off_means_stored_discoveries_are_not_fetched(monkeypatch):
    monkeypatch.delenv(ld.LINK_DISCOVERY_ENV, raising=False)
    policy = _policy(NHS + "/every-mind-matters/lifes-challenges/life-changes/")
    assert ld.discovered_urls_for_cycle(_row(), policy) == []


def test_stored_discoveries_are_rechecked_against_todays_rules(monkeypatch):
    monkeypatch.setenv(ld.LINK_DISCOVERY_ENV, "true")
    good = NHS + "/every-mind-matters/lifes-challenges/life-changes/"
    policy = _policy(good, good + "", NHS + "/mental-health/conditions/psychosis/", _row()["exact_url"])
    assert ld.discovered_urls_for_cycle(_row(), policy) == [good]
    row = _row()
    row.pop("link_discovery")
    assert ld.discovered_urls_for_cycle(row, policy) == []


def test_reactivation_keeps_discoveries():
    previous = json.dumps({"controlled_urls": ["a"], "discovered_urls": [{"url": "b"}], "link_discovery_last": {"x": 1}})
    merged = ld.merge_discovery_state({"controlled_urls": ["a", "c"]}, previous)
    assert merged == {"controlled_urls": ["a", "c"], "discovered_urls": [{"url": "b"}], "link_discovery_last": {"x": 1}}
    assert ld.merge_discovery_state({"controlled_urls": []}, "not json") == {"controlled_urls": []}


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._slug = None

    def filter(self, cond):
        self._slug = cond.right.value
        return self

    def one_or_none(self):
        return self._rows.get(self._slug)


class _Db:
    def __init__(self, rows):
        self.rows = rows
        self.flushed = False

    def query(self, model):
        return _Query(self.rows)

    def flush(self):
        self.flushed = True


def _models():
    from backend.app import models

    return models


def test_run_link_discovery_stores_admitted_urls_and_a_summary(monkeypatch):
    row = _row()
    monkeypatch.setattr(ld, "active_manifest_rows", lambda: [row])
    monkeypatch.setattr(ld, "_governed_profile_eligible", lambda db, models, key: True)
    ks = SimpleNamespace(
        slug="nhs_uk_mental_health",
        source_fetch_enabled=True,
        crawl_policy_json=json.dumps({"controlled_urls": [row["exact_url"], *row["additional_urls"]]}),
    )
    db = _Db({"nhs_uk_mental_health": ks})
    hubs = row["link_discovery"]["hub_urls"]
    report = ld.run_link_discovery(
        db,
        _models(),
        fetch_page=_fetch({hubs[0]: (200, "text/html", HUB_HTML)}),
        load_robots=lambda host: _robots(),
        max_new_urls_per_run=1,
    )
    policy = json.loads(ks.crawl_policy_json)
    assert report.admitted_total == 1 and db.flushed
    assert [e["url"] for e in policy["discovered_urls"]] == [
        NHS + "/every-mind-matters/lifes-challenges/money-worries-mental-health/"
    ]
    assert policy["link_discovery_last"]["admitted"] == 1
    assert policy["controlled_urls"][0] == row["exact_url"]


def test_inactive_source_is_reported_and_untouched(monkeypatch):
    row = _row()
    monkeypatch.setattr(ld, "active_manifest_rows", lambda: [row])
    ks = SimpleNamespace(slug="nhs_uk_mental_health", source_fetch_enabled=False, crawl_policy_json="{}")
    report = ld.run_link_discovery(_Db({"nhs_uk_mental_health": ks}), _models(), fetch_page=_fetch({}), load_robots=lambda h: _robots())
    assert report.sources == [ld.SourceDiscovery("nhs_uk_mental_health", "SOURCE_NOT_ACTIVE").summary()]
    assert ks.crawl_policy_json == "{}"


def test_a_suspended_governed_profile_is_not_discovered(monkeypatch):
    row = _row()
    monkeypatch.setattr(ld, "active_manifest_rows", lambda: [row])
    monkeypatch.setattr(ld, "_governed_profile_eligible", lambda db, models, key: False)
    ks = SimpleNamespace(slug="nhs_uk_mental_health", source_fetch_enabled=True, crawl_policy_json="{}")
    fetch = _fetch({})
    report = ld.run_link_discovery(_Db({"nhs_uk_mental_health": ks}), _models(), fetch_page=fetch, load_robots=lambda h: _robots())
    assert report.sources[0]["status"] == "SOURCE_NOT_ACTIVE" and fetch.calls == [] and ks.crawl_policy_json == "{}"


def test_both_activation_flags_gate_discovery_before_any_network(monkeypatch):
    monkeypatch.setenv(ld.LINK_DISCOVERY_ENV, "true")
    monkeypatch.setenv("SEDI_I5_MULTISOURCE_ENABLED", "true")
    called = []
    monkeypatch.setattr(ld, "run_link_discovery", lambda *a, **k: called.append(1))
    for weekly, activation in (("", ""), ("true", ""), ("", "true")):
        monkeypatch.setenv("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED", weekly)
        monkeypatch.setenv("SEDI_I5_SOURCE_ACTIVATION_ENABLED", activation)
        assert ld.maybe_run_link_discovery(object(), object()) is None
    assert called == []


def test_weekly_hook_is_off_by_default_and_never_raises(monkeypatch):
    monkeypatch.delenv(ld.LINK_DISCOVERY_ENV, raising=False)
    assert ld.maybe_run_link_discovery(object(), object()) is None
    monkeypatch.setenv(ld.LINK_DISCOVERY_ENV, "true")
    monkeypatch.setenv("SEDI_I5_MULTISOURCE_ENABLED", "true")
    monkeypatch.setenv("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED", "true")
    monkeypatch.setenv("SEDI_I5_SOURCE_ACTIVATION_ENABLED", "true")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(ld, "run_link_discovery", boom)
    assert ld.maybe_run_link_discovery(object(), object()) is None


# ---- D23 boundary on discovered pages ---------------------------------------------------------------------------


def test_discovered_d23_pages_get_the_crisis_route_check():
    url = NHS + "/mental-health/conditions/health-anxiety/"
    spec = resolve_specialized_entity_from_url(url)
    assert spec is not None and spec.entity_id == "D23"
    assert _d23_mh_edu_content_blocked(UK_ROUTE, spec, canonical_url=url) == (True, "MH_EDU_UK_CRISIS_ROUTE_BLOCK")


@pytest.mark.parametrize(
    "url",
    [
        NHS + "/mental-health/conditions/panic-disorder/",
        NHS + "/mental-health/conditions/panic-disorder",
        "https://www.nimh.nih.gov/health/topics/caring-for-your-mental-health",
        "https://www.cdc.gov/mental-health/about/index.html",
    ],
)
def test_pages_eligible_before_r044_are_not_re_judged(url):
    spec = resolve_specialized_entity_from_url(url)
    assert _d23_mh_edu_content_blocked(UK_ROUTE, spec, canonical_url=url) == (False, "")
