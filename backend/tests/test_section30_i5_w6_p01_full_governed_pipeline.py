"""Section 30 / I5-IMPL-W6-P01 — full governed pipeline proof (Master Gate).

Covers extraction integration, fail-closed retention, DB source loading,
deterministic weekly identity, advisory-lock behavior, governed persistence,
publication only through the governed low-risk manifest path, 81-C2 version
lifecycle, and no unauthorized Knowledge Memory write.
"""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime
from typing import Any, Mapping, Optional

import pytest
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5 import governed_weekly_runtime as runtime
from backend.app.services.i5 import weekly_orchestrator as orch
from backend.app.services.i5.adapters.base import AdapterFrameworkError
from backend.app.services.i5.conceptual_extraction import extract_candidates
from backend.app.services.i5.normalization import normalize_document
from backend.app.schemas.i5_adapters import FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.source_discovery import SourceCandidateDescriptor


def _load_models():
    return importlib.import_module("backend.app.models")


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for governed pipeline DB nodes")


def _ok_gov(**overrides) -> SourceGovernanceSnapshot:
    base = dict(
        source_profile_id=1,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="OGL",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="nhs.uk",
    )
    base.update(overrides)
    return SourceGovernanceSnapshot(**base)


def _html_envelope(body: bytes = b"<html><title>Sleep</title><body><p>Sleep tips and tiredness guidance for adults from NHS live well pages.</p></body></html>") -> FetchEnvelope:
    return FetchEnvelope(
        request_id="t",
        adapter_id="i5.public_web_fetch",
        adapter_version="1",
        canonical_url=runtime.NHS_SLEEP_URL,
        final_url=runtime.NHS_SLEEP_URL,
        http_status=200,
        content_type="text/html",
        charset="utf-8",
        body=body,
        byte_count=len(body),
        content_hash=hashlib.sha256(body).hexdigest(),
        retrieved_at=datetime(2026, 8, 8, 0, 0, 0),
        disposition="OK",
        error_category=None,
    )


def test_W6P01_FG01_extraction_integration_and_candidate_semantics() -> None:
    envelope = _html_envelope()
    cands = extract_candidates(envelope, mode="PUBLIC_WEB_FETCH")
    assert len(cands) > 0
    assert "candidate_only_not_approved_knowledge" in cands[0].warnings
    norm = normalize_document(
        raw_text=cands[0].normalized_text,
        domain="lifestyle",
        topic="sleep",
        jurisdiction="GB",
    )
    assert norm.content_hash
    assert norm.dedupe_key


def test_W6P01_FG02_retention_fail_closed_unknown_rights() -> None:
    with pytest.raises(runtime.GovernedWeeklyRuntimeError) as exc:
        runtime.map_fetch_rights_to_retention(
            rights_terms_state="UNKNOWN",
            robots_access_state="ALLOWED",
        )
    assert exc.value.code == "RETENTION_RIGHTS_FAIL_CLOSED"


def test_W6P01_FG03_retention_ogl_maps_to_minimal_evidence() -> None:
    retention, storage, rights, robots = runtime.map_fetch_rights_to_retention(
        rights_terms_state="OGL",
        robots_access_state="ALLOWED",
    )
    assert retention == "RAW_MINIMAL_EVIDENCE_ONLY"
    assert storage == "NONE"
    assert rights == "APPROVED"
    assert robots == "ALLOWED"


def test_W6P01_FG04_deterministic_weekly_window_stable() -> None:
    a = datetime(2026, 8, 8, 1, 2, 3, 456789)
    b = datetime(2026, 8, 8, 23, 59, 59, 1)
    w1 = runtime.deterministic_weekly_window(a)
    w2 = runtime.deterministic_weekly_window(b)
    assert w1 == w2
    assert (w1[1] - w1[0]).days == 7
    # Next distinct week differs.
    w3 = runtime.deterministic_weekly_window(datetime(2026, 8, 15, 0, 0, 1))
    assert w3[0] != w1[0]


def test_W6P01_FG05_same_window_logical_run_key_stable() -> None:
    cand = SourceCandidateDescriptor(
        source_profile_id=7,
        adapter_mode="PUBLIC_WEB_FETCH",
        url=runtime.NHS_SLEEP_URL,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="OGL",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="nhs.uk",
    )
    k1, s1, e1, _ = runtime.build_scheduled_logical_identity(
        candidates=[cand], now=datetime(2026, 8, 8, 3, 0, 0)
    )
    k2, s2, e2, _ = runtime.build_scheduled_logical_identity(
        candidates=[cand], now=datetime(2026, 8, 8, 18, 0, 0)
    )
    assert k1 == k2 and s1 == s2 and e1 == e2
    k3, *_ = runtime.build_scheduled_logical_identity(
        candidates=[cand], now=datetime(2026, 8, 15, 3, 0, 0)
    )
    assert k3 != k1


def test_W6P01_FG06_live_apply_requires_real_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.services.i5.source_discovery import build_discovery_work_item

    body = (
        b"<html><title>Sleep</title><body>"
        b"<p>Enough visible medical guidance text for extraction threshold.</p>"
        b"</body></html>"
    )

    class _Resp:
        status_code = 200
        content = body
        headers = {"Content-Type": "text/html; charset=utf-8"}
        text = body.decode()

    def _get(*_a, **_k):
        return _Resp()

    monkeypatch.setattr(
        "backend.app.services.gate3.fetch_security.socket.getaddrinfo",
        lambda *_a, **_k: [(0, 0, 0, "", ("93.184.216.34", 0))],
    )
    monkeypatch.setattr(
        "backend.app.services.gate3.robots_checker.requests.get",
        lambda *_a, **_k: type("R", (), {"status_code": 200, "text": "User-agent: *\nAllow: /\n"})(),
    )
    work = build_discovery_work_item(
        SourceCandidateDescriptor(
            source_profile_id=1,
            adapter_mode="PUBLIC_WEB_FETCH",
            url="https://www.nhs.uk/live-well/sleep-and-tiredness/",
            registry_state="ACTIVE",
            runtime_eligibility="ELIGIBLE",
            rights_terms_state="OGL",
            robots_access_state="ALLOWED",
            rate_limit_policy="DEFINED",
            allowed_domain="nhs.uk",
        )
    )
    status, code, handoffs = orch._apply_live_source(work=work, http_get=_get)
    assert status == "EXTRACTED"
    assert code is None
    assert any(h.handoff_kind == "CANDIDATE" for h in handoffs)
    cand = next(h for h in handoffs if h.handoff_kind == "CANDIDATE")
    assert cand.payload.get("normalized_statement")
    assert "candidate_only_not_approved_knowledge" in (cand.payload.get("candidate_warnings") or [])


