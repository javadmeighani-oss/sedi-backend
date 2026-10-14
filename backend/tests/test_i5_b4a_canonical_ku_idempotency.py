"""B4A — KU idempotency under the 81-C1/81-C2 identity contract.

The original B4A fixed same-content reuse when the content-derived dedupe key drifted
(identity `ku-w6p01-<fingerprint>`). Since 81-C1 the logical identity is source+URL and
since 81-C2 a changed served statement opens the next version. These tests keep the B4A
intent on the new contract and prove compatibility with legacy production rows whose
canonical_unit_id is still `ku-w6p01-<fingerprint>`.
"""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime

import pytest
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5 import governed_weekly_runtime as runtime


def _sha(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for governed persistence DB nodes")


def _models():
    configure_mappers()
    return importlib.import_module("backend.app.models")


class _Handoff:
    def __init__(self, kind: str, key: str, payload: dict) -> None:
        self.handoff_kind = kind
        self.request_key = key
        self.payload = payload
        self.execute = False


def _handoffs(
    *,
    profile_id: int,
    url: str,
    statement: str,
    page_token: str,
    dedupe_key: str,
    canonical_hash: str,
) -> list[_Handoff]:
    content_hash = _sha(page_token)
    raw_key = f"raw-{content_hash[:12]}"
    shared = {
        "source_profile_id": profile_id,
        "canonical_url": url,
        "rights_terms_state": "OGL",
        "robots_access_state": "ALLOWED",
        "content_sha256": content_hash,
        "byte_hash": content_hash,
        "normalized_hash": canonical_hash,
        "normalized_statement": statement,
        "candidate_fingerprint": content_hash,
        "dedupe_key": dedupe_key,
        "canonical_hash": canonical_hash,
        "domain": "oncology",
        "topic": "cancer",
        "language": "en",
        "jurisdiction": "US",
        "retrieval_method": "PUBLIC_WEB_FETCH_HTTPS",
        "raw_evidence_request_key": raw_key,
    }
    return [
        _Handoff("RAW_EVIDENCE", raw_key, dict(shared)),
        _Handoff("CANDIDATE", f"cand-{content_hash[:12]}", dict(shared)),
        _Handoff("PROVENANCE", f"prov-{content_hash[:12]}", dict(shared)),
    ]


def _setup(db, models, key: str):
    gsp = models.GovernedSourceProfile(
        canonical_key=f"b4a-{key}",
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        canonicalization_version="v1",
    )
    db.add(gsp)
    run = models.WeeklyKnowledgeRun(
        logical_run_key=_sha(f"b4a-run-{key}"),
        schedule_key="weekly_governed_test",
        run_type="WEEKLY_GOVERNED",
        trigger_type="AD_HOC",
        planned_window_start=datetime(2026, 8, 8, 0, 0, 0),
        planned_window_end=datetime(2026, 8, 15, 0, 0, 0),
        approval_state="APPROVED",
        source_scope="{}",
        domain_scope="{}",
        gap_scope="{}",
        source_scope_hash=_sha("src"),
        domain_scope_hash=_sha("dom"),
        gap_scope_hash=_sha("gap"),
        config_version="w6p01-governed-v1",
        config_hash=_sha("cfg"),
        status="PLANNED",
    )
    db.add(run)
    db.flush()
    return int(gsp.id), int(run.id)


def _persist(db, models, run_id: int, handoffs: list[_Handoff]):
    return runtime.execute_governed_persistence(
        db, models, handoffs=handoffs, run_id=run_id, attempt_id=1
    )


def _legacy_ku(db, models, *, profile_id: int, url: str, statement: str, fingerprint: str):
    """A production-shaped pre-C1 row: content-derived id + provenance for the URL."""
    ku = models.KnowledgeUnit(
        canonical_unit_id=f"ku-w6p01-{fingerprint[:16]}",
        immutable_version_id="v1",
        domain="oncology",
        topic_taxonomy="cancer",
        language="en",
        knowledge_type="OTHER",
        normalized_statement=statement,
        applicability="candidate_only_not_approved_knowledge",
        evidence_strength="UNKNOWN",
        medical_safety_state="PENDING_REVIEW",
        conflict_state="NONE",
        freshness_state="UNKNOWN",
        review_state="NOT_REVIEWED",
        publication_state="DRAFT",
        runtime_eligibility="NOT_ELIGIBLE",
        provenance_complete=True,
        deduplication_key=_sha(f"legacy-dedupe-{fingerprint}"),
        canonical_hash=_sha(f"legacy-canon-{fingerprint}"),
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
    raw = models.I5RawEvidence(
        source_profile_id=profile_id,
        canonical_url=url,
        content_hash=fingerprint,
        byte_hash=fingerprint,
        hash_algorithm="SHA-256",
        retrieval_timestamp=datetime(2026, 9, 1, 0, 0, 0),
        retention_mode="RAW_MINIMAL_EVIDENCE_ONLY",
        storage_mode="NONE",
        rights_terms_state="APPROVED",
        robots_access_state="ALLOWED",
    )
    db.add(raw)
    db.flush()
    db.add(
        models.KnowledgeProvenance(
            knowledge_unit_id=int(ku.id),
            source_profile_id=profile_id,
            raw_evidence_id=int(raw.id),
            retrieval_method="PUBLIC_WEB_FETCH_HTTPS",
        )
    )
    db.flush()
    return ku


STATEMENT = "cancer acute lymphoblastic leukemia see acute lymphocytic leukemia"


def test_b4a_same_statement_with_drifted_dedupe_and_page_hash_reuses_current_version(db) -> None:
    _require_postgres(db)
    models = _models()
    profile_id, run_id = _setup(db, models, "drift")
    url = "https://medlineplus.gov/b4a-drift.html"

    first = _persist(db, models, run_id, _handoffs(
        profile_id=profile_id, url=url, statement=STATEMENT, page_token="page-1",
        dedupe_key=_sha("dedupe-old"), canonical_hash=_sha("canon-old"),
    ))
    again = _persist(db, models, run_id, _handoffs(
        profile_id=profile_id, url=url, statement=STATEMENT, page_token="page-2",
        dedupe_key=_sha("dedupe-new"), canonical_hash=_sha("canon-new"),
    ))

    assert first.document_failures == [] and again.document_failures == []
    assert again.knowledge_unit_ids == first.knowledge_unit_ids
    assert again.new_knowledge_count == 0
    assert again.superseded_knowledge_unit_ids == []
    identity = runtime.stable_document_identity(profile_id, url)
    assert db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=identity).count() == 1


def test_b4a_legacy_fingerprint_identity_is_adopted_and_reused(db) -> None:
    _require_postgres(db)
    models = _models()
    profile_id, run_id = _setup(db, models, "legacy-same")
    url = "https://medlineplus.gov/b4a-legacy-same.html"
    legacy = _legacy_ku(db, models, profile_id=profile_id, url=url, statement=STATEMENT, fingerprint=_sha("lp1"))

    result = _persist(db, models, run_id, _handoffs(
        profile_id=profile_id, url=url, statement=STATEMENT, page_token="lp1-refetch",
        dedupe_key=_sha("lp1-new-dedupe"), canonical_hash=_sha("lp1-new-canon"),
    ))

    assert result.document_failures == []
    assert result.knowledge_unit_ids == [legacy.id]
    assert result.new_knowledge_count == 0
    assert db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=legacy.canonical_unit_id).count() == 1


