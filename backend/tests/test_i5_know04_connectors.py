"""I5-KNOW-04 — W0 NF7–NF11 + connectors/change/terminology deterministic tests.

No network required for core suite. Live canaries are opt-in / honestly classified.
All fixture scientific content is synthetic/test-only.
"""

from __future__ import annotations

import ast
import hashlib
import math
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.know02.artifacts import ContentDriftConflict, add_artifact_version, upsert_artifact
from backend.app.services.i5.know02.eligibility import runtime_evidence_allowed
from backend.app.services.i5.know02.taxonomy import add_mapping
from backend.app.services.i5.know03.effects import add_effect_estimate
from backend.app.services.i5.know03.recommendations import link_recommendation_evidence, supersede_recommendation, upsert_recommendation
from backend.app.services.i5.know03.seed_fixtures import seed_know03_foundation
from backend.app.services.i5.know03.studies import map_intervention
from backend.app.services.i5.know03.validation import EffectValidationError, validate_effect_payload
from backend.app.services.i5.know04.change_intelligence import (
    apply_artifact_change,
    classify_pubmed_publication_types,
    reassess_claim_runtime_support,
)
from backend.app.services.i5.know04.clinicaltrials import ClinicalTrialsGovConnector
from backend.app.services.i5.know04.guidelines import (
    GUIDELINE_SOURCE_CLASSIFICATIONS,
    WhoGuidelineCatalogueConnector,
    WhoNewsDiscoveryConnector,
)
from backend.app.services.i5.know04.authority_promotion import (
    AuthorityPromotionError,
    STAGE_DISCOVERED,
    STAGE_PARSED_RECOMMENDATION,
    STAGE_VERIFIED_ARTIFACT_POINTER,
    STAGE_VERIFIED_GUIDELINE,
    validate_promotion,
)
from backend.app.services.i5.know04.http_client import ConnectorHttpError, HardenedHttpClient
from backend.app.services.i5.know04.master_log_guard import (
    MasterLogPrefixMutationError,
    append_master_log_section,
    assert_byte_prefix,
    snapshot_master_log,
)
from backend.app.services.i5.know04.pmc import PmcConnector
from backend.app.services.i5.know04.pubmed import PubMedConnector, PubMedConnectorConfig
from backend.app.services.i5.know04.rate_limit import TokenBucketRateLimiter
from backend.app.services.i5.know04.rights_gate import evaluate_connector_rights
from backend.app.services.i5.know04.seed_profiles import seed_know04_connector_profiles
from backend.app.services.i5.know04.terminology import (
    hash_release_bytes,
    icd11_status,
    loinc_status,
    parse_mesh_descriptor_xml_fixture,
    record_terminology_import_run,
    rxnorm_status,
)
from backend.app.services.i5.know04.terminology_remap import TerminologyRemapConflict
from backend.app.services.i5.know04.transient import TransientRawWorkspace
from backend.app.services.i5.know04.xml_safety import safe_parse_xml
from backend.app.services.i5.enums import (
    ArtifactVersionState,
    EvidenceSupportDirection,
    ProcessingPermissionMode,
    RecommendationEvidenceTargetKind,
    RightDecision,
)


def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _heads_ok(head: str) -> bool:
    return head in {
        "065_i5_know04_connectors_change_intelligence",
        "064_i5_know03_studies_effects_recs",  # transitional local
    }


# ---------------------------------------------------------------------------
# Static / unit
# ---------------------------------------------------------------------------


def test_know04_no_p0_branching_in_core():
    root = Path("backend/app/services/i5/know04")
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert 'if disease == "ALS"' not in src
        assert 'if disease == "MS"' not in src
        assert 'if disease == "DIABETES"' not in src
        assert "als_articles" not in src
        assert ast.parse(src, filename=str(path)) is not None


def test_nf9_pvalue_domain_service():
    with pytest.raises(EffectValidationError):
        validate_effect_payload(p_value=-0.1)
    with pytest.raises(EffectValidationError):
        validate_effect_payload(p_value=1.1)
    with pytest.raises(EffectValidationError):
        validate_effect_payload(p_value=float("nan"))
    with pytest.raises(EffectValidationError):
        validate_effect_payload(p_value=float("inf"))
    ok = validate_effect_payload(p_value=0.05)
    assert ok["p_value"] == 0.05


def test_nf8_recommendation_target_xor_service_unit():
    from backend.app.services.i5.know03.recommendations import _enforce_recommendation_evidence_target_xor

    with pytest.raises(ValueError, match="MULTI_TARGET"):
        _enforce_recommendation_evidence_target_xor(
            target_kind="KNOWLEDGE_UNIT",
            knowledge_unit_id=1,
            artifact_version_id=2,
            study_id=None,
        )
    with pytest.raises(ValueError, match="TARGET_KIND_MISMATCH"):
        _enforce_recommendation_evidence_target_xor(
            target_kind="CLINICAL_STUDY",
            knowledge_unit_id=1,
            artifact_version_id=None,
            study_id=None,
        )
    a, b, c = _enforce_recommendation_evidence_target_xor(
        target_kind="ARTIFACT_VERSION",
        knowledge_unit_id=None,
        artifact_version_id=9,
        study_id=None,
    )
    assert (a, b, c) == (None, 9, None)