def test_W6P01_FG07_activation_loader_and_persistence(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()

    activation = runtime.activate_nhs_sleep_source(db, models)
    assert activation.source_fetch_enabled is True
    assert activation.governed_source_profile_id > 0

    # Idempotent second activation.
    activation2 = runtime.activate_nhs_sleep_source(db, models)
    assert activation2.knowledge_source_id == activation.knowledge_source_id
    assert activation2.governed_source_profile_id == activation.governed_source_profile_id

    candidates = runtime.load_controlled_weekly_candidates(db, models)
    assert len(candidates) == 1
    assert candidates[0].url == runtime.NHS_SLEEP_URL
    assert candidates[0].source_profile_id == activation.governed_source_profile_id

    body = (
        b"<html><title>Sleep</title><body>"
        b"<p>Enough visible medical guidance text for extraction threshold on NHS sleep page.</p>"
        b"</body></html>"
    )

    class _Resp:
        status_code = 200
        content = body
        headers = {"Content-Type": "text/html; charset=utf-8"}
        text = body.decode()

    def _get(*_a, **_k):
        return _Resp()

    import os

    os.environ[orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV] = "true"
    os.environ[orch.SOURCE_ACTIVATION_ENV] = "true"
    try:
        # Patch robots/DNS for injected transport path.
        import backend.app.services.gate3.fetch_security as fs
        import backend.app.services.gate3.robots_checker as rc

        old_dns = fs.socket.getaddrinfo
        old_robots = rc.requests.get
        fs.socket.getaddrinfo = lambda *_a, **_k: [(0, 0, 0, "", ("93.184.216.34", 0))]
        rc.requests.get = lambda *_a, **_k: type(
            "R", (), {"status_code": 200, "text": "User-agent: *\nAllow: /\n"}
        )()
        try:
            outcome = runtime.run_weekly_scheduled_job(
                db,
                models,
                candidates=candidates,
                persist_ledger=True,
                live_http_get=_get,
                acquire_lock=True,
                now=datetime(2026, 8, 8, 12, 0, 0),
            )
        finally:
            fs.socket.getaddrinfo = old_dns
            rc.requests.get = old_robots
    finally:
        os.environ.pop(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, None)
        os.environ.pop(orch.SOURCE_ACTIVATION_ENV, None)

    assert outcome.network_executed is True
    assert outcome.production_write is True
    assert outcome.run_id is not None
    # Orchestrator appends "|autonomous_governance_side_stage=..." (since 7455bacb).
    assert outcome.detail.startswith("governed_raw_ku_provenance_persisted")

    raw_count = db.query(models.I5RawEvidence).count()
    ku_count = db.query(models.KnowledgeUnit).count()
    prov_count = db.query(models.KnowledgeProvenance).count()
    mem_count = db.query(models.KnowledgeMemoryItem).count()
    assert raw_count >= 1
    assert ku_count >= 1
    assert prov_count >= 1
    assert mem_count == 0

    # Publication happens only through the governed low-risk manifest path
    # (NHS live-well is governed_low_risk_eligibility: YES). Non-manifest sources stay
    # unpublished — see FG11.
    from backend.app.services.i5.trusted_source_manifest import governed_low_risk_eligible

    assert governed_low_risk_eligible(runtime.NHS_SOURCE_KEY) is True
    ku = db.query(models.KnowledgeUnit).order_by(models.KnowledgeUnit.id.desc()).first()
    assert ku.provenance_complete is True
    assert ku.medical_safety_state == "CLEARED"
    assert ku.review_state == "APPROVED"
    assert ku.publication_state == "PUBLISHED"
    assert ku.freshness_state == "CURRENT"
    assert ku.runtime_eligibility == "ELIGIBLE"

    # Same-window idempotent re-entry: no second fetch.
    os.environ[orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV] = "true"
    os.environ[orch.SOURCE_ACTIVATION_ENV] = "true"
    try:
        outcome2 = runtime.run_weekly_scheduled_job(
            db,
            models,
            candidates=candidates,
            persist_ledger=True,
            live_http_get=_get,
            acquire_lock=True,
            now=datetime(2026, 8, 8, 18, 0, 0),
        )
    finally:
        os.environ.pop(orch.WEEKLY_ORCHESTRATOR_ENABLE_ENV, None)
        os.environ.pop(orch.SOURCE_ACTIVATION_ENV, None)
    assert outcome2.network_executed is False
    assert outcome2.detail.startswith("ALREADY_SUCCESSFUL_TERMINAL")
    assert outcome2.run_id == outcome.run_id
    assert db.query(models.KnowledgeUnit).count() == ku_count


def _sha(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


class _Handoff:
    def __init__(self, kind: str, key: str, payload: dict) -> None:
        self.handoff_kind = kind
        self.request_key = key
        self.payload = payload
        self.execute = False


def _identity_handoffs(
    *,
    source_profile_id: int,
    canonical_url: str,
    statement: str,
    content_token: str,
    section_key: str = "",
) -> list[_Handoff]:
    content_hash = _sha(content_token)
    canon = _sha(statement)
    raw_key = f"raw-{content_hash[:12]}"
    fingerprint = content_hash
    shared = {
        "section_key": section_key,
        "source_profile_id": source_profile_id,
        "canonical_url": canonical_url,
        "rights_terms_state": "OGL",
        "robots_access_state": "ALLOWED",
        "content_sha256": content_hash,
        "byte_hash": content_hash,
        "normalized_hash": canon,
        "normalized_statement": statement,
        "candidate_fingerprint": fingerprint,
        "dedupe_key": canon,
        "canonical_hash": canon,
        "domain": "lifestyle",
        "topic": "sleep",
        "language": "en",
        "jurisdiction": "GB",
        "retrieval_method": "PUBLIC_WEB_FETCH_HTTPS",
        "raw_evidence_request_key": raw_key,
    }
    return [
        _Handoff("RAW_EVIDENCE", raw_key, dict(shared)),
        _Handoff("CANDIDATE", f"cand-{content_hash[:12]}", dict(shared)),
        _Handoff("PROVENANCE", f"prov-{content_hash[:12]}", dict(shared)),
    ]


def test_W6P01_FG08_stable_source_url_identity(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    activation = runtime.activate_nhs_sleep_source(db, models)
    profile_id = int(activation.governed_source_profile_id)
    url = "https://www.nhs.uk/live-well/sleep-and-tiredness/k81c-identity"
    other_url = "https://www.nhs.uk/live-well/sleep-and-tiredness/k81c-other"
    run = models.WeeklyKnowledgeRun(
        logical_run_key=_sha("k81c-identity-run"),
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
    mem_before = db.query(models.KnowledgeMemoryItem).count()
    statement = "Sleep regularity is general lifestyle guidance for this identity fixture."
    first = runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=profile_id,
            canonical_url=url,
            statement=statement,
            content_token="body-a",
        ),
        run_id=int(run.id),
        attempt_id=1,
    )
    again = runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=profile_id,
            canonical_url=url,
            statement=statement,
            content_token="body-a",
        ),
        run_id=int(run.id),
        attempt_id=1,
    )
    assert first.knowledge_unit_ids == again.knowledge_unit_ids
    assert len(set(first.knowledge_unit_ids)) == 1
    ku = db.query(models.KnowledgeUnit).filter_by(id=first.knowledge_unit_ids[0]).one()
    expected = runtime.stable_document_identity(profile_id, url)
    assert ku.canonical_unit_id == expected
    assert ku.immutable_version_id == "v1"
    assert expected not in statement
    raw = db.query(models.I5RawEvidence).filter_by(id=first.raw_evidence_ids[0]).one()
    prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).one()
    assert raw.source_document_id == expected
    assert prov.source_document_id == expected
    assert raw.source_document_id != raw.content_hash
    raw.source_document_id = None
    prov.source_document_id = None
    db.flush()
    runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=profile_id,
            canonical_url=url,
            statement=statement,
            content_token="body-a",
        ),
        run_id=int(run.id),
        attempt_id=1,
    )
    db.refresh(raw)
    db.refresh(prov)
    assert raw.source_document_id == expected
    assert prov.source_document_id == expected
    assert db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=expected).count() == 1

    # 81-C2: changed content keeps the logical identity and opens the next version.
    changed = "Sleep regularity guidance wording changed for the same source page."
    changed_result = runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=profile_id,
            canonical_url=url,
            statement=changed,
            content_token="body-b",
        ),
        run_id=int(run.id),
        attempt_id=2,
    )
    assert changed_result.document_failures == []
    assert changed_result.superseded_knowledge_unit_ids == [int(ku.id)]
    assert db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=expected).count() == 2
    v2 = db.query(models.KnowledgeUnit).filter_by(id=changed_result.knowledge_unit_ids[0]).one()
    assert v2.canonical_unit_id == expected
    assert v2.immutable_version_id == "v2"
    assert v2.supersedes_unit_id == ku.id
    db.refresh(ku)
    assert ku.canonical_unit_id == expected
    assert ku.publication_state == "SUPERSEDED"

    other = runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=profile_id,
            canonical_url=other_url,
            statement=statement,
            content_token="body-c",
        ),
        run_id=int(run.id),
        attempt_id=3,
    )
    other_ku = db.query(models.KnowledgeUnit).filter_by(id=other.knowledge_unit_ids[0]).one()
    assert other_ku.canonical_unit_id == runtime.stable_document_identity(profile_id, other_url)
    assert other_ku.canonical_unit_id != ku.canonical_unit_id

    alt = models.GovernedSourceProfile(
        canonical_key="k81c-alt-source",
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        canonicalization_version="v1",
    )
    db.add(alt)
    db.flush()
    alt_result = runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=int(alt.id),
            canonical_url=url,
            statement=statement,
            content_token="body-d",
        ),
        run_id=int(run.id),
        attempt_id=4,
    )
    alt_ku = db.query(models.KnowledgeUnit).filter_by(id=alt_result.knowledge_unit_ids[0]).one()
    assert alt_ku.canonical_unit_id == runtime.stable_document_identity(int(alt.id), url)
    assert alt_ku.canonical_unit_id != ku.canonical_unit_id
    alt_raw = db.query(models.I5RawEvidence).filter_by(id=alt_result.raw_evidence_ids[0]).one()
    assert alt_raw.source_document_id == alt_ku.canonical_unit_id
    assert alt_raw.source_document_id != raw.content_hash

    decoy_nested = db.begin_nested()
    try:
        decoy_hash = _sha("decoy-canonical")
        decoy = models.KnowledgeUnit(
            canonical_unit_id=decoy_hash,
            immutable_version_id="v1",
            domain="lifestyle",
            language="en",
            knowledge_type="OTHER",
            normalized_statement="A second logical identity for the same page.",
            evidence_strength="UNKNOWN",
            medical_safety_state="PENDING_REVIEW",
            conflict_state="NONE",
            freshness_state="UNKNOWN",
            review_state="NOT_REVIEWED",
            publication_state="DRAFT",
            runtime_eligibility="NOT_ELIGIBLE",
            provenance_complete=False,
            deduplication_key=_sha("decoy-dedupe"),
            canonical_hash=_sha("decoy-canon-hash"),
            hash_algorithm="SHA-256",
            canonicalization_version="v1",
        )
        db.add(decoy)
        db.flush()
        decoy_raw = models.I5RawEvidence(
            source_profile_id=profile_id,
            source_document_id=expected,
            canonical_url=url,
            content_hash=_sha("decoy-body"),
            byte_hash=_sha("decoy-body"),
            hash_algorithm="SHA-256",
            retrieval_timestamp=datetime(2026, 8, 9, 0, 0, 0),
            retention_mode="RAW_MINIMAL_EVIDENCE_ONLY",
            storage_mode="NONE",
            rights_terms_state="APPROVED",
            robots_access_state="ALLOWED",
        )
        db.add(decoy_raw)
        db.flush()
        db.add(
            models.KnowledgeProvenance(
                knowledge_unit_id=int(decoy.id),
                source_profile_id=profile_id,
                source_document_id=expected,
                raw_evidence_id=int(decoy_raw.id),
                retrieval_method="PUBLIC_WEB_FETCH_HTTPS",
            )
        )
        db.flush()
        ku_rows_before = db.query(models.KnowledgeUnit).count()
        ambiguous = runtime.execute_governed_persistence(
            db,
            models,
            handoffs=_identity_handoffs(
                source_profile_id=profile_id,
                canonical_url=url,
                statement="Yet another wording for the ambiguous page.",
                content_token="body-e",
            ),
            run_id=int(run.id),
            attempt_id=5,
        )
        # Fail closed for this document only: recorded, nothing written, no raise.
        assert [f["code"] for f in ambiguous.document_failures] == ["KU_DOCUMENT_IDENTITY_AMBIGUOUS"]
        assert ambiguous.knowledge_unit_ids == []
        assert db.query(models.KnowledgeUnit).count() == ku_rows_before
    finally:
        decoy_nested.rollback()
    assert db.query(models.KnowledgeMemoryItem).count() == mem_before
    assert first.knowledge_memory_writes == 0


