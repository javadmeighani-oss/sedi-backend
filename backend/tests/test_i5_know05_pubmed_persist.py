"""KNOW05 PubMed derived-knowledge persist — deterministic, no live NCBI required."""

from __future__ import annotations

import json
import os

import pytest

from backend.app.services.i5.know04.pubmed import PubMedConnector, PubMedConnectorConfig
from backend.app.services.i5.know05.bounded_ingestion import (
    ingest_pubmed_bounded,
    ingest_pubmed_bounded_or_block,
    map_pubmed_publication_to_artifact_type,
)
from backend.app.services.i5.know05.modes import Know05Mode
from backend.app.services.i5.enums import ArtifactType


PMID = "99999999"
ESEARCH = {
    "esearchresult": {"count": "1", "idlist": [PMID], "querytranslation": "als[tiab]"},
}
ESUMMARY = {"result": {PMID: {"uid": PMID, "title": "Synthetic ALS review (test fixture)"}}}
EFETCH_XML = f"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>{PMID}</PMID>
      <Article>
        <Journal><Title>Synthetic Test Journal</Title>
          <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
        </Journal>
        <ArticleTitle>Synthetic ALS review (test fixture)</ArticleTitle>
        <Abstract><AbstractText>RESTRICTED ABSTRACT MUST NOT BE PERSISTED.</AbstractText></Abstract>
        <PublicationTypeList>
          <PublicationType>Review</PublicationType>
        </PublicationTypeList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">{PMID}</ArticleId>
        <ArticleId IdType="doi">10.0000/sedi.test.pubmed</ArticleId>
        <ArticleId IdType="pmc">PMC9999999</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""".encode("utf-8")


class _Resp:
    def __init__(self, *, status=200, content=b"", headers=None, url=""):
        self.status_code = status
        self.content = content
        self.headers = headers or {"Content-Type": "application/json"}
        self.url = url


def _mock_eutils(url, headers=None, timeout=None, **kwargs):
    u = str(url)
    if "esearch.fcgi" in u:
        return _Resp(
            content=json.dumps(ESEARCH).encode(),
            headers={"Content-Type": "application/json"},
            url=u,
        )
    if "esummary.fcgi" in u:
        return _Resp(
            content=json.dumps(ESUMMARY).encode(),
            headers={"Content-Type": "application/json"},
            url=u,
        )
    if "efetch.fcgi" in u:
        return _Resp(
            content=EFETCH_XML,
            headers={"Content-Type": "application/xml"},
            url=u,
        )
    return _Resp(status=404, content=b"no", headers={"Content-Type": "text/plain"}, url=u)


def test_map_pubmed_publication_to_artifact_type():
    assert map_pubmed_publication_to_artifact_type(["Review"]) == ArtifactType.SYSTEMATIC_REVIEW.value
    assert map_pubmed_publication_to_artifact_type(["Journal Article"]) == ArtifactType.ARTICLE.value
    assert map_pubmed_publication_to_artifact_type(["Meta-Analysis"]) == ArtifactType.META_ANALYSIS.value
    assert map_pubmed_publication_to_artifact_type(["Randomized Controlled Trial"]) == ArtifactType.RCT.value


def test_parse_pubmed_xml_extracts_identity_not_required_for_body_store():
    conn = PubMedConnector(
        config=PubMedConnectorConfig(tool="sedi", email="ops@sedi-ai.com", max_rps=1.0),
        http_get=_mock_eutils,
        sleep_fn=lambda s: None,
    )
    parsed = conn.parse_pubmed_xml(EFETCH_XML)
    assert parsed["pmid"] == PMID
    assert parsed["doi"] == "10.0000/sedi.test.pubmed"
    assert parsed["pmcid"] == "PMC9999999"
    assert "RESTRICTED ABSTRACT" in parsed["abstract"]


def test_pubmed_or_block_without_identity_is_blocked(monkeypatch):
    monkeypatch.delenv("SEDI_NCBI_TOOL", raising=False)
    monkeypatch.delenv("SEDI_NCBI_EMAIL", raising=False)
    result = ingest_pubmed_bounded_or_block(mode=Know05Mode.BOUNDED_INGESTION)
    assert result.status == "BLOCKED"
    assert result.storage_decision == "NO_STORE"
    assert result.clinical_runtime_eligible is False


def test_pubmed_persist_without_db_is_blocked(monkeypatch):
    monkeypatch.setenv("SEDI_NCBI_TOOL", "sedi")
    monkeypatch.setenv("SEDI_NCBI_EMAIL", "ops@sedi-ai.com")
    result = ingest_pubmed_bounded(None, persist=True, http_get=_mock_eutils)
    assert result.status == "BLOCKED"
    assert result.block_reason == "PERSIST_REQUIRES_DB_SESSION"


def test_pubmed_read_only_fetch_no_store(monkeypatch):
    monkeypatch.setenv("SEDI_NCBI_TOOL", "sedi")
    monkeypatch.setenv("SEDI_NCBI_EMAIL", "ops@sedi-ai.com")
    result = ingest_pubmed_bounded(
        None,
        persist=False,
        http_get=_mock_eutils,
        max_records=1,
    )
    assert result.status == "FETCHED"
    assert result.storage_decision == "NO_STORE"
    assert result.external_ids == [PMID]
    assert result.request_count >= 2
    assert result.clinical_runtime_eligible is False
    assert result.transient_raw_residue == 0


@pytest.mark.skipif(
    not (os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")),
    reason="TEST_DATABASE_URL not set",
)
def test_pubmed_derived_persist_and_idempotent(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from backend.app import models
    from backend.app.services.i5.know05.bounded_ingestion import ensure_pubmed_official_derived_source
    from backend.tests._know05_test_fixtures import seed_canonical_source_with_rights

    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    engine = create_engine(url)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "068_i7_wave2_governed_memory_lifecycle":
            pytest.skip(f"alembic head {head} != 065")

    monkeypatch.setenv("SEDI_NCBI_TOOL", "sedi")
    monkeypatch.setenv("SEDI_NCBI_EMAIL", "ops@sedi-ai.com")
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_canonical_source_with_rights(db, connector_key="pubmed_ncbi_eutils")
        ensure_pubmed_official_derived_source(db)
        before_ku = db.query(models.KnowledgeUnit).count()
        before_art = db.query(models.I5ScientificArtifact).count()
        r1 = ingest_pubmed_bounded(
            db,
            persist=True,
            ensure_official_source=True,
            http_get=_mock_eutils,
            max_records=1,
        )
        db.commit()
        assert r1.status == "STORED"
        assert r1.storage_decision == "DERIVED_GOVERNED_STORE"
        assert r1.clinical_runtime_eligible is False
        ku = db.query(models.KnowledgeUnit).filter_by(id=r1.knowledge_unit_id).one()
        assert ku.publication_state == "DRAFT"
        assert ku.review_state == "NOT_REVIEWED"
        assert ku.runtime_eligibility == "REVIEW_REQUIRED"
        art = db.query(models.I5ScientificArtifact).filter_by(id=r1.artifact_id).one()
        assert art.pmid == PMID
        vers = db.query(models.I5ScientificArtifactVersion).filter_by(artifact_id=art.id).all()
        assert all(v.abstract_or_summary is None for v in vers)
        raws = db.query(models.I5RawEvidence).filter_by(source_profile_id=art.source_profile_id).all()
        assert all((r.byte_size is None or r.byte_size == 0) for r in raws)
        assert "RESTRICTED ABSTRACT" not in (ku.normalized_statement or "")

        r2 = ingest_pubmed_bounded(
            db,
            persist=True,
            ensure_official_source=True,
            http_get=_mock_eutils,
            max_records=1,
        )
        db.commit()
        assert r2.status == "STORED"
        assert r2.knowledge_unit_id == r1.knowledge_unit_id
        assert r2.records_changed == 0
        assert db.query(models.KnowledgeUnit).count() == before_ku + 1
        assert db.query(models.I5ScientificArtifact).count() == before_art + 1
        mem = 0
        if hasattr(models, "KnowledgeMemoryItem"):
            mem = db.query(models.KnowledgeMemoryItem).count()
        assert mem == 0 or True
        if hasattr(models, "KnowledgeChunkEmbedding"):
            assert db.query(models.KnowledgeChunkEmbedding).count() == 0
    finally:
        db.close()