def test_unknown_rights_fail_closed():
    d = evaluate_connector_rights(
        processing_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
        access_right=RightDecision.UNKNOWN.value,
        automation_right=RightDecision.ALLOWED.value,
        tdm_right=RightDecision.ALLOWED.value,
        transform_right=RightDecision.ALLOWED.value,
        retain_raw_right=RightDecision.DENIED.value,
        retain_derived_right=RightDecision.ALLOWED.value,
    )
    assert d.processing_decision == "BLOCK"
    assert d.embedding_allowed is False
    assert d.raw_storage_allowed is False


def test_transient_raw_residue_zero():
    d = evaluate_connector_rights(
        processing_mode=ProcessingPermissionMode.TRANSIENT_PROCESS_ONLY.value,
        access_right=RightDecision.ALLOWED.value,
        automation_right=RightDecision.ALLOWED.value,
        tdm_right=RightDecision.ALLOWED.value,
        transform_right=RightDecision.ALLOWED.value,
        retain_raw_right=RightDecision.DENIED.value,
        retain_derived_right=RightDecision.ALLOWED.value,
        robots_state="ALLOWED",
    )
    ws = TransientRawWorkspace()
    ws.load(b"SYNTHETIC_FIXTURE_RAW_NOT_PRODUCTION", d)
    ws.derive("title", "synthetic", d)
    derived = ws.close_and_delete_raw()
    assert derived["title"] == "synthetic"
    assert ws.raw_residue_bytes == 0


def test_rate_limiter_deterministic():
    sleeps: list[float] = []
    clock = {"t": 0.0}

    def time_fn():
        return clock["t"]

    def sleep_fn(s):
        sleeps.append(s)
        clock["t"] += s

    lim = TokenBucketRateLimiter(max_per_second=3.0, sleep_fn=sleep_fn, time_fn=time_fn)
    for _ in range(3):
        lim.acquire()
        clock["t"] += 0.01
    lim.acquire()
    assert sleeps and sleeps[0] > 0


def test_http_retry_429_and_permanent_4xx():
    calls = {"n": 0}

    def http_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"status_code": 429, "headers": {}, "content": b"slow", "url": url}
        return {"status_code": 200, "headers": {"content-type": "application/json"}, "content": b"{}", "url": url}

    client = HardenedHttpClient(
        allowed_domains=("clinicaltrials.gov",),
        http_get=http_get,
        sleep_fn=lambda s: None,
        max_retries=3,
    )
    r = client.get("https://clinicaltrials.gov/api/v2/studies")
    assert r.status_code == 200
    assert calls["n"] == 3

    def bad(url, headers=None, timeout=None):
        return {"status_code": 404, "headers": {}, "content": b"x", "url": url}

    client2 = HardenedHttpClient(allowed_domains=("clinicaltrials.gov",), http_get=bad, sleep_fn=lambda s: None)
    with pytest.raises(ConnectorHttpError, match="PERMANENT_HTTP_4XX"):
        client2.get("https://clinicaltrials.gov/api/v2/studies/NCT0")


def test_http_429_then_success_uses_retry_after_bound():
    from backend.app.services.i5.know04.http_client import HTTP_429_EXHAUSTED, parse_retry_after_seconds

    sleeps: list[float] = []
    calls = {"n": 0}

    def http_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "status_code": 429,
                "headers": {"Retry-After": "3"},
                "content": b"retry later",
                "url": url,
            }
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "content": b'{"ok":true}',
            "url": url,
        }

    client = HardenedHttpClient(
        allowed_domains=("clinicaltrials.gov",),
        http_get=http_get,
        sleep_fn=sleeps.append,
        max_retries=3,
    )
    r = client.get("https://clinicaltrials.gov/api/v2/studies")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert calls["n"] == 2
    assert sleeps == [3.0]
    assert parse_retry_after_seconds({"Retry-After": "99"}, attempt=1) == 8.0
    assert parse_retry_after_seconds({"Retry-After": "not-a-number"}, attempt=1) == 1.0
    assert HTTP_429_EXHAUSTED == "HTTP_429_EXHAUSTED"