# ---------------------------------------------------------------------------
# 81-C2 — changed-content supersession inside the canonical weekly persistence.
# ---------------------------------------------------------------------------


def _governed_run(db, models, key: str):
    run = models.WeeklyKnowledgeRun(
        logical_run_key=_sha(key),
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
    return run


def _plain_source(db, models, canonical_key: str) -> int:
    """Governed profile outside the low-risk manifest (no lexical indexing side effects)."""
    gsp = models.GovernedSourceProfile(
        canonical_key=canonical_key,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        canonicalization_version="v1",
    )
    db.add(gsp)
    db.flush()
    return int(gsp.id)


def _persist(db, models, run, *, profile_id: int, url: str, statement: str, token: str, **kw):
    return runtime.execute_governed_persistence(
        db,
        models,
        handoffs=_identity_handoffs(
            source_profile_id=profile_id,
            canonical_url=url,
            statement=statement,
            content_token=token,
            **kw,
        ),
        run_id=int(run.id),
        attempt_id=1,
    )


def _versions(db, models, canonical_unit_id: str):
    return (
        db.query(models.KnowledgeUnit)
        .filter_by(canonical_unit_id=canonical_unit_id)
        .order_by(models.KnowledgeUnit.id)
        .all()
    )


def _serving_kce(db, models, knowledge_unit_id: int):
    return (
        db.query(models.KnowledgeChunkEmbedding)
        .filter(
            models.KnowledgeChunkEmbedding.knowledge_unit_id == int(knowledge_unit_id),
            models.KnowledgeChunkEmbedding.retracted_at.is_(None),
        )
        .all()
    )


def test_W6P01_FG09_c2_pure_helpers() -> None:
    # Document identity is unchanged from 81-C1; sections get their own identity.
    assert runtime.stable_document_identity(7, " https://x/a ") == _sha("7|https://x/a")
    assert runtime.stable_document_identity(7, "https://x/a", "") == _sha("7|https://x/a")
    sec = runtime.stable_document_identity(7, "https://x/a", "h2:symptoms")
    assert sec == _sha("7|https://x/a|h2:symptoms")
    assert sec != runtime.stable_document_identity(7, "https://x/a", "h2:treatment")
    assert len(sec) == 64

    assert runtime._version_number("v1") == 1
    assert runtime._version_number("v12") == 12
    for bad in ("", "1", "v0", "v-1", "vX", "version2"):
        with pytest.raises(runtime.GovernedWeeklyRuntimeError) as exc:
            runtime._version_number(bad)
        assert exc.value.code == "KU_VERSION_ID_UNPARSEABLE"

    class _Ku:
        normalized_statement = "Adults need 7 to 9 hours of sleep."

    assert runtime._served_statement_changed(_Ku(), "Adults need 7 to 9 hours of sleep. ") is False
    assert runtime._served_statement_changed(_Ku(), "Adults need 8 hours of sleep.") is True

    k2 = runtime._version_dedupe_key("cid", "v2")
    assert k2 == runtime._version_dedupe_key("cid", "v2")
    assert k2 != runtime._version_dedupe_key("cid", "v3")
    assert k2 != runtime._version_dedupe_key("other", "v2")

    a = _identity_handoffs(source_profile_id=1, canonical_url="https://x/a", statement="s", content_token="a")
    b = _identity_handoffs(source_profile_id=1, canonical_url="https://x/b", statement="s", content_token="b")
    c = _identity_handoffs(source_profile_id=2, canonical_url="https://x/a", statement="s", content_token="c")
    groups = runtime._group_handoffs_by_document(a + b + c + a[:1])
    assert [len(g) for g in groups] == [4, 3, 3]


def test_W6P01_FG10_c2_changed_content_supersession_lifecycle(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    activation = runtime.activate_nhs_sleep_source(db, models)
    profile_id = int(activation.governed_source_profile_id)
    run = _governed_run(db, models, "k81c2-lifecycle-run")
    url = "https://www.nhs.uk/live-well/sleep-and-tiredness/k81c2-lifecycle"
    identity = runtime.stable_document_identity(profile_id, url)
    mem_before = db.query(models.KnowledgeMemoryItem).count()
    a = "Most adults need between 7 and 9 hours of sleep every night."
    b = "Most adults need 7 or more hours of sleep every night for good health."

    first = _persist(db, models, run, profile_id=profile_id, url=url, statement=a, token="page-a1")
    assert first.document_failures == []
    v1 = db.query(models.KnowledgeUnit).filter_by(id=first.knowledge_unit_ids[0]).one()
    assert (v1.canonical_unit_id, v1.immutable_version_id) == (identity, "v1")
    v1_eligibility = v1.runtime_eligibility
    if v1_eligibility == "ELIGIBLE":
        assert len(_serving_kce(db, models, v1.id)) > 0

    # Same served statement, different page bytes (chrome/date change) -> NO_CHANGE.
    same = _persist(db, models, run, profile_id=profile_id, url=url, statement=a, token="page-a2")
    assert same.document_failures == []
    assert same.knowledge_unit_ids == [v1.id]
    assert same.superseded_knowledge_unit_ids == []
    assert same.new_knowledge_count == 0
    assert len(_versions(db, models, identity)) == 1

    # Changed statement -> v2 supersedes v1 atomically.
    changed = _persist(db, models, run, profile_id=profile_id, url=url, statement=b, token="page-b1")
    assert changed.document_failures == []
    assert changed.superseded_knowledge_unit_ids == [v1.id]
    assert changed.new_knowledge_count == 0
    v2 = db.query(models.KnowledgeUnit).filter_by(id=changed.knowledge_unit_ids[0]).one()
    db.refresh(v1)
    assert (v2.canonical_unit_id, v2.immutable_version_id) == (identity, "v2")
    assert v2.supersedes_unit_id == v1.id
    assert v2.normalized_statement == b
    assert v2.provenance_complete is True
    v1_prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=v1.id).one()
    v2_prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=v2.id).one()
    assert v2_prov.source_document_id == identity
    assert v2_prov.raw_evidence_id != v1_prov.raw_evidence_id
    assert v1.publication_state == "SUPERSEDED"
    assert v1.freshness_state == "STALE"
    assert v1.runtime_eligibility == "NOT_ELIGIBLE"
    assert _serving_kce(db, models, v1.id) == []
    # The new version goes through the same governed eligibility as v1 did.
    assert v2.runtime_eligibility == v1_eligibility
    if v1_eligibility == "ELIGIBLE":
        assert len(_serving_kce(db, models, v2.id)) > 0
    open_versions = [
        k for k in _versions(db, models, identity) if k.publication_state not in {"SUPERSEDED", "WITHDRAWN"}
    ]
    assert [k.id for k in open_versions] == [v2.id]

    # Re-run of the changed page is idempotent.
    again = _persist(db, models, run, profile_id=profile_id, url=url, statement=b, token="page-b1")
    assert again.knowledge_unit_ids == [v2.id]
    assert len(_versions(db, models, identity)) == 2

    # Content reverts to the original wording -> v3 (no dedupe collision with v1).
    reverted = _persist(db, models, run, profile_id=profile_id, url=url, statement=a, token="page-a3")
    assert reverted.document_failures == []
    assert reverted.superseded_knowledge_unit_ids == [v2.id]
    v3 = db.query(models.KnowledgeUnit).filter_by(id=reverted.knowledge_unit_ids[0]).one()
    db.refresh(v2)
    assert (v3.immutable_version_id, v3.supersedes_unit_id) == ("v3", v2.id)
    assert v3.deduplication_key != v1.deduplication_key
    assert v2.publication_state == "SUPERSEDED"
    assert _serving_kce(db, models, v2.id) == []
    serving_ids = {
        row.knowledge_unit_id
        for k in _versions(db, models, identity)
        for row in _serving_kce(db, models, k.id)
    }
    assert serving_ids <= {v3.id}

    # Different URL with identical text keeps its own identity (no cross-identity reuse).
    other_url = url + "-mirror"
    other = _persist(db, models, run, profile_id=profile_id, url=other_url, statement=a, token="page-m1")
    other_ku = db.query(models.KnowledgeUnit).filter_by(id=other.knowledge_unit_ids[0]).one()
    assert other_ku.canonical_unit_id == runtime.stable_document_identity(profile_id, other_url)
    assert other_ku.id not in {v1.id, v2.id, v3.id}

    # No Knowledge Memory writes (I7/I8 boundary unchanged).
    assert db.query(models.KnowledgeMemoryItem).count() == mem_before


