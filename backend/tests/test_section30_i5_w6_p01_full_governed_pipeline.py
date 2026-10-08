"""Section 30 / I5-IMPL-W6-P01 — full governed pipeline proof (Master Gate).

Covers extraction integration, fail-closed retention, DB source loading,
deterministic weekly identity, advisory-lock behavior, governed persistence,
no auto-publication, and no unauthorized Knowledge Memory write.
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
    assert outcome.detail == "governed_raw_ku_provenance_persisted"

    raw_count = db.query(models.I5RawEvidence).count()
    ku_count = db.query(models.KnowledgeUnit).count()
    prov_count = db.query(models.KnowledgeProvenance).count()
    mem_count = db.query(models.KnowledgeMemoryItem).count()
    assert raw_count >= 1
    assert ku_count >= 1
    assert prov_count >= 1
    assert mem_count == 0

    ku = db.query(models.KnowledgeUnit).order_by(models.KnowledgeUnit.id.desc()).first()
    assert ku.publication_state == "DRAFT"
    assert ku.medical_safety_state == "PENDING_REVIEW"
    assert ku.runtime_eligibility in {"REVIEW_REQUIRED", "NOT_ELIGIBLE"}
    assert ku.runtime_eligibility != "ELIGIBLE"
    assert ku.provenance_complete is True

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
    assert outcome2.detail == "ALREADY_SUCCESSFUL_TERMINAL"
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
) -> list[_Handoff]:
    content_hash = _sha(content_token)
    canon = _sha(statement)
    raw_key = f"raw-{content_hash[:12]}"
    fingerprint = content_hash
    shared = {
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

    changed = "Sleep regularity guidance wording changed for the same source page."
    nested = db.begin_nested()
    try:
        runtime.execute_governed_persistence(
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
        raise AssertionError("changed content must fail closed")
    except runtime.GovernedWeeklyRuntimeError as exc:
        assert exc.code == "KU_CANONICAL_VERSION_CONTENT_MISMATCH"
        assert expected in str(exc)
        nested.rollback()
    assert db.query(models.KnowledgeUnit).filter_by(canonical_unit_id=expected).count() == 1
    assert ku.canonical_unit_id == expected

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
        runtime.execute_governed_persistence(
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
        raise AssertionError("ambiguous identity must fail closed")
    except runtime.GovernedWeeklyRuntimeError as exc:
        assert exc.code == "KU_DOCUMENT_IDENTITY_AMBIGUOUS"
        decoy_nested.rollback()
    assert db.query(models.KnowledgeMemoryItem).count() == mem_before
    assert first.knowledge_memory_writes == 0