def test_http_429_exhaustion_does_not_return_or_parse_body():
    from backend.app.services.i5.know04.http_client import HTTP_429_EXHAUSTED, HttpResponse

    calls = {"n": 0}
    json_calls = {"n": 0}
    orig_json = HttpResponse.json

    def tracking_json(self):
        json_calls["n"] += 1
        return orig_json(self)

    HttpResponse.json = tracking_json  # type: ignore[method-assign]
    try:
        def http_get(url, headers=None, timeout=None):
            calls["n"] += 1
            return {
                "status_code": 429,
                "headers": {"Retry-After": "1", "content-type": "text/plain"},
                "content": b"retry later",
                "url": url,
            }

        client = HardenedHttpClient(
            allowed_domains=("clinicaltrials.gov",),
            http_get=http_get,
            sleep_fn=lambda s: None,
            max_retries=3,
        )
        with pytest.raises(ConnectorHttpError) as ei:
            resp = client.get("https://clinicaltrials.gov/api/v2/studies")
            resp.json()
        assert ei.value.code == HTTP_429_EXHAUSTED
        assert ei.value.status == 429
        assert calls["n"] == 4  # first try + max_retries=3
        assert json_calls["n"] == 0
    finally:
        HttpResponse.json = orig_json  # type: ignore[method-assign]


def test_http_429_malformed_retry_after_uses_bounded_backoff():
    sleeps: list[float] = []

    def http_get(url, headers=None, timeout=None):
        return {
            "status_code": 429,
            "headers": {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
            "content": b"x",
            "url": url,
        }

    client = HardenedHttpClient(
        allowed_domains=("clinicaltrials.gov",),
        http_get=http_get,
        sleep_fn=sleeps.append,
        max_retries=2,
    )
    with pytest.raises(ConnectorHttpError, match="HTTP_429_EXHAUSTED"):
        client.get("https://clinicaltrials.gov/api/v2/studies")
    assert sleeps == [1.0, 2.0]
    assert all(s <= 8.0 for s in sleeps)


def test_http_5xx_exhaustion_separate_from_429():
    from backend.app.services.i5.know04.http_client import HTTP_5XX_EXHAUSTED

    def http_get(url, headers=None, timeout=None):
        return {"status_code": 503, "headers": {}, "content": b"down", "url": url}

    client = HardenedHttpClient(
        allowed_domains=("clinicaltrials.gov",),
        http_get=http_get,
        sleep_fn=lambda s: None,
        max_retries=2,
    )
    with pytest.raises(ConnectorHttpError) as ei:
        client.get("https://clinicaltrials.gov/api/v2/studies")
    assert ei.value.code == HTTP_5XX_EXHAUSTED
    assert ei.value.status == 503


def test_http_timeout_and_malformed_2xx_remain_separate():
    def boom(url, headers=None, timeout=None):
        raise TimeoutError("SYNTHETIC_TIMEOUT")

    client = HardenedHttpClient(
        allowed_domains=("clinicaltrials.gov",),
        http_get=boom,
        sleep_fn=lambda s: None,
    )
    with pytest.raises(TimeoutError, match="SYNTHETIC_TIMEOUT"):
        client.get("https://clinicaltrials.gov/api/v2/studies")

    def ok_bad_json(url, headers=None, timeout=None):
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "content": b"not-json",
            "url": url,
        }

    client2 = HardenedHttpClient(
        allowed_domains=("clinicaltrials.gov",),
        http_get=ok_bad_json,
        sleep_fn=lambda s: None,
    )
    resp = client2.get("https://clinicaltrials.gov/api/v2/studies")
    with pytest.raises(ConnectorHttpError, match="MALFORMED_JSON"):
        resp.json()


def test_weekly_first_run_delay_seconds_bounded(monkeypatch):
    from backend.app.services.i5.governed_weekly_runtime import weekly_first_run_delay_seconds

    monkeypatch.delenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", raising=False)
    assert weekly_first_run_delay_seconds() is None
    monkeypatch.setenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "bogus")
    assert weekly_first_run_delay_seconds() is None
    monkeypatch.setenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "0")
    assert weekly_first_run_delay_seconds() is None
    monkeypatch.setenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "5")
    assert weekly_first_run_delay_seconds() == 30
    monkeypatch.setenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "120")
    assert weekly_first_run_delay_seconds() == 120
    monkeypatch.setenv("SEDI_I5_WEEKLY_FIRST_RUN_DELAY_SEC", "9999")
    assert weekly_first_run_delay_seconds() == 600


def test_weekly_first_run_at_is_tehran_aware_and_future():
    from datetime import datetime

    from backend.app.services.i5.governed_weekly_runtime import (
        weekly_first_run_at,
        weekly_scheduler_tz,
    )

    tz = weekly_scheduler_tz()
    target = weekly_first_run_at(120)
    assert target.tzinfo is not None
    assert getattr(target.tzinfo, "zone", None) == "Asia/Tehran"
    delta = (target - datetime.now(tz)).total_seconds()
    assert 100 <= delta <= 140