def test_W6P01_FG11_c2_document_isolation_and_fail_closed(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    profile_id = _plain_source(db, models, "k81c2-isolation-source")
    run = _governed_run(db, models, "k81c2-isolation-run")
    good_url = "https://example.org/k81c2/good"
    multi_url = "https://example.org/k81c2/multi-current"
    multi_identity = runtime.stable_document_identity(profile_id, multi_url)

    seeded = _persist(db, models, run, profile_id=profile_id, url=multi_url, statement="Seed v1.", token="m1")
    seed_v1 = db.query(models.KnowledgeUnit).filter_by(id=seeded.knowledge_unit_ids[0]).one()
    # Corrupt the chain on purpose: a second open version for the same identity.
    rogue = models.KnowledgeUnit(
        canonical_unit_id=multi_identity,
        immutable_version_id="v2",
        domain="lifestyle",
        language="en",
        knowledge_type="OTHER",
        normalized_statement="Rogue open version.",
        evidence_strength="UNKNOWN",
        medical_safety_state="PENDING_REVIEW",
        conflict_state="NONE",
        freshness_state="UNKNOWN",
        review_state="NOT_REVIEWED",
        publication_state="DRAFT",
        runtime_eligibility="NOT_ELIGIBLE",
        provenance_complete=False,
        deduplication_key=_sha("k81c2-rogue-dedupe"),
        canonical_hash=_sha("k81c2-rogue-canon"),
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(rogue)
    db.flush()
    ku_rows_before = db.query(models.KnowledgeUnit).count()

    handoffs = _identity_handoffs(
        source_profile_id=profile_id, canonical_url=multi_url, statement="New text.", content_token="m2"
    ) + _identity_handoffs(
        source_profile_id=profile_id, canonical_url=good_url, statement="Good document text.", content_token="g1"
    )
    result = runtime.execute_governed_persistence(
        db, models, handoffs=handoffs, run_id=int(run.id), attempt_id=2
    )
    # The broken document fails closed alone; the good one is persisted in the same call.
    assert [(f["canonical_url"], f["code"]) for f in result.document_failures] == [
        (multi_url, "KU_MULTIPLE_CURRENT_VERSIONS")
    ]
    assert result.new_knowledge_count == 1
    good = db.query(models.KnowledgeUnit).filter_by(id=result.knowledge_unit_ids[0]).one()
    assert good.canonical_unit_id == runtime.stable_document_identity(profile_id, good_url)
    # Source outside the low-risk manifest: never auto-published.
    assert good.publication_state != "PUBLISHED"
    assert good.runtime_eligibility != "ELIGIBLE"
    assert db.query(models.KnowledgeUnit).count() == ku_rows_before + 1
    db.refresh(seed_v1)
    assert seed_v1.publication_state != "SUPERSEDED"
    assert all(h.execute is False for h in handoffs[:3])
    assert all(h.execute is True for h in handoffs[3:])

    # Section identity is honoured and independent of the document identity.
    sectioned = _persist(
        db,
        models,
        run,
        profile_id=profile_id,
        url=good_url,
        statement="Section text.",
        token="g-sec",
        section_key="h2:causes",
    )
    sec_ku = db.query(models.KnowledgeUnit).filter_by(id=sectioned.knowledge_unit_ids[0]).one()
    assert sec_ku.canonical_unit_id == runtime.stable_document_identity(profile_id, good_url, "h2:causes")
    assert sec_ku.immutable_version_id == "v1"


def test_W6P01_FG12_c2_failed_change_retires_old_version_stale(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    profile_id = _plain_source(db, models, "k81c2-stale-source")
    run = _governed_run(db, models, "k81c2-stale-run")
    url = "https://example.org/k81c2/stale"
    identity = runtime.stable_document_identity(profile_id, url)

    first = _persist(db, models, run, profile_id=profile_id, url=url, statement="Original text.", token="s1")
    v1 = db.query(models.KnowledgeUnit).filter_by(id=first.knowledge_unit_ids[0]).one()

    real_finalize = runtime.apply_governed_finalize_and_lexical_index

    def _boom(*_a, **_k):
        raise RuntimeError("simulated lifecycle failure")

    monkeypatch.setattr(runtime, "apply_governed_finalize_and_lexical_index", _boom)
    failed = _persist(db, models, run, profile_id=profile_id, url=url, statement="Changed text.", token="s2")
    monkeypatch.setattr(runtime, "apply_governed_finalize_and_lexical_index", real_finalize)

    # Whole document rolled back (no v2), and the known-outdated v1 can no longer serve.
    assert [f["code"] for f in failed.document_failures] == ["RuntimeError"]
    assert failed.stale_retired_knowledge_unit_ids == [v1.id]
    assert failed.knowledge_unit_ids == []
    assert [k.immutable_version_id for k in _versions(db, models, identity)] == ["v1"]
    db.refresh(v1)
    assert v1.freshness_state == "STALE"
    assert v1.runtime_eligibility == "NOT_ELIGIBLE"
    assert v1.publication_state != "SUPERSEDED"
    assert _serving_kce(db, models, v1.id) == []

    # Next successful run refreshes the stale version even when the text matches it again.
    refreshed = _persist(db, models, run, profile_id=profile_id, url=url, statement="Original text.", token="s3")
    assert refreshed.document_failures == []
    assert refreshed.superseded_knowledge_unit_ids == [v1.id]
    v2 = db.query(models.KnowledgeUnit).filter_by(id=refreshed.knowledge_unit_ids[0]).one()
    assert (v2.immutable_version_id, v2.supersedes_unit_id) == ("v2", v1.id)
    db.refresh(v1)
    assert v1.publication_state == "SUPERSEDED"

    # A failure before any change was detected leaves existing data untouched.
    monkeypatch.setattr(runtime, "apply_governed_finalize_and_lexical_index", _boom)
    untouched = _persist(db, models, run, profile_id=profile_id, url=url, statement="Original text.", token="s4")
    monkeypatch.setattr(runtime, "apply_governed_finalize_and_lexical_index", real_finalize)
    assert untouched.stale_retired_knowledge_unit_ids == []
    db.refresh(v2)
    assert v2.freshness_state != "STALE"


def test_W6P01_FG13_c2_unchanged_source_reevaluation_never_revives_retired_versions(db) -> None:
    from backend.app.services.i5.governed_ku_serving import (
        apply_governed_finalize_and_lexical_index,
        ku_blocks_governed_reevaluation,
        reevaluate_existing_kus_for_unchanged_source,
    )

    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    activation = runtime.activate_nhs_sleep_source(db, models)
    profile_id = int(activation.governed_source_profile_id)
    run = _governed_run(db, models, "k81c2-reeval-run")
    url = "https://www.nhs.uk/live-well/sleep-and-tiredness/k81c2-reeval"
    identity = runtime.stable_document_identity(profile_id, url)

    first = _persist(db, models, run, profile_id=profile_id, url=url, statement="Sleep text one.", token="r1")
    v1 = db.query(models.KnowledgeUnit).filter_by(id=first.knowledge_unit_ids[0]).one()
    second = _persist(db, models, run, profile_id=profile_id, url=url, statement="Sleep text two.", token="r2")
    v2 = db.query(models.KnowledgeUnit).filter_by(id=second.knowledge_unit_ids[0]).one()
    db.refresh(v1)
    assert v1.publication_state == "SUPERSEDED"
    assert ku_blocks_governed_reevaluation(v1) is True
    assert ku_blocks_governed_reevaluation(v2) is False

    # HTTP 304 / NO_MATERIAL_CHANGE path re-evaluates every KU of the source.
    reevaluate_existing_kus_for_unchanged_source(db, source_profile_id=profile_id)
    db.refresh(v1)
    db.refresh(v2)
    assert v1.publication_state == "SUPERSEDED"
    assert v1.freshness_state == "STALE"
    assert v1.runtime_eligibility == "NOT_ELIGIBLE"
    assert _serving_kce(db, models, v1.id) == []
    open_versions = [
        k for k in _versions(db, models, identity) if k.publication_state not in {"SUPERSEDED", "WITHDRAWN"}
    ]
    assert [k.id for k in open_versions] == [v2.id]

    # Direct finalize on a retired version is a no-op as well.
    prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=v1.id).one()
    assert (
        apply_governed_finalize_and_lexical_index(
            db,
            v1,
            source_key=runtime.NHS_SOURCE_KEY,
            source_profile_id=profile_id,
            authoritative_provenance=prov,
            incoming_source_profile_id=profile_id,
        ).value
        == "NOT_ELIGIBLE"
    )
    db.refresh(v1)
    assert v1.publication_state == "SUPERSEDED"

    # A version retired as STALE after a failed change is blocked too.
    class _Stale:
        retraction_reason = None
        publication_state = "PUBLISHED"
        freshness_state = "STALE"
        conflict_state = "NONE"

    assert ku_blocks_governed_reevaluation(_Stale()) is True


def test_W6P01_FG14_c2_healed_specialized_statement_is_not_a_change() -> None:
    """Specialized eligibility stores a healed claim window; the raw claim must still match."""
    from backend.app.services.i5.governed_specialized_entity_eligibility import (
        select_clinical_claim_window,
    )

    url = "https://medlineplus.gov/amyotrophiclateralsclerosis.html"
    claim = (
        "Amyotrophic Lateral Sclerosis | ALS | MedlinePlus Learn how to cope with ALS and more. "
        "Summary What is amyotrophic lateral sclerosis (ALS)? Amyotrophic lateral sclerosis (ALS) "
        "is a nervous system disease that attacks nerve cells called neurons in your brain and "
        "spinal cord. These neurons transmit messages from your brain and spinal cord to your "
        "voluntary muscles. At first, this causes mild muscle problems."
    )
    healed = select_clinical_claim_window(claim, canonical_url=url)
    assert healed and healed != claim

    class _Stored:
        normalized_statement = healed

    assert runtime._served_statement_changed(_Stored(), claim, url) is False
    assert runtime._served_statement_changed(_Stored(), claim.replace("mild", "severe"), url) is True


# ---------------------------------------------------------------------------
# Knowledge depth — one KU per content section of a page.
# ---------------------------------------------------------------------------

_SECTION_PAGE = (
    "<html><head><title>Motor neurone disease - NHS</title></head><body>"
    "<header><nav><a href='/'>Home</a> <h2>Health A to Z</h2><a href='/a'>Conditions A to Z</a></nav></header>"
    "<button class='menu'>Menu"  # unclosed button must not silence the page
    "<main><h1>Motor neurone disease (MND)</h1>"
    "<p>Motor neurone disease (MND) is a rare condition that progressively damages parts of the "
    "nervous system. It leads to muscle weakness, often with visible wasting.</p>"
    "<h2>Language switcher</h2><p>English Español Motor neurone disease happens when specialist "
    "nerve cells called motor neurones stop working properly and progressively lose function. "
    "It is not known exactly why this happens in most people.</p>"
    "<h2>Symptoms of MND</h2><p>Early symptoms can include weakness in the ankle or leg, slurred speech, "
    "a weak grip, muscle cramps and twitches, and weight loss. Symptoms usually start gradually and "
    "get worse over time as the condition progresses.</p>"
    "<h2>Treatment for MND</h2><p>There is no cure for MND, but treatment can help reduce the impact the "
    "symptoms have on your life. A care team will help you stay as independent as possible and plan for "
    "the future, including physiotherapy, speech therapy and nutritional support.</p>"
    "<h3>Riluzole</h3><p>Riluzole is a medicine that may slow the progression of MND slightly. It is taken "
    "as a tablet twice a day and your care team will monitor how it affects you over time.</p>"
    "<h2>Related conditions</h2><p><a href='/x'>Kennedy disease is a related neuromuscular condition</a> "
    "<a href='/y'>Spinal muscular atrophy is also a motor neurone condition</a> "
    "<a href='/z'>Myasthenia gravis affects how nerves and muscles communicate</a></p>"
    "<h2>Page last reviewed: 01 May 2026</h2><p>Next review due: 01 May 2029 and this page is checked "
    "regularly by the clinical content team to make sure it stays accurate and current.</p>"
    "</main><footer><h2>Support links</h2><p>Home Health A to Z Live Well Mental health Care and support</p></footer>"
    "</body></html>"
).encode("utf-8")


def _section_envelope(body: bytes, url: str = "https://www.nhs.uk/conditions/motor-neurone-disease/"):
    return FetchEnvelope(
        request_id="t",
        adapter_id="i5.public_web_fetch",
        adapter_version="1",
        canonical_url=url,
        final_url=url,
        http_status=200,
        content_type="text/html",
        charset="utf-8",
        body=body,
        byte_count=len(body),
        content_hash=hashlib.sha256(body).hexdigest(),
        retrieved_at=datetime(2026, 10, 15, 0, 0, 0),
        disposition="OK",
        error_category=None,
    )


def test_W6P01_FG15_section_extraction_drops_chrome_and_keeps_narrative() -> None:
    cands = extract_candidates(_section_envelope(_SECTION_PAGE), mode="PUBLIC_WEB_FETCH")
    keys = [c.section_anchor for c in cands]
    # Intro (incl. the widget-headed continuation), symptoms, treatment and its sub-section.
    assert keys == ["h2:intro", "h2:intro-2", "h2:symptoms-of-mnd", "h2:treatment-for-mnd", "h3:riluzole"]
    by_key = {c.section_anchor: c for c in cands}
    treatment = by_key["h2:treatment-for-mnd"].claim_candidate
    assert treatment.startswith("Motor neurone disease (MND) — Treatment for MND: There is no cure for MND")
    assert "physiotherapy, speech therapy" in treatment  # natural case, full section text
    assert not by_key["h2:intro-2"].claim_candidate.split(": ", 1)[1].startswith("English")
    joined = " ".join(c.claim_candidate for c in cands)
    for chrome in ("Health A to Z", "Kennedy disease", "Next review due", "Support links"):
        assert chrome not in joined
    for c in cands:
        assert "candidate_only_not_approved_knowledge" in c.warnings
        assert len(c.claim_candidate) <= 1400


def test_W6P01_FG16_section_page_yields_one_handoff_pair_per_section() -> None:
    from backend.app.services.i5.source_discovery import build_discovery_work_item

    class _Resp:
        status_code = 200
        content = _SECTION_PAGE
        headers = {"Content-Type": "text/html; charset=utf-8"}
        text = _SECTION_PAGE.decode()

    import backend.app.services.gate3.fetch_security as fs
    import backend.app.services.gate3.robots_checker as rc

    old_dns, old_robots = fs.socket.getaddrinfo, rc.requests.get
    fs.socket.getaddrinfo = lambda *_a, **_k: [(0, 0, 0, "", ("93.184.216.34", 0))]
    rc.requests.get = lambda *_a, **_k: type(
        "R", (), {"status_code": 200, "text": "User-agent: *\nAllow: /\n"}
    )()
    try:
        work = build_discovery_work_item(
            SourceCandidateDescriptor(
                source_profile_id=1,
                adapter_mode="PUBLIC_WEB_FETCH",
                url="https://www.nhs.uk/conditions/motor-neurone-disease/",
                registry_state="ACTIVE",
                runtime_eligibility="ELIGIBLE",
                rights_terms_state="OGL",
                robots_access_state="ALLOWED",
                rate_limit_policy="DEFINED",
                allowed_domain="nhs.uk",
            )
        )
        status, code, handoffs = orch._apply_live_source(work=work, http_get=lambda *_a, **_k: _Resp())
    finally:
        fs.socket.getaddrinfo, rc.requests.get = old_dns, old_robots
    assert (status, code) == ("EXTRACTED", None)
    kinds = [h.handoff_kind for h in handoffs]
    assert kinds.count("RAW_EVIDENCE") == 1
    assert kinds.count("CANDIDATE") == kinds.count("PROVENANCE") == 5
    cands = [h for h in handoffs if h.handoff_kind == "CANDIDATE"]
    provs = [h for h in handoffs if h.handoff_kind == "PROVENANCE"]
    assert len({h.request_key for h in provs}) == 5
    assert {h.payload["section_key"] for h in cands} == {h.payload["section_key"] for h in provs}
    assert len({h.payload["candidate_fingerprint"] for h in cands}) == 5


def test_W6P01_FG17_section_layout_lifecycle(db) -> None:
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    profile_id = _plain_source(db, models, "k-depth-source")
    run = _governed_run(db, models, "k-depth-run")
    url = "https://example.org/k-depth/condition"
    doc_identity = runtime.stable_document_identity(profile_id, url)

    # Legacy document-level KU for the page.
    legacy = _persist(db, models, run, profile_id=profile_id, url=url, statement="Doc-level claim.", token="d1")
    legacy_ku = db.query(models.KnowledgeUnit).filter_by(id=legacy.knowledge_unit_ids[0]).one()
    assert legacy_ku.canonical_unit_id == doc_identity

    def _page(sections: dict, token: str):
        handoffs = []
        for key, text in sections.items():
            hs = _identity_handoffs(
                source_profile_id=profile_id,
                canonical_url=url,
                statement=text,
                content_token=f"{token}-{key}",
                section_key=key,
            )
            for h in hs:
                h.payload["extraction_process"] = "w3p01-conceptual-sections-1.0.0"
                h.payload["raw_evidence_request_key"] = f"raw-{token}"
                h.payload["content_sha256"] = _sha(token)
            hs[0].request_key = f"raw-{token}"
            handoffs.extend(hs if not handoffs else hs[1:])
        return runtime.execute_governed_persistence(
            db, models, handoffs=handoffs, run_id=int(run.id), attempt_id=1
        )

    first = _page(
        {"h2:symptoms": "Condition — Symptoms: weakness.", "h2:treatment": "Condition — Treatment: care team."},
        "p1",
    )
    assert first.document_failures == []
    assert first.new_knowledge_count == 2
    assert first.retired_knowledge_unit_ids == [legacy_ku.id]
    db.refresh(legacy_ku)
    assert legacy_ku.publication_state == "SUPERSEDED"
    sec_ids = {
        k: runtime.stable_document_identity(profile_id, url, k) for k in ("h2:symptoms", "h2:treatment")
    }
    for cid in sec_ids.values():
        ku = db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=cid).one()
        prov = db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).one()
        assert prov.extraction_process.startswith(runtime.SECTION_EXTRACTION_PROCESS_PREFIX)
        assert prov.source_document_id == doc_identity

    # The treatment section disappears -> retired; symptoms unchanged.
    second = _page({"h2:symptoms": "Condition — Symptoms: weakness."}, "p2")
    treatment_v1 = (
        db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=sec_ids["h2:treatment"]).one()
    )
    assert second.retired_knowledge_unit_ids == [treatment_v1.id]
    assert second.new_knowledge_count == 0
    db.refresh(treatment_v1)
    assert treatment_v1.publication_state == "SUPERSEDED"

    # It comes back -> next version of the same identity, linked to the retired one.
    third = _page(
        {"h2:symptoms": "Condition — Symptoms: weakness.", "h2:treatment": "Condition — Treatment: new plan."},
        "p3",
    )
    assert third.document_failures == []
    versions = _versions(db, models, sec_ids["h2:treatment"])
    assert [v.immutable_version_id for v in versions] == ["v1", "v2"]
    assert versions[1].supersedes_unit_id == treatment_v1.id
    assert third.retired_knowledge_unit_ids == []


