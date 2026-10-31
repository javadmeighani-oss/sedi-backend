"""R-044 step 5: the weekly knowledge-growth report shows ELIGIBLE counts per domain x language, before / after.

The report is read-only aggregate counts (no statement text, no user data). The weekly hook only logs it and can
never break the run; the production probe prints it through a read-only CLI.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from backend.app import models
from backend.app.services.i5 import weekly_growth_report as wgr

NOW = datetime(2026, 11, 6, 1, 0, 0)
SINCE = datetime(2026, 11, 6, 0, 0, 0)


def _assemble(**over):
    base = dict(
        generated_at=NOW,
        since=SINCE,
        run={"id": 33, "status": "COMPLETED_WITH_WARNINGS"},
        source_results=[
            {"source_key": "nhs_uk_mental_health", "result_status": "EXTRACTED", "knowledge_new_count": 3, "knowledge_updated_count": 1},
            {"source_key": "nhs_uk_mental_health", "result_status": "SKIPPED", "failure_code": "NO_MATERIAL_CHANGE"},
            {"source_key": "cdc_chronic_disease", "result_status": "FAILED", "failure_code": "TIMEOUT", "knowledge_rejected_count": 2, "error_count": 1},
        ],
        unit_counts=[
            ("mental_health_psychology", "en", "ELIGIBLE", 95),
            ("wellbeing", "en", "ELIGIBLE", 42),
            ("neurology", "en", "ELIGIBLE", 101),
            ("mental_health_psychology", "en", "REVIEW_REQUIRED", 22),
        ],
        created_counts=[
            ("mental_health_psychology", "en", "ELIGIBLE", 3),
            ("mental_health_psychology", "en", "REVIEW_REQUIRED", 1),
        ],
        discovery=[{"source_key": "nhs_uk_mental_health", "discovered": 12, "last": {"admitted": 12}}],
        gaps_total=0,
        gaps_created=0,
        baseline_counts=[
            ("mental_health_psychology", "en", "ELIGIBLE", 92),
            ("wellbeing", "en", "ELIGIBLE", 42),
            ("neurology", "en", "ELIGIBLE", 101),
        ],
        attempt_counters={"new_knowledge_count": 3, "updated_knowledge_count": 1, "superseded_knowledge_count": 1, "rejected_knowledge_count": 2, "error_count": 1},
    )
    base.update(over)
    return wgr.assemble_report(**base)


def test_growth_is_shown_per_domain_and_language_with_before_and_after():
    report = _assemble()
    assert report["verdict"] == "GREW"
    assert report["knowledge"]["eligible_total"] == 238
    assert report["knowledge"]["eligible_by_domain_language"]["mental_health_psychology|en"] == 95
    assert report["growth"]["eligible_created"] == 3
    assert report["growth"]["eligible_before"] == 235
    assert report["growth"]["eligible_net"] == 3
    assert report["growth"]["eligible_net_by_domain_language"] == {"mental_health_psychology|en": 3}
    assert report["growth"]["eligible_created_by_domain_language"] == {"mental_health_psychology|en": 3}
    assert report["growth"]["created_by_eligibility"] == {"ELIGIBLE": 3, "REVIEW_REQUIRED": 1}


def test_psychology_comes_first_with_its_own_numbers():
    psych = _assemble()["psychology"]
    assert psych["domains"] == ["mental_health_psychology", "wellbeing"]
    assert psych["by_eligibility"] == {"ELIGIBLE": 137, "REVIEW_REQUIRED": 22}
    assert psych["eligible_created"] == 3


def test_sources_are_summarised_per_source_and_failure_code():
    sources = _assemble()["sources"]
    assert sources["checked"] == 3
    assert sources["by_result"] == {"EXTRACTED": 1, "FAILED": 1, "SKIPPED": 1}
    # aggregate outcomes come from the attempt ledger, not from the (always zero) source-result rows
    assert (sources["new"], sources["updated"], sources["superseded"], sources["rejected"], sources["errors"]) == (3, 1, 1, 2, 1)
    assert sources["failure_codes"] == {"NO_MATERIAL_CHANGE": 1, "TIMEOUT": 1}
    nhs = next(s for s in sources["per_source"] if s["source_key"] == "nhs_uk_mental_health")
    assert nhs["urls"] == 2 and nhs["by_result"] == {"EXTRACTED": 1, "SKIPPED": 1} and "new" not in nhs


def test_a_replaced_unit_is_not_growth():
    # one of 100 eligible units is replaced by a new version: the old one turns NOT_ELIGIBLE, the new one is ELIGIBLE
    report = _assemble(
        unit_counts=[("wellbeing", "en", "ELIGIBLE", 100), ("wellbeing", "en", "NOT_ELIGIBLE", 1)],
        created_counts=[("wellbeing", "en", "ELIGIBLE", 1)],
        baseline_counts=[("wellbeing", "en", "ELIGIBLE", 100)],
    )
    assert report["growth"]["eligible_before"] == 100 and report["growth"]["eligible_net"] == 0
    assert report["verdict"] == "NO_NET_GROWTH"


def test_a_retirement_sweep_shows_as_decline():
    report = _assemble(
        unit_counts=[("wellbeing", "en", "ELIGIBLE", 90)],
        created_counts=[("wellbeing", "en", "ELIGIBLE", 1)],
        baseline_counts=[("wellbeing", "en", "ELIGIBLE", 100)],
    )
    assert report["verdict"] == "DECLINED" and report["growth"]["eligible_net"] == -10
    assert report["growth"]["eligible_net_by_domain_language"] == {"wellbeing|en": -10}


def test_without_a_baseline_no_before_or_net_claim_is_made():
    report = _assemble(baseline_counts=None)
    assert report["verdict"] == "NO_BASELINE"
    assert report["growth"]["eligible_before"] is None and report["growth"]["eligible_net"] is None
    assert _assemble(baseline_counts=None, created_counts=[])["verdict"] == "NO_NEW_UNITS"


def test_the_baseline_helper_is_fail_open():
    class Broken:
        def query(self, *a, **k):
            raise RuntimeError("db gone")

    assert wgr.capture_eligible_baseline(Broken(), models) is None


def test_discovery_numbers_and_flag_state(monkeypatch):
    monkeypatch.delenv("SEDI_I5_LINK_DISCOVERY_ENABLED", raising=False)
    report = _assemble()
    assert report["discovery"]["discovered_urls_total"] == 12 and report["discovery"]["enabled"] is False
    monkeypatch.setenv("SEDI_I5_LINK_DISCOVERY_ENABLED", "true")
    assert _assemble()["discovery"]["enabled"] is True


def test_report_carries_counts_only():
    text = str(_assemble())
    assert "normalized_statement" not in text and "user" not in text.lower()


def test_weekly_hook_never_raises():
    class Broken:
        def query(self, *a, **k):
            raise RuntimeError("db gone")

    assert wgr.log_weekly_growth_report(Broken(), models) is None
    assert wgr.log_weekly_growth_report(None, models) is None


def _ku(db, *, domain, eligibility, created_at, tag):
    fp = hashlib.sha256(tag.encode()).hexdigest()
    ku = models.KnowledgeUnit(
        canonical_unit_id=f"ku-wgr-{fp[:16]}",
        immutable_version_id="v1",
        domain=domain,
        topic_taxonomy="mental_health_education",
        language="en",
        knowledge_type="OTHER",
        normalized_statement=f"Growth report test statement {tag} about coping with stress and worry.",
        applicability="consumer_health_education_not_diagnosis",
        evidence_strength="MODERATE",
        medical_safety_state="CLEARED",
        conflict_state="NONE",
        freshness_state="CURRENT",
        review_state="APPROVED",
        publication_state="PUBLISHED",
        runtime_eligibility=eligibility,
        provenance_complete=True,
        deduplication_key=hashlib.sha256(f"d-{tag}".encode()).hexdigest(),
        canonical_hash=hashlib.sha256(f"c-{tag}".encode()).hexdigest(),
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
        created_at=created_at,
    )
    db.add(ku)
    db.flush()


def test_build_report_reads_the_database_without_writing(db):
    now = datetime.utcnow()
    baseline = wgr.capture_eligible_baseline(db, models)
    before = wgr.build_weekly_growth_report(db, models, now=now)
    _ku(db, domain="mental_health_psychology", eligibility="ELIGIBLE", created_at=now - timedelta(days=30), tag="old")
    _ku(db, domain="mental_health_psychology", eligibility="ELIGIBLE", created_at=now - timedelta(hours=1), tag="new")
    _ku(db, domain="wellbeing", eligibility="NOT_ELIGIBLE", created_at=now - timedelta(hours=1), tag="blocked")
    after = wgr.build_weekly_growth_report(db, models, now=now, baseline_counts=baseline)
    assert after["growth"]["eligible_net"] == 2 and after["verdict"] == "GREW"
    assert after["knowledge"]["eligible_total"] - before["knowledge"]["eligible_total"] == 2
    assert after["growth"]["eligible_created"] - before["growth"]["eligible_created"] == 1
    assert after["psychology"]["eligible_created"] - before["psychology"]["eligible_created"] == 1
    assert after["growth"]["created_by_eligibility"].get("NOT_ELIGIBLE", 0) - before["growth"]["created_by_eligibility"].get("NOT_ELIGIBLE", 0) == 1
    assert not db.new and not db.dirty


def test_probe_workflow_prints_the_report_read_only():
    wf = (Path(__file__).resolve().parents[2] / ".github/workflows/i5-prod-readonly-probe.yml").read_text(encoding="utf-8")
    assert "python -m backend.app.services.i5.weekly_growth_report" in wf
    assert "PROBE|growth_report|" in wf