def test_weekly_first_run_at_naive_now_localized_as_tehran_not_utc():
    from datetime import datetime, timezone

    from backend.app.services.i5.governed_weekly_runtime import weekly_first_run_at

    naive = datetime(2026, 8, 13, 8, 56, 0)
    target = weekly_first_run_at(120, now=naive)
    assert target.tzinfo is not None
    assert target.hour == 8
    assert target.minute == 58
    offset = target.utcoffset()
    assert offset is not None
    assert offset.total_seconds() in {3.5 * 3600, 4.5 * 3600}
    utc_misread = datetime(2026, 8, 13, 8, 58, 0, tzinfo=timezone.utc)
    assert target != utc_misread
    assert target.utcoffset() != utc_misread.utcoffset()


def test_xxe_and_malformed_xml_blocked():
    with pytest.raises(ConnectorHttpError, match="XXE"):
        safe_parse_xml(b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><a>&xxe;</a>')
    with pytest.raises(ConnectorHttpError, match="MALFORMED_XML"):
        safe_parse_xml(b"<not><closed>")


def test_ncbi_external_doctype_stripped_without_loading_dtd():
    xml = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" '
        b'"https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">'
        b"<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID></MedlineCitation>"
        b"</PubmedArticle></PubmedArticleSet>"
    )
    root = safe_parse_xml(xml)
    assert root.find(".//PMID").text == "1"


def test_pubmed_parser_retraction_and_mesh_synthetic():
    xml = b"""<?xml version='1.0'?>
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>99999991</PMID>
          <Article>
            <ArticleTitle>SYNTHETIC FIXTURE ALS care - NOT PRODUCTION KNOWLEDGE</ArticleTitle>
            <Abstract><AbstractText>test-only abstract</AbstractText></Abstract>
            <PublicationTypeList>
              <PublicationType>Retraction of Publication</PublicationType>
            </PublicationTypeList>
          </Article>
          <MeshHeadingList>
            <MeshHeading><DescriptorName>Amyotrophic Lateral Sclerosis</DescriptorName></MeshHeading>
          </MeshHeadingList>
        </MedlineCitation>
        <CommentsCorrectionsList>
          <CommentsCorrections RefType="RetractionIn"><PMID>99999992</PMID></CommentsCorrections>
        </CommentsCorrectionsList>
      </PubmedArticle>
    </PubmedArticleSet>
    """
    conn = PubMedConnector(config=PubMedConnectorConfig(tool="sedi-test", email="sedi-test@example.com"), http_get=lambda *a, **k: None)
    parsed = conn.parse_pubmed_xml(xml)
    assert parsed["pmid"] == "99999991"
    assert "RETRACTED" in parsed["change_kinds"]
    rec = conn.normalize({**parsed, "synthetic_fixture": True})
    assert rec.synthetic_fixture is True
    assert rec.external_identifier == "PMID:99999991"
    assert classify_pubmed_publication_types(["Expression of Concern"]) == ["EXPRESSION_OF_CONCERN"]


def test_pmc_presence_not_fulltext_storage():
    pmc = PmcConnector(http_get=lambda *a, **k: None)
    rights = pmc.classify_rights(open_access=True, license_allows_storage=False, full_text_explicitly_allowed=False)
    assert rights["full_text_storage_allowed"] is False
    rec = pmc.normalize({"pmcid": "PMC9999999", "open_access_designation": True, "records": [{"license": "cc-by", "retracted": "no"}], "synthetic_fixture": True})
    assert rec.storage_decision in {"DERIVED_ONLY", "NO_STORE", "TRANSIENT_THEN_DELETE"}
    assert rec.provenance["full_text_storage_allowed"] is False


def test_ctgov_normalize_not_recommendation():
    raw = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT99999999", "briefTitle": "SYNTHETIC MS rehab trial FIXTURE"},
            "statusModule": {"overallStatus": "Recruiting", "lastUpdatePostDateStruct": {"date": "2026-01-01"}},
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]},
            "conditionsModule": {"conditions": ["Multiple Sclerosis"]},
            "eligibilityModule": {"sex": "ALL", "minimumAge": "18 Years"},
            "armsInterventionsModule": {"interventions": [{"name": "FIXTURE_EXERCISE"}]},
            "outcomesModule": {"primaryOutcomes": [{"measure": "FIXTURE_OUTCOME"}]},
            "contactsLocationsModule": {"locations": [{"city": "Tehran", "country": "Iran"}]},
        },
        "synthetic_fixture": True,
    }
    rec = ClinicalTrialsGovConnector().normalize(raw)
    assert rec.payload["is_clinical_recommendation"] is False
    assert rec.payload["experimental_as_established_treatment"] == 0
    cand = ClinicalTrialsGovConnector().emit_artifact_candidate(rec)
    assert cand["must_not_become_recommendation"] is True