def test_b4a_legacy_identity_with_changed_statement_opens_v2_under_same_id(db) -> None:
    _require_postgres(db)
    models = _models()
    profile_id, run_id = _setup(db, models, "legacy-changed")
    url = "https://medlineplus.gov/b4a-legacy-changed.html"
    legacy = _legacy_ku(db, models, profile_id=profile_id, url=url, statement=STATEMENT, fingerprint=_sha("lp2"))
    changed = "acute lymphocytic leukemia is a cancer of the blood and bone marrow"

    result = _persist(db, models, run_id, _handoffs(
        profile_id=profile_id, url=url, statement=changed, page_token="lp2-changed",
        dedupe_key=_sha("lp2-changed-dedupe"), canonical_hash=_sha("lp2-changed-canon"),
    ))

    assert result.document_failures == []
    assert result.superseded_knowledge_unit_ids == [legacy.id]
    v2 = db.query(models.KnowledgeUnit).filter_by(id=result.knowledge_unit_ids[0]).one()
    db.refresh(legacy)
    assert (v2.canonical_unit_id, v2.immutable_version_id) == (legacy.canonical_unit_id, "v2")
    assert v2.supersedes_unit_id == legacy.id
    assert legacy.publication_state == "SUPERSEDED"
    assert legacy.runtime_eligibility == "NOT_ELIGIBLE"


def test_b4a_new_identity_inserts_v1_with_stable_source_url_id(db) -> None:
    _require_postgres(db)
    models = _models()
    profile_id, run_id = _setup(db, models, "new")
    url = "https://medlineplus.gov/b4a-new.html"

    result = _persist(db, models, run_id, _handoffs(
        profile_id=profile_id, url=url, statement=STATEMENT + " new", page_token="n1",
        dedupe_key=_sha("n1-dedupe"), canonical_hash=_sha("n1-canon"),
    ))

    assert result.new_knowledge_count == 1
    ku = db.query(models.KnowledgeUnit).filter_by(id=result.knowledge_unit_ids[0]).one()
    assert ku.canonical_unit_id == runtime.stable_document_identity(profile_id, url)
    assert ku.immutable_version_id == "v1"
    assert ku.deduplication_key == _sha("n1-dedupe")


def test_b4a_ambiguous_legacy_identities_fail_closed_for_that_document_only(db) -> None:
    _require_postgres(db)
    models = _models()
    profile_id, run_id = _setup(db, models, "ambiguous")
    url = "https://medlineplus.gov/b4a-ambiguous.html"
    other_url = "https://medlineplus.gov/b4a-ambiguous-other.html"
    # Two pre-C1 content ids for one URL (RISK-002 shape in production).
    _legacy_ku(db, models, profile_id=profile_id, url=url, statement=STATEMENT, fingerprint=_sha("amb1"))
    _legacy_ku(db, models, profile_id=profile_id, url=url, statement=STATEMENT + " v", fingerprint=_sha("amb2"))
    ku_before = db.query(models.KnowledgeUnit).count()

    result = _persist(
        db,
        models,
        run_id,
        _handoffs(
            profile_id=profile_id, url=url, statement="new wording", page_token="amb3",
            dedupe_key=_sha("amb3-dedupe"), canonical_hash=_sha("amb3-canon"),
        )
        + _handoffs(
            profile_id=profile_id, url=other_url, statement="other page", page_token="amb4",
            dedupe_key=_sha("amb4-dedupe"), canonical_hash=_sha("amb4-canon"),
        ),
    )

    assert [(f["canonical_url"], f["code"]) for f in result.document_failures] == [
        (url, "KU_DOCUMENT_IDENTITY_AMBIGUOUS")
    ]
    assert result.new_knowledge_count == 1
    assert db.query(models.KnowledgeUnit).count() == ku_before + 1