def test_W6P01_FG18_specialized_eligibility_keeps_clean_section_statement() -> None:
    from backend.app.services.i5.governed_specialized_entity_eligibility import (
        can_apply_specialized_entity_eligibility,
    )

    statement = (
        "Amyotrophic Lateral Sclerosis — Summary: Amyotrophic lateral sclerosis (ALS) is a nervous "
        "system disease that attacks nerve cells called neurons in your brain and spinal cord. "
        + "These neurons transmit messages from your brain and spinal cord to your voluntary muscles. " * 6
    )

    class _Ku:
        provenance_complete = True
        retraction_reason = None
        conflict_state = "NONE"
        manifest_entity_id = "D18"
        normalized_statement = statement

    ku = _Ku()
    ok, reason, spec = can_apply_specialized_entity_eligibility(
        source_key="medlineplus_consumer_health",
        ku=ku,
        canonical_url="https://medlineplus.gov/amyotrophiclateralsclerosis.html",
    )
    assert (ok, reason, spec.entity_id) == (True, "OK", "D18")
    assert ku.normalized_statement == statement  # not re-windowed to 520 chars


# ---------------------------------------------------------------------------
# Living knowledge — unconfirmed crawled knowledge stops serving; real counters.
# ---------------------------------------------------------------------------


def test_W6P01_FG19_unconfirmed_weekly_knowledge_goes_stale(db) -> None:
    from datetime import timedelta

    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    profile_id = _plain_source(db, models, "k-fresh-source")
    run = _governed_run(db, models, "k-fresh-run")
    old_url = "https://example.org/k-fresh/removed-page"
    live_url = "https://example.org/k-fresh/live-page"
    now = datetime(2026, 10, 15, 0, 0, 0)

    old = _persist(db, models, run, profile_id=profile_id, url=old_url, statement="Old page text.", token="f1")
    old_ku = db.query(models.KnowledgeUnit).filter_by(id=old.knowledge_unit_ids[0]).one()
    live = _persist(db, models, run, profile_id=profile_id, url=live_url, statement="Live page text.", token="f2")
    live_ku = db.query(models.KnowledgeUnit).filter_by(id=live.knowledge_unit_ids[0]).one()
    for ku in (old_ku, live_ku):
        ku.freshness_state = "CURRENT"  # as if published by governed eligibility
    old_ku.last_reviewed_at = now - timedelta(days=runtime.WEEKLY_RECONFIRMATION_POLICY_DAYS + 1)
    db.flush()

    # Re-crawling the live page (NO_CHANGE) reconfirms it.
    again = _persist(db, models, run, profile_id=profile_id, url=live_url, statement="Live page text.", token="f3")
    assert again.knowledge_unit_ids == [live_ku.id]
    db.refresh(live_ku)
    assert live_ku.last_reviewed_at is not None
    live_ku.last_reviewed_at = now - timedelta(days=1)
    db.flush()

    retired = runtime.retire_unconfirmed_weekly_knowledge(db, models, now=now)
    assert retired == [old_ku.id]
    db.refresh(old_ku)
    db.refresh(live_ku)
    assert old_ku.freshness_state == "STALE"
    assert old_ku.runtime_eligibility == "NOT_ELIGIBLE"
    assert _serving_kce(db, models, old_ku.id) == []
    assert live_ku.freshness_state == "CURRENT"
    # Idempotent: nothing left to retire.
    assert runtime.retire_unconfirmed_weekly_knowledge(db, models, now=now) == []