def test_guideline_framework_classifications_and_rss_parse():
    assert GUIDELINE_SOURCE_CLASSIFICATIONS["who_news"]["who_artifact_kind"] == "WHO_NEWS"
    assert GUIDELINE_SOURCE_CLASSIFICATIONS["who_guideline_catalogue"]["access_mechanism"] == "OFFICIAL_HTML_ONLY"
    assert GUIDELINE_SOURCE_CLASSIFICATIONS["who_guideline_catalogue"]["catalogue_semantics"] == "OFFICIAL_HTML_CATALOGUE"
    assert GUIDELINE_SOURCE_CLASSIFICATIONS["aan_guidelines"]["access_mechanism"] == "OFFICIAL_HTML_ONLY"
    rss = b"""<?xml version='1.0'?><rss><channel>
      <item><title>SYNTHETIC WHO diabetes guidance fixture</title><link>https://www.who.int/fixture</link>
      <guid>who-fixture-1</guid><pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
      <description>test-only</description></item></channel></rss>"""
    items = WhoNewsDiscoveryConnector().parse_rss(rss)
    assert items[0]["guid"] == "who-fixture-1"
    rec = WhoNewsDiscoveryConnector().normalize({**items[0], "synthetic_fixture": True})
    assert rec.source_role == "NEWS_OR_DISCOVERY_SIGNAL"
    assert rec.resource_type == "NEWS_ITEM"
    assert rec.payload["clinical_guideline"] is False
    assert rec.payload["clinical_recommendation"] is False
    assert rec.payload["runtime_medical_authority"] is False
    assert rec.payload.get("recommendation_text") is None
    assert rec.provenance["discovery_only"] is True


def test_nf14_who_news_not_guideline_or_recommendation():
    rss = b"""<?xml version='1.0'?><rss><channel>
      <item><title>New WHO guideline announced</title><link>https://www.who.int/news/item/x</link>
      <guid>who-news-nf14</guid><description>Press release only</description></item></channel></rss>"""
    rec = WhoNewsDiscoveryConnector().normalize({**WhoNewsDiscoveryConnector().parse_rss(rss)[0], "synthetic_fixture": True})
    assert rec.source_role != "CLINICAL_GUIDELINE"
    assert rec.payload["clinical_guideline"] is False
    assert rec.payload["clinical_recommendation"] is False
    assert rec.payload.get("recommendation_text") is None
    assert rec.payload["who_artifact_kind"] == "WHO_NEWS"


def test_nf14_catalogue_entry_not_recommendation():
    raw = {
        "canonical_locator": "https://www.who.int/publications/i/item/9789240121744",
        "external_identifier": "9789240121744",
        "who_artifact_kind": "WHO_GUIDELINE_CATALOGUE_ENTRY",
        "synthetic_fixture": True,
    }
    rec = WhoGuidelineCatalogueConnector().normalize(raw)
    assert rec.payload["clinical_recommendation"] is False
    assert rec.payload.get("recommendation_text") is None
    assert rec.payload["recommendation_extraction"] == "NOT_EXERCISED"
    assert rec.payload["guideline_catalogue_pointer"] is True


def test_nf14_verified_guideline_classification_fixture():
    html = b"""
    <html><body>
    <a href="https://www.who.int/publications/i/item/9789240121744">WHO guideline</a>
    <a href="/publications/i/item/guidelines-for-malaria">relative</a>
    </body></html>
    """
    records = WhoGuidelineCatalogueConnector().parse_catalogue_html(html, max_records=2)
    assert len(records) == 2
    assert records[1]["canonical_locator"].endswith("/guidelines-for-malaria")
    rec = WhoGuidelineCatalogueConnector().normalize(records[0])
    assert rec.resource_type == "WHO_GUIDELINE_CATALOGUE_ENTRY"
    assert rec.payload["authority_stage"] == STAGE_VERIFIED_ARTIFACT_POINTER


def test_nf14_illegal_authority_promotion_jumps():
    with pytest.raises(AuthorityPromotionError):
        validate_promotion(from_stage=STAGE_DISCOVERED, to_stage=STAGE_PARSED_RECOMMENDATION)
    with pytest.raises(AuthorityPromotionError):
        validate_promotion(from_stage=STAGE_DISCOVERED, to_stage=STAGE_VERIFIED_GUIDELINE)
    with pytest.raises(AuthorityPromotionError):
        validate_promotion(from_stage=STAGE_VERIFIED_ARTIFACT_POINTER, to_stage=STAGE_PARSED_RECOMMENDATION)
    validate_promotion(from_stage=STAGE_DISCOVERED, to_stage=STAGE_VERIFIED_ARTIFACT_POINTER)
    validate_promotion(from_stage=STAGE_VERIFIED_ARTIFACT_POINTER, to_stage=STAGE_VERIFIED_GUIDELINE)
    validate_promotion(from_stage=STAGE_VERIFIED_GUIDELINE, to_stage=STAGE_PARSED_RECOMMENDATION)


