"""R-114 am.1 (PR-A2a): the read-only search-eval harness measures the provider web search without side effects."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "ops" / "search_eval" / "search_eval.py"
WORKFLOW = ROOT / ".github" / "workflows" / "i5-search-eval-readonly.yml"


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("search_eval_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(name, specialty, **extra):
    base = {"name": name, "specialty": specialty, "source_url": f"https://www.paziresh24.com/dr/{name}", "trusted": True, "page_read": True,
            "phone_status": "verified", "address_verified": True, "rating_avg": 4.5}
    base.update(extra)
    return base


# --- the golden set ------------------------------------------------------------------------------------------------------------------------------------
def test_the_golden_set_is_deterministic_and_covers_the_pilot_place(ev):
    first, second = ev.golden_set(24), ev.golden_set(24)
    assert first == second and len(first) == 24
    pilot = [r for r in ev.golden_set(48) if r["city"] == "بومهن"]
    assert len(pilot) >= 6 and len([r for r in first if r["city"] == "بومهن"]) >= 4   # the pilot place gets the most specialties
    assert {r["city"] for r in first} == {"بومهن", "پردیس", "رودهن", "تهران", "شیراز"}   # the DEFAULT sample covers every place, controls included
    assert {r["city"] for r in ev.golden_set(6)} == {"بومهن", "پردیس", "رودهن", "تهران", "شیراز"}   # even a short prefix does
    assert {r["city"] for r in ev.golden_set(48)} >= {"بومهن", "پردیس", "رودهن", "تهران", "شیراز"}
    assert all(set(r) == {"specialty", "area", "city", "province"} for r in first)
    assert len(ev.golden_set(0)) == 1                        # never empty


def test_the_set_holds_only_synthetic_structured_fields(ev):
    blob = " ".join(str(v) for r in ev.golden_set(48) for v in r.values())
    assert not re.search(r"\d{4,}|@|http", blob)             # no phone / mail / link: a query is a specialty and a place


# --- suitability ------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("row,specialty,expected", [
    ({"specialty": "متخصص گوارش و کبد", "name": "دکتر الف"}, "گوارش", True),
    ({"specialty": "", "name": "دکتر گوارش علوی"}, "گوارش", True),
    ({"specialty": "متخصص کودکان", "name": "دکتر ب"}, "گوارش", False),
    ({"specialty": None, "name": None}, "گوارش", False),
])
def test_suitability_needs_the_specialty_stem(ev, row, specialty, expected):
    assert ev.suitable(row, specialty) is expected


# --- measuring ---------------------------------------------------------------------------------------------------------------------------------------
def test_measure_counts_what_the_search_returned(ev):
    def search(**k):
        assert k["entity"] == "SPECIALIST" and k["specialty"] == "گوارش"
        return [_row("a", "گوارش"), _row("b", "کودکان", trusted=False, phone_status="unchecked", address_verified=False, page_read=False)]

    out = ev.measure({"specialty": "گوارش", "area": None, "city": "بومهن", "province": "تهران"}, search, lambda *a, **k: "q")
    assert (out["results"], out["suitable"], out["trusted"], out["phone_verified"], out["address_verified"], out["page_read"]) == (2, 1, 1, 1, 1, 1)
    assert out["domains"] == ["paziresh24.com"] and out["error"] is None and out["query"] == "q"


def test_a_failing_query_is_a_data_point_not_a_crash(ev):
    def boom(**k):
        raise RuntimeError("network")

    out = ev.measure({"specialty": "پوست", "area": None, "city": "پردیس", "province": "تهران"}, boom, lambda *a, **k: None)
    assert out["error"] == "RuntimeError" and out["results"] == 0


def test_the_aggregate_reports_the_rates(ev):
    rows = [
        {"results": 2, "suitable": 1, "trusted": 2, "page_read": 2, "phone_verified": 1, "address_verified": 2, "domains": ["paziresh24.com"], "seconds": 3.0, "error": None},
        {"results": 0, "suitable": 0, "trusted": 0, "page_read": 0, "phone_verified": 0, "address_verified": 0, "domains": [], "seconds": 1.0, "error": None},
    ]
    agg = ev.aggregate(rows)
    assert agg["queries"] == 2 and agg["pct_with_any_result"] == 50.0 and agg["pct_with_suitable_result"] == 50.0
    assert agg["pct_results_suitable"] == 50.0 and agg["pct_results_phone_verified"] == 50.0 and agg["pct_results_address_verified"] == 100.0
    assert agg["domains"] == {"paziresh24.com": 1} and agg["seconds_max"] == 3.0


def test_run_prints_every_query_the_nearby_places_and_the_aggregate(ev):
    lines = []
    agg = ev.run(lambda **k: [_row("a", k["specialty"])], lambda *a, **k: "q", lambda origin: ["پردیس", "رودهن"], limit=3, label="baseline", model="m1", out=lines.append)
    kinds = [ln.split("|")[1] for ln in lines]
    assert kinds.count("query") == 3 and "nearby" in kinds and kinds[-2:] == ["aggregate", "phase_search_eval"]
    assert agg["set"] == "baseline" and agg["model"] == "m1" and agg["pct_with_suitable_result"] == 100.0
    assert "پردیس" in [ln for ln in lines if "|nearby|" in ln][0]


def test_a_failing_nearby_helper_does_not_stop_the_eval(ev):
    lines = []

    def nearby(origin):
        raise ValueError("x")

    ev.run(lambda **k: [], lambda *a, **k: None, nearby, limit=1, out=lines.append)
    assert any("ERR:ValueError" in ln for ln in lines) and lines[-1].endswith("PASS")


# --- the harness is read-only ---------------------------------------------------------------------------------------------------------------------
def test_the_script_has_no_write_path():
    text = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("open(", "os.environ[", "os.putenv", "subprocess", "shutil", "commit(", ".execute(", "INSERT ", "UPDATE ", "DELETE ", "requests.post"):
        assert forbidden not in text, forbidden
    assert "OPENAI_API_KEY" not in text.replace("A secret is never printed", "")


def test_the_workflow_is_a_guarded_read_only_dispatch():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text and "SEARCH_EVAL_READONLY" in text and "contents: read" in text
    assert "group: sedi-production-backend-operation" in text                      # one production operation at a time
    assert "image_tag_guard" in text and "oci_revision_guard" in text              # only against the running image
    assert "SECRET_LEAK" in text                                                   # the log is scanned before it is kept
    for forbidden in ("psql", "docker restart", "docker compose", "sed -i", "/etc/sedi", "env_file", "docker run"):
        assert forbidden not in text, forbidden
    import yaml

    data = yaml.safe_load(text)
    assert data["jobs"]["eval"]["steps"] and (data.get("on") or data[True])["workflow_dispatch"]["inputs"]["max_queries"]["default"] == "24"


# --- Codex round 1 on PR 212 ------------------------------------------------------------------------------------------------------------------
def test_p2_a_provider_failure_swallowed_by_the_wrapper_is_still_recorded(ev):
    """search_web_providers is fail-open (returns []); the probe sees the exception before it is swallowed."""
    probe = ev.FailureProbe()

    def provider(*a, **k):
        raise PermissionError("401")

    wrapped = probe.wrap(provider)

    def search(**k):  # what the production wrapper does: catch everything, return []
        try:
            return wrapped("q", "IR")
        except Exception:  # noqa: BLE001
            return []

    out = ev.measure({"specialty": "پوست", "area": None, "city": "پردیس", "province": "تهران"}, search, lambda *a, **k: "q", probe)
    assert out["error"] == "PermissionError" and out["results"] == 0


def test_p2_an_eval_where_every_query_failed_does_not_pass(ev):
    probe = ev.FailureProbe()

    def provider(*a, **k):
        raise RuntimeError("rate limit")

    wrapped = probe.wrap(provider)

    def search(**k):
        try:
            return wrapped()
        except Exception:  # noqa: BLE001
            return []

    lines = []
    ev.run(search, lambda *a, **k: None, None, limit=3, out=lines.append, probe=probe)
    assert lines[-1] == "EVAL|phase_search_eval|FAIL" and '"errors": 3' in lines[-2]


def test_p2_a_psychologist_is_not_a_psychiatrist_and_every_golden_specialty_has_its_own_stems(ev):
    assert ev.suitable({"specialty": "روانشناس بالینی", "name": "دکتر الف"}, "روانپزشکی") is False
    assert ev.suitable({"specialty": "متخصص روان‌پزشکی", "name": "دکتر الف"}, "روانپزشکی") is True
    assert ev.suitable({"specialty": "گوش، حلق و بینی", "name": "دکتر ب"}, "گوش و حلق و بینی") is True
    assert ev.suitable({"specialty": "متخصص مغز و اعصاب", "name": "دکتر ج"}, "مغز و اعصاب") is True
    assert ev.suitable({"specialty": "متخصص کودکان", "name": "دکتر ج"}, "مغز و اعصاب") is False
    assert set(ev.SPECIALTIES) <= set(ev._ALIASES)                       # no golden specialty falls back to a blunt prefix