def test_W6P01_FG20_lifecycle_counters_reflect_real_outcome() -> None:
    class _Attempt:
        new_knowledge_count = 0
        updated_knowledge_count = 0
        superseded_knowledge_count = 0
        rejected_knowledge_count = 0
        warning_count = 1

    result = runtime.GovernedPersistResult(
        new_knowledge_count=3,
        superseded_knowledge_unit_ids=[10, 11],
        retired_knowledge_unit_ids=[12],
        stale_retired_knowledge_unit_ids=[13],
        document_failures=[{"code": "KU_MULTIPLE_CURRENT_VERSIONS"}],
    )
    attempt = _Attempt()
    runtime.record_lifecycle_counters(attempt, result, stale_unconfirmed_ids=[14, 15])
    assert attempt.new_knowledge_count == 3
    assert attempt.updated_knowledge_count == 2
    assert attempt.superseded_knowledge_count == 2 + 1 + 1 + 2
    assert attempt.rejected_knowledge_count == 1
    assert attempt.warning_count == 2

    only_sweep = _Attempt()
    runtime.record_lifecycle_counters(only_sweep, None, stale_unconfirmed_ids=[1])
    assert only_sweep.superseded_knowledge_count == 1
    assert only_sweep.new_knowledge_count == 0


# ---------------------------------------------------------------------------
# Multilingual knowledge identity (concept catalog + 81-B authority) and chat intent.
# ---------------------------------------------------------------------------