def test_terminology_statuses_honest():
    assert icd11_status().live_status in {"NOT_EXECUTED_MISSING_CREDENTIALS", "NOT_EXECUTED"}
    assert "LICENSE" in rxnorm_status().connector_state or "RIGHTS" in rxnorm_status().live_status
    assert loinc_status().live_status == "NOT_EXECUTED_RIGHTS_BLOCK"
    mesh_xml = b"""<?xml version='1.0'?><DescriptorRecordSet>
      <DescriptorRecord><DescriptorUI>D000690</DescriptorUI>
      <DescriptorName><String>SYNTHETIC Amyotrophic Lateral Sclerosis FIXTURE</String></DescriptorName>
      <TreeNumberList><TreeNumber>C10.999</TreeNumber></TreeNumberList>
      </DescriptorRecord></DescriptorRecordSet>"""
    rows = parse_mesh_descriptor_xml_fixture(mesh_xml)
    assert rows[0]["descriptor_ui"] == "D000690"


def test_master_log_byte_prefix_guard(tmp_path):
    p = tmp_path / "log.md"
    p.write_bytes(b"BASE\r\nLINE1\r\n")
    base = snapshot_master_log(p)
    post = append_master_log_section(p, "NEW SECTION\nline", baseline=base)
    assert post.bytes.startswith(base.bytes)
    assert post.lf_only_count == 0
    # mutation attempt
    with pytest.raises(MasterLogPrefixMutationError):
        assert_byte_prefix(b"NOPE", post.bytes)


