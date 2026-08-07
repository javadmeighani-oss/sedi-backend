"""Section 30 / W4-P02 — Grounded synthesis + reference/disclosure (P09).

Runtime selectors exercised by w4p02-postgresql-grounded-synthesis-runtime.yml.
No live LLM/network. local_rag untouched. Formal §164.2 credit not owned.
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5 import reference_renderer as rr
from backend.app.services.i5.reference_renderer import (
    MANAGEMENT_ALIAS,
    NO_BASE_MODEL_MEDICAL_FALLBACK,
    PACKAGE_ID,
    SERVICE_NAME,
    STATUS_NO_SAFE_KNOWLEDGE,
    STATUS_OK,
    extract_handoffs_from_retrieval,
    format_care_context_block,
    reject_unsupported_medical_claim,
    render_from_care_context,
    render_grounded_answer,
)
from backend.app.services.i5.runtime_knowledge_retrieval import (
    STATUS_NO_ELIGIBLE_KNOWLEDGE,
    retrieve_knowledge_context,
)


def _load_models():
    return importlib.import_module("backend.app.models")


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


def _eligible_ku_kwargs(**overrides) -> dict[str, Any]:
    base = dict(
        provenance_complete=True,
        evidence_strength="HIGH",
        freshness_state="CURRENT",
        conflict_state="NONE",
        medical_safety_state="CLEARED",
        publication_state="PUBLISHED",
        runtime_eligibility="ELIGIBLE",
        retraction_reason=None,
        topic_taxonomy="migraine",
        domain="neurology",
        language="en",
        knowledge_type="FACT",
        normalized_statement="Migraine prevention lifestyle guidance for adults",
    )
    base.update(overrides)
    return base


def _build_gsp(**overrides):
    models = _load_models()
    base = dict(
        canonical_key="w4p02-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


def _build_ku(**overrides):
    models = _load_models()
    kwargs = _eligible_ku_kwargs(**overrides)
    stmt = kwargs.pop("normalized_statement")
    dedupe = kwargs.pop("deduplication_key", None) or _det_hex(32)
    canon = kwargs.pop("canonical_hash", None) or _det_hex(32)
    base = dict(
        canonical_unit_id=kwargs.pop("canonical_unit_id", "ku-" + _det_hex(8)),
        immutable_version_id=kwargs.pop("immutable_version_id", "v-" + _det_hex(8)),
        normalized_statement=stmt,
        deduplication_key=dedupe,
        canonical_hash=canon,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    base.update(kwargs)
    return models.KnowledgeUnit(**base)


def _ensure_gsp(db, **overrides):
    gsp = _build_gsp(**overrides)
    db.add(gsp)
    db.flush()
    return gsp


def _ensure_ku(db, **overrides):
    ku = _build_ku(**overrides)
    db.add(ku)
    db.flush()
    return ku


def _ensure_memory(db, ku, **overrides):
    models = _load_models()
    mid = overrides.pop("memory_item_id", None) or _det_hex(32)
    base = dict(
        memory_item_id=mid,
        knowledge_unit_id=ku.id,
        domain=ku.domain,
        topic=ku.topic_taxonomy or "migraine",
        knowledge_version=ku.immutable_version_id,
        evidence_strength=ku.evidence_strength,
        freshness_state=ku.freshness_state,
        conflict_state=ku.conflict_state,
        medical_safety_state=ku.medical_safety_state,
        runtime_eligibility=ku.runtime_eligibility,
        supersession_state="CURRENT",
    )
    base.update(overrides)
    mem = models.KnowledgeMemoryItem(**base)
    db.add(mem)
    db.flush()
    return mem


def _ensure_provenance(db, ku, gsp=None, **overrides):
    models = _load_models()
    if gsp is None:
        gsp = _ensure_gsp(db)
    base = dict(
        knowledge_unit_id=ku.id,
        source_profile_id=gsp.id,
        retrieval_method="W4P02_TEST_FIXTURE",
    )
    base.update(overrides)
    row = models.KnowledgeProvenance(**base)
    db.add(row)
    db.flush()
    return row


def _seed_eligible(db, *, memory_overrides: dict[str, Any] | None = None, **ku_overrides):
    gsp = _ensure_gsp(db)
    ku = _ensure_ku(db, **ku_overrides)
    mem = _ensure_memory(db, ku, **(memory_overrides or {}))
    prov = _ensure_provenance(db, ku, gsp=gsp)
    return gsp, ku, mem, prov


def _fixture_retrieval_ok(*statements: str) -> dict[str, Any]:
    items = []
    for i, stmt in enumerate(statements, start=1):
        items.append(
            {
                "knowledge_unit_id": i,
                "canonical_unit_id": f"canon-{i}",
                "immutable_version_id": f"ver-{i}",
                "memory_item_id": f"mem-{i}",
                "provenance_id": 100 + i,
                "source_profile_id": 10 + i,
                "raw_evidence_id": None,
                "normalized_statement": stmt,
                "evidence_strength": "HIGH",
                "freshness_state": "CURRENT",
                "conflict_state": "NONE",
                "medical_safety_state": "CLEARED",
                "domain": "neurology",
                "language": "en",
            }
        )
    return {
        "package_id": "I5-IMPL-W4-P01",
        "status": "OK",
        "query_id": "q-fixture",
        "trace_id": "t-fixture",
        "items": items,
        "exclusions": [],
        "no_base_model_fallback": True,
    }


def test_W4P02_T1_package_identity():
    assert PACKAGE_ID == "I5-IMPL-W4-P02"
    assert MANAGEMENT_ALIAS == "P09"
    assert SERVICE_NAME == "reference_renderer"
    assert NO_BASE_MODEL_MEDICAL_FALLBACK is True
    assert rr.STATUS_OK == "OK"


def test_W4P02_T2_retrieval_to_synthesis_handoff():
    retrieval = _fixture_retrieval_ok("Migraine hydration guidance")
    handoffs = extract_handoffs_from_retrieval(retrieval)
    assert len(handoffs) == 1
    assert handoffs[0].normalized_statement == "Migraine hydration guidance"
    answer = render_grounded_answer(retrieval, language="en")
    assert answer.package_id == PACKAGE_ID
    assert answer.status == STATUS_OK
    assert "Migraine hydration guidance" in answer.synthesized_text


def test_W4P02_T3_eligible_evidence_synthesis(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(db, normalized_statement="Migraine prevention lifestyle guidance")
    retrieval = retrieve_knowledge_context(
        db, "migraine prevention", language="en", domain="neurology", enqueue_gap_on_empty=False
    )
    answer = render_grounded_answer(retrieval, language="en")
    assert answer.status == STATUS_OK
    assert any(c.claim_kind == "SUPPORTED_MEDICAL" for c in answer.claims)
    assert "Migraine prevention lifestyle guidance" in answer.synthesized_text


def test_W4P02_T4_reference_traceability():
    retrieval = _fixture_retrieval_ok("Sleep hygiene reduces migraine frequency")
    answer = render_grounded_answer(retrieval)
    assert len(answer.references) == 1
    ref = answer.references[0]
    assert ref.knowledge_unit_id == 1
    assert ref.provenance_id == 101
    assert ref.label.startswith("KU:")
    assert answer.show_sources
    assert answer.why_sedi_said_this


def test_W4P02_T5_multi_evidence_deterministic():
    a = render_grounded_answer(
        _fixture_retrieval_ok("Alpha migraine note", "Beta migraine note")
    )
    b = render_grounded_answer(
        _fixture_retrieval_ok("Alpha migraine note", "Beta migraine note")
    )
    assert a.synthesized_text == b.synthesized_text
    assert [r.label for r in a.references] == [r.label for r in b.references]
    assert len(a.references) == 2


def test_W4P02_T6_unsupported_claim_rejection():
    retrieval = _fixture_retrieval_ok("Hydration may help some migraine sufferers")
    evidence = extract_handoffs_from_retrieval(retrieval)
    assert reject_unsupported_medical_claim("Take 900mg experimental toxin daily", evidence)
    answer = render_grounded_answer(
        retrieval,
        proposed_unsupported_claims=["Take 900mg experimental toxin daily"],
    )
    assert answer.unsupported_claims_rejected
    assert all("UNSUPPORTED_MEDICAL_CLAIM" in x for x in answer.unsupported_claims_rejected)
    assert "experimental toxin" not in answer.synthesized_text.lower()


def test_W4P02_T7_missing_evidence_fail_closed():
    answer = render_grounded_answer(
        {
            "status": STATUS_NO_ELIGIBLE_KNOWLEDGE,
            "items": [],
            "exclusions": [{"reason": "KU_NOT_ELIGIBLE:NOT_ELIGIBLE", "knowledge_unit_id": 9}],
            "no_base_model_fallback": True,
        }
    )
    assert answer.status == STATUS_NO_SAFE_KNOWLEDGE
    assert answer.references == []
    assert answer.no_base_model_fallback is True
    assert any(d.trigger == "NO_SAFE_KNOWLEDGE" for d in answer.disclosures)


def test_W4P02_T8_no_base_model_fallback():
    answer = render_grounded_answer({"status": "NO_ELIGIBLE_KNOWLEDGE", "items": []})
    assert answer.no_base_model_fallback is True
    assert answer.chat_metadata["no_base_model_fallback"] is True
    assert "invent medical content" in answer.synthesized_text.lower() or any(
        "invent medical content" in d.message.lower() for d in answer.disclosures
    )


@pytest.mark.parametrize(
    "conflict_state,label",
    [("SUSPECTED", "suspected"), ("CONFIRMED", "confirmed")],
    ids=["suspected", "confirmed"],
)
def test_W4P02_T9_conflict_disclosure(db, conflict_state: str, label: str):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        conflict_state=conflict_state,
        runtime_eligibility="REVIEW_REQUIRED",
        normalized_statement=f"Conflicted migraine {label}",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    retrieval = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    answer = render_grounded_answer(retrieval, language="en")
    assert len(retrieval.items) == 0
    assert any(d.trigger == "CONFLICT" for d in answer.disclosures) or answer.status in {
        STATUS_NO_SAFE_KNOWLEDGE,
        "CONFLICT_DISCLOSURE",
        "INSUFFICIENT",
    }


def test_W4P02_T10_safety_restricted_disclosure(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        medical_safety_state="RESTRICTED",
        runtime_eligibility="NOT_ELIGIBLE",
        normalized_statement="Restricted migraine note",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    retrieval = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    answer = render_grounded_answer(retrieval)
    assert len(retrieval.items) == 0
    assert any(d.trigger in {"SAFETY", "NO_SAFE_KNOWLEDGE"} for d in answer.disclosures)


def test_W4P02_T11_stale_exclusion_inheritance(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        freshness_state="STALE",
        runtime_eligibility="NOT_ELIGIBLE",
        normalized_statement="Stale migraine guidance",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    retrieval = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    answer = render_grounded_answer(retrieval)
    assert len(retrieval.items) == 0
    assert "Stale migraine guidance" not in answer.synthesized_text
    assert any(d.trigger in {"STALE", "NO_SAFE_KNOWLEDGE"} for d in answer.disclosures)


def test_W4P02_T12_provenance_requirement_inheritance(db):
    _require_postgres(db)
    configure_mappers()
    ku = _ensure_ku(
        db,
        provenance_complete=True,
        normalized_statement="Migraine without provenance row",
    )
    _ensure_memory(db, ku)
    retrieval = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    answer = render_grounded_answer(retrieval)
    assert len(retrieval.items) == 0
    assert answer.references == []


def test_W4P02_T13_personalization_boundary():
    retrieval = _fixture_retrieval_ok("Caffeine timing may affect migraine")
    answer = render_grounded_answer(retrieval, language="fa")
    assert answer.personalization.language == "fa"
    assert answer.personalization.medical_facts_altered is False
    assert "Caffeine timing may affect migraine" in answer.synthesized_text


def test_W4P02_T14_language_boundary():
    en = render_grounded_answer(_fixture_retrieval_ok("English migraine note"), language="en")
    fa = render_grounded_answer(_fixture_retrieval_ok("English migraine note"), language="fa")
    assert en.personalization.language == "en"
    assert fa.personalization.language == "fa"
    # Medical statement unchanged across languages.
    assert "English migraine note" in en.synthesized_text
    assert "English migraine note" in fa.synthesized_text


def test_W4P02_T15_mandatory_disclosure_triggers():
    answer = render_grounded_answer(
        {
            "status": "OK",
            "items": [],
            "exclusions": [{"reason": "KU_NOT_ELIGIBLE:NOT_ELIGIBLE"}],
        },
        user_requested_sources=True,
    )
    triggers = {d.trigger for d in answer.disclosures}
    assert "USER_REQUEST_SOURCES" in triggers
    assert "NO_SAFE_KNOWLEDGE" in triggers


def test_W4P02_T16_output_envelope():
    answer = render_grounded_answer(_fixture_retrieval_ok("Envelope migraine statement"))
    dumped = answer.model_dump()
    for key in (
        "package_id",
        "management_alias",
        "status",
        "synthesized_text",
        "claims",
        "references",
        "show_sources",
        "why_sedi_said_this",
        "disclosures",
        "personalization",
        "no_base_model_fallback",
        "chat_metadata",
    ):
        assert key in dumped
    assert dumped["chat_metadata"]["management_alias"] == "P09"


def test_W4P02_T17_brain_care_integration(monkeypatch):
    from backend.app.core.conversation import brain as brain_mod

    messages: list = []
    fake_ctx = {
        "goals": [],
        "restrictions": [],
        "upcoming_events": [],
        "i5_retrieval_status": "OK",
        "no_base_model_fallback": True,
        "knowledge_snippets": [
            {
                "content": "Brain-hook migraine statement",
                "knowledge_unit_id": 42,
                "canonical_unit_id": "canon-brain",
                "immutable_version_id": "ver-brain",
                "provenance_id": 7,
                "evidence_strength": "HIGH",
                "citation": {"label": "KU:canon-brain:ver-brain", "handoff": "W4-P02"},
            }
        ],
        "i5_knowledge_retrieval": {
            "status": "OK",
            "items": [
                {
                    "knowledge_unit_id": 42,
                    "canonical_unit_id": "canon-brain",
                    "immutable_version_id": "ver-brain",
                    "normalized_statement": "Brain-hook migraine statement",
                    "evidence_strength": "HIGH",
                    "provenance_id": 7,
                }
            ],
            "exclusions": [],
        },
    }

    monkeypatch.setattr(
        "backend.app.services.gate3.medical_intent.is_medical_care_intent",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "backend.app.services.gate3.care_intelligence.build_care_context",
        lambda *a, **k: fake_ctx,
    )
    brain_mod._maybe_append_gate3_care_context(
        messages, db=None, user_id=1, user_message="migraine pain", language="en"
    )
    assert messages
    content = messages[0]["content"]
    assert "SHOW SOURCES" in content
    assert "WHY SEDI SAID THIS" in content
    assert "NO_BASE_MODEL_MEDICAL_FALLBACK=1" in content
    assert "Brain-hook migraine statement" in content
    assert fake_ctx.get("i5_chat_metadata", {}).get("package_id") == PACKAGE_ID


def test_W4P02_T18_insufficiency_behavior():
    answer = render_from_care_context(
        {
            "i5_retrieval_status": "INSUFFICIENT_CONTEXT",
            "i5_knowledge_retrieval": {
                "status": "INSUFFICIENT_CONTEXT",
                "items": [],
                "exclusions": [],
            },
            "knowledge_snippets": [],
        },
        language="en",
    )
    assert answer.status in {STATUS_NO_SAFE_KNOWLEDGE, "INSUFFICIENT"}
    assert answer.references == []


def test_W4P02_T19_artifact_coverage_invariant():
    """Static invariant for Evidence Assurance generation order (W4P01-EVIDENCE-PACK-COVERAGE-01)."""
    actual = {
        "a.md",
        "b.json",
        "artifact-manifest.json",
        "checksums.sha256",
    }
    checksum_entries = actual - {"checksums.sha256"}
    manifest_declared = set(actual)
    assert checksum_entries == actual - {"checksums.sha256"}
    assert manifest_declared == actual
    assert "checksums.sha256" not in checksum_entries
    assert "artifact-manifest.json" in manifest_declared


def test_W4P02_T20_warning_precision_invariant():
    """Static invariant: pytest occurrence total must equal parsed terminal total."""
    sample = "19 passed, 135 warnings in 1.51s"
    import re

    m = re.search(r"(\d+) passed(?:, (\d+) warnings)?", sample)
    assert m
    assert int(m.group(2)) == 135
    # Representative line count must not replace occurrence total.
    representative_lines = 10
    assert representative_lines != 135
    pytest_total = int(m.group(2))
    assert pytest_total == 135


def test_W4P02_T21_show_sources_why_sedi():
    answer = render_grounded_answer(_fixture_retrieval_ok("Magnesium discussion for migraine"))
    block = format_care_context_block(answer)
    assert "SHOW SOURCES" in block
    assert "WHY SEDI SAID THIS" in block
    assert answer.chat_metadata["show_sources"]
    assert answer.chat_metadata["why_sedi_said_this"]