def test_W6P01_FG21_concept_catalog_contract() -> None:
    from backend.app.services.i5.know02.concept_catalog import (
        VERIFIED_LABEL_STATUSES,
        concept_key_for_url,
        dimension_for_section,
        load_concept_catalog,
    )

    catalog = load_concept_catalog()
    concepts = catalog["concepts"]
    assert len({c["concept_key"] for c in concepts}) == len(concepts)
    for concept in concepts:
        langs = {lab["language"] for lab in concept["labels"]}
        assert {"en", "fa", "ar"} <= langs, concept["concept_key"]
        for lab in concept["labels"]:
            if lab["language"] == "en":
                # EN terms come from the governed sources' own titles.
                assert lab["status"] in VERIFIED_LABEL_STATUSES
            else:
                # FA/AR are model-assisted drafts until Javad approves them (D-010).
                assert lab["status"] in {"MODEL_ASSISTED_DRAFT", "FOUNDER_APPROVED"}
                if lab["status"] == "FOUNDER_APPROVED":
                    assert lab.get("approved_on"), concept["concept_key"]
    assert concept_key_for_url("https://www.nhs.uk/conditions/motor-neurone-disease/") == "disease:als"
    assert concept_key_for_url("https://medlineplus.gov/multiplesclerosis.html") == "disease:ms"
    assert concept_key_for_url("https://www.cdc.gov/physical-activity-basics/guidelines/adults.html") == "topic:physical_activity"
    assert concept_key_for_url("https://www.nhlbi.nih.gov/health/asthma") is None
    assert dimension_for_section("h2:symptoms-of-mnd") == "SYMPTOMS"
    assert dimension_for_section("h3:medicines-for-high-blood-pressure") == "PHARMACOLOGICAL_TREATMENT"
    assert dimension_for_section("h2:how-you-can-help-lower-your-blood-pressure") == "PREVENTION"
    assert dimension_for_section("h2:intro") == "DEFINITION"
    assert dimension_for_section("") is None