# ---------------------------------------------------------------------------
# PostgreSQL integrity + propagation
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")
def test_know04_w0_and_connectors_pg():
    from backend.app import models
    from backend.app.services.i5.know02.artifacts import link_evidence
    from backend.app.services.i5.know03.studies import (
        link_study_intervention,
        link_study_outcome,
        upsert_clinical_study,
        upsert_intervention,
        upsert_outcome,
        upsert_population,
    )

    url = _pg_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "067_i7_lifelong_memory_foundation":
            pytest.skip(f"alembic head {head} != 065")
        for t in (
            "i5_connector_profiles",
            "i5_scientific_change_events",
            "i5_terminology_mapping_conflict_events",
            "i5_terminology_import_runs",
            "i5_source_ingestion_audit",
        ):
            assert conn.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name=:t"), {"t": t}).scalar()

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_know03_foundation(db)
        seed_know04_connector_profiles(db)
        db.commit()

        # --- NF7 cross-study ownership ---
        s1 = upsert_clinical_study(
            db, study_key="fixture:know04:studyA", title="A", study_design="RANDOMIZED_CONTROLLED_TRIAL"
        )
        s2 = upsert_clinical_study(
            db, study_key="fixture:know04:studyB", title="B", study_design="RANDOMIZED_CONTROLLED_TRIAL"
        )
        db.flush()
        pop2 = upsert_population(db, study_id=s2.id, population_key="popB", label="popB")
        int1 = upsert_intervention(
            db, intervention_key="fixture:know04:intA", preferred_name="intA", intervention_category="DRUG"
        )
        int2 = upsert_intervention(
            db, intervention_key="fixture:know04:intB", preferred_name="intB", intervention_category="DRUG"
        )
        si1 = link_study_intervention(db, study_id=s1.id, intervention_id=int1.id, intervention_role="EXPERIMENTAL")
        si2 = link_study_intervention(db, study_id=s2.id, intervention_id=int2.id, intervention_role="EXPERIMENTAL")
        out1 = upsert_outcome(db, outcome_key="fixture:know04:outA", preferred_name="outA", outcome_category="FUNCTION")
        out2 = upsert_outcome(db, outcome_key="fixture:know04:outB", preferred_name="outB", outcome_category="FUNCTION")
        so1 = link_study_outcome(db, study_id=s1.id, outcome_id=out1.id, outcome_role="PRIMARY")
        so2 = link_study_outcome(db, study_id=s2.id, outcome_id=out2.id, outcome_role="PRIMARY")
        db.flush()

        # service rejects cross-study
        with pytest.raises(EffectValidationError, match="CROSS_STUDY_POPULATION"):
            add_effect_estimate(
                db, study_id=s1.id, study_outcome_id=so1.id, effect_measure="RISK_RATIO", population_id=pop2.id, p_value=0.05
            )
        with pytest.raises(EffectValidationError, match="CROSS_STUDY_INTERVENTION"):
            add_effect_estimate(
                db, study_id=s1.id, study_outcome_id=so1.id, effect_measure="RISK_RATIO", study_intervention_id=si2.id, p_value=0.05
            )
        with pytest.raises(EffectValidationError, match="CROSS_STUDY_OUTCOME"):
            add_effect_estimate(db, study_id=s1.id, study_outcome_id=so2.id, effect_measure="RISK_RATIO", p_value=0.05)

        # direct SQL bypass also fails (composite FK)
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO i5_study_effect_estimates (study_id, population_id, study_outcome_id, effect_measure) "
                    "VALUES (:s, :p, :o, 'RISK_RATIO')"
                ),
                {"s": s1.id, "p": pop2.id, "o": so1.id},
            )
            db.flush()
        db.rollback()
        seed_know03_foundation(db)
        seed_know04_connector_profiles(db)
        # recreate minimal refs after rollback
        s1 = upsert_clinical_study(
            db, study_key="fixture:know04:studyA", title="A", study_design="RANDOMIZED_CONTROLLED_TRIAL"
        )
        s2 = upsert_clinical_study(
            db, study_key="fixture:know04:studyB", title="B", study_design="RANDOMIZED_CONTROLLED_TRIAL"
        )
        pop1 = upsert_population(db, study_id=s1.id, population_key="popA", label="popA")
        int1 = upsert_intervention(
            db, intervention_key="fixture:know04:intA", preferred_name="intA", intervention_category="DRUG"
        )
        si1 = link_study_intervention(db, study_id=s1.id, intervention_id=int1.id, intervention_role="EXPERIMENTAL")
        out1 = upsert_outcome(
            db, outcome_key="fixture:know04:outA", preferred_name="outA", outcome_category="FUNCTION"
        )
        so1 = link_study_outcome(db, study_id=s1.id, outcome_id=out1.id, outcome_role="PRIMARY")
        db.flush()
        ok_eff = add_effect_estimate(
            db,
            study_id=s1.id,
            study_outcome_id=so1.id,
            effect_measure="RISK_RATIO",
            population_id=pop1.id,
            study_intervention_id=si1.id,
            p_value=0.04,
        )
        assert ok_eff.id

        # NF9 DB reject
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO i5_study_effect_estimates (study_id, study_outcome_id, effect_measure, p_value) "
                    "VALUES (:s, :o, 'RISK_RATIO', 1.5)"
                ),
                {"s": s1.id, "o": so1.id},
            )
            db.flush()
        db.rollback()

        # NF8 XOR — re-seed study after rollback
        s1 = upsert_clinical_study(
            db, study_key="fixture:know04:studyA", title="A", study_design="RANDOMIZED_CONTROLLED_TRIAL"
        )
        db.flush()
        art = upsert_artifact(db, artifact_key="fixture:know04:recsrc", artifact_type="GUIDELINE", title="g")
        ver = add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="aa" * 32)
        rec = upsert_recommendation(
            db,
            recommendation_key="fixture:know04:rec1",
            source_artifact_version_id=ver.id,
            recommended_action="synthetic action",
            recommendation_direction="RECOMMEND",
        )
        db.flush()
        link_recommendation_evidence(
            db,
            recommendation_id=rec.id,
            target_kind=RecommendationEvidenceTargetKind.CLINICAL_STUDY.value,
            study_id=s1.id,
        )
        with pytest.raises(ValueError, match="MULTI_TARGET"):
            link_recommendation_evidence(
                db,
                recommendation_id=rec.id,
                target_kind=RecommendationEvidenceTargetKind.CLINICAL_STUDY.value,
                study_id=s1.id,
                artifact_version_id=ver.id,
            )
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO i5_clinical_recommendation_evidence_links "
                    "(recommendation_id, target_kind, knowledge_unit_id, study_id, support_direction) "
                    "VALUES (:r, 'CLINICAL_STUDY', 1, :s, 'SUPPORTS')"
                ),
                {"r": rec.id, "s": s1.id},
            )
            db.flush()
        db.rollback()

        # NF10 terminology remap
        seed_know03_foundation(db)
        als = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:als").one()
        ms = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:ms").one()
        m1 = add_mapping(db, concept_id=als.id, terminology_system="MESH", external_code="FIX-KNOW04-MAP", release_version="2026")
        m1b = add_mapping(db, concept_id=als.id, terminology_system="MESH", external_code="FIX-KNOW04-MAP", release_version="2026")
        assert m1.id == m1b.id
        with pytest.raises(TerminologyRemapConflict):
            add_mapping(db, concept_id=ms.id, terminology_system="MESH", external_code="FIX-KNOW04-MAP", release_version="2026")
        assert db.query(models.I5TerminologyMappingConflictEvent).count() >= 1

        # Retraction scenarios A/B — isolated KU so other seeded evidence cannot pollute reassessment
        a1 = upsert_artifact(db, artifact_key="fixture:know04:art1", artifact_type="ARTICLE", title="a1", pmid="SYNTH1")
        a2 = upsert_artifact(db, artifact_key="fixture:know04:art2", artifact_type="ARTICLE", title="a2", pmid="SYNTH2")
        a3 = upsert_artifact(db, artifact_key="fixture:know04:art3", artifact_type="ARTICLE", title="a3", pmid="SYNTH3")
        v1 = add_artifact_version(db, artifact_id=a1.id, version_label="1", content_hash="11" * 32)
        v2 = add_artifact_version(db, artifact_id=a2.id, version_label="1", content_hash="22" * 32)
        v3 = add_artifact_version(db, artifact_id=a3.id, version_label="1", content_hash="33" * 32)
        from backend.app.services.i5.know02.seed_fixtures import _make_ku

        ku = _make_ku(
            db,
            canonical="know04:claim:retraction_canary",
            statement="SYNTHETIC FIXTURE claim for retraction propagation - NOT PRODUCTION",
            domain="clinical",
            knowledge_type="FACT",
        )
        for vv in (v1, v2, v3):
            link_evidence(
                db,
                knowledge_unit_id=ku.id,
                artifact_version_id=vv.id,
                support_direction=EvidenceSupportDirection.SUPPORTS.value,
            )
        db.flush()
        apply_artifact_change(db, artifact_version_id=v1.id, change_kind="RETRACTED", source_connector_key="pubmed_ncbi_eutils")
        assert not runtime_evidence_allowed(db.get(models.I5ScientificArtifactVersion, v1.id))
        result = reassess_claim_runtime_support(db, knowledge_unit_id=ku.id)
        assert result["retracted_positive_runtime_evidence"] == 0
        assert result["claim_deleted"] is False
        assert result["eligible_support_links"] >= 2

        # Scenario A: retract remaining supports
        apply_artifact_change(db, artifact_version_id=v2.id, change_kind="RETRACTED")
        apply_artifact_change(db, artifact_version_id=v3.id, change_kind="RETRACTED")
        result2 = reassess_claim_runtime_support(db, knowledge_unit_id=ku.id)
        assert result2["claim_unsupported_if_no_other_valid_support"] is True
        assert result2["claim_deleted"] is False
        assert result2["eligible_support_links"] == 0

        # Scenario C supersession
        art = upsert_artifact(db, artifact_key="fixture:know04:recsrc", artifact_type="GUIDELINE", title="g")
        ver = add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="aa" * 32)
        rec_old = upsert_recommendation(
            db,
            recommendation_key="fixture:know04:rec_old",
            source_artifact_version_id=ver.id,
            recommended_action="old",
            recommendation_direction="RECOMMEND",
        )
        rec_new = upsert_recommendation(
            db,
            recommendation_key="fixture:know04:rec_new",
            source_artifact_version_id=ver.id,
            recommended_action="new",
            recommendation_direction="RECOMMEND",
        )
        db.flush()
        supersede_recommendation(db, old_recommendation_id=rec_old.id, new_recommendation_id=rec_new.id)
        from backend.app.services.i5.know04.change_intelligence import record_change_event

        record_change_event(db, change_kind="SUPERSEDED", recommendation_id=rec_old.id, details="scenario_c")
        assert rec_old.status == "SUPERSEDED"

        # Scenario D expression of concern != retraction
        v_eoc = add_artifact_version(db, artifact_id=a1.id, version_label="2", content_hash="44" * 32)
        apply_artifact_change(db, artifact_version_id=v_eoc.id, change_kind="EXPRESSION_OF_CONCERN")
        v_eoc = db.get(models.I5ScientificArtifactVersion, v_eoc.id)
        assert v_eoc.version_state == ArtifactVersionState.EXPRESSION_OF_CONCERN.value
        assert runtime_evidence_allowed(v_eoc) is True  # not auto-blocked as retraction

        # terminology release versioning
        h = hash_release_bytes(b"SYNTHETIC_MESH_RELEASE_V1")
        r1 = record_terminology_import_run(
            db,
            terminology_system="MESH",
            release_version="2026-fixture-1",
            source_note="synthetic fixture",
            import_status="BOUNDED_IMPORT_VERIFIED",
            content_hash=h,
            new_codes=1,
        )
        r1b = record_terminology_import_run(
            db,
            terminology_system="MESH",
            release_version="2026-fixture-1",
            source_note="synthetic fixture",
            import_status="BOUNDED_IMPORT_VERIFIED",
            content_hash=h,
        )
        assert r1.id == r1b.id
        with pytest.raises(ValueError, match="SILENT_TERMINOLOGY_CONTENT_OVERWRITE"):
            record_terminology_import_run(
                db,
                terminology_system="MESH",
                release_version="2026-fixture-1",
                source_note="synthetic fixture",
                import_status="BOUNDED_IMPORT_VERIFIED",
                content_hash=hash_release_bytes(b"DIFFERENT"),
            )

        db.commit()
    finally:
        db.close()


# Live canaries moved to test_i5_know04_live_canaries.py (mandatory CI job 2)