def test_W6P01_FG22_cross_language_serving_needs_founder_approved_label(db) -> None:
    from backend.app.services.i5.know02.concept_catalog import ensure_concept_catalog
    from backend.app.services.i5.know02.taxonomy import resolve_verified_concept_authority
    from backend.app.services.scis.governed_runtime_adapter import retrieve_scis_governed_runtime_items
    from backend.app.services.scis.contracts import RetrievalMode

    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    counts = ensure_concept_catalog(db)
    assert counts["concepts"] >= 20
    again = ensure_concept_catalog(db)  # idempotent
    assert again == counts

    activation = runtime.activate_nhs_sleep_source(db, models)
    profile_id = int(activation.governed_source_profile_id)
    run = _governed_run(db, models, "k-multilingual-run")
    url = "https://www.nhs.uk/live-well/exercise/physical-activity-guidelines-for-adults-aged-19-to-64/"
    statement = (
        "Physical activity guidelines for adults — Recommendations: adults should do some type of "
        "physical activity every day, at least 150 minutes of moderate intensity activity a week."
    )
    hs = _identity_handoffs(
        source_profile_id=profile_id, canonical_url=url, statement=statement,
        content_token="ml1", section_key="h2:recommendations-for-adults",
    )
    for h in hs:
        h.payload["domain"] = "physical_activity_exercise"
        h.payload["topic"] = "exercise"
    result = runtime.execute_governed_persistence(db, models, handoffs=hs, run_id=int(run.id), attempt_id=1)
    assert result.document_failures == []
    ku = db.query(models.KnowledgeUnit).filter_by(id=result.knowledge_unit_ids[0]).one()
    concept = db.query(models.I5ClinicalConcept).filter_by(concept_key="topic:physical_activity").one()
    links = db.query(models.I5KnowledgeUnitConcept).filter_by(knowledge_unit_id=ku.id).all()
    assert [link.concept_id for link in links] == [concept.id]
    dims = db.query(models.I5KnowledgeUnitDimension).filter_by(knowledge_unit_id=ku.id).all()
    assert dims == []  # "recommendations for adults" implies no dimension rule

    fa_query = "فعالیت بدنی برای بزرگسالان چقدر باید باشد؟"
    # Draft FA label: no authority, and the same-language gate keeps EN evidence out.
    assert resolve_verified_concept_authority(db, fa_query, "fa") is None
    items, meta = retrieve_scis_governed_runtime_items(
        db, fa_query, language="fa", allow_network=False, force_mode=RetrievalMode.LEXICAL
    )
    assert items == [] and meta["concept_authority_applied"] is False

    # Javad approves the FA label -> verified concept authority + EN label hints.
    fa_label = (
        db.query(models.I5ClinicalConceptLabel)
        .filter_by(concept_id=concept.id, language="fa", label_text="فعالیت بدنی")
        .one()
    )
    fa_label.verified = True
    db.flush()
    authority = resolve_verified_concept_authority(db, fa_query, "fa")
    assert authority is not None and ku.id in authority.knowledge_unit_ids
    assert ku.runtime_eligibility == "ELIGIBLE"  # NHS low-risk source, physical-activity domain
    items, meta = retrieve_scis_governed_runtime_items(
        db, fa_query, language="fa", allow_network=False, force_mode=RetrievalMode.LEXICAL
    )
    assert meta["concept_authority_applied"] is True
    assert meta.get("concept_label_hints") is True
    # Persian question -> English governed evidence, only from the concept's linked KUs.
    assert {item.knowledge_unit_id for item in items} == {ku.id}


def test_W6P01_FG23_chat_intent_covers_fa_ar_en_and_whole_words() -> None:
    from backend.app.services.gate3.medical_intent import (
        is_medical_care_intent,
        is_mental_wellbeing_intent,
    )

    assert is_medical_care_intent("What is ALS?", "en")
    assert not is_medical_care_intent("I also walk every day", "en")
    assert is_medical_care_intent("I feel stressed at work", "en")
    assert is_medical_care_intent("ام اس من بدتر شده", "fa")
    assert is_medical_care_intent("درباره MS سوال دارم", "fa")
    assert is_medical_care_intent("برنامه ورزش برای کاهش وزن", "fa")
    assert is_medical_care_intent("ما هي أعراض التصلب المتعدد؟", "ar")
    assert is_mental_wellbeing_intent("أشعر بالقلق كل يوم", "ar")
    assert not is_medical_care_intent("سلام، خوبی؟", "fa")
    assert not is_medical_care_intent("مرحبا كيف حالك", "ar")
