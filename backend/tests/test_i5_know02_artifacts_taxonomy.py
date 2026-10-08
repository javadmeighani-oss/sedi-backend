"""I5-KNOW-02 — artifacts, multi-evidence, claims, universal taxonomy tests."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.enums import (
    ArtifactVersionState,
    EvidenceSupportDirection,
    KnowledgeDimensionCode,
    SediCoveragePriority,
    SediRootCategory,
)
from backend.app.services.i5.know02.artifacts import link_evidence
from backend.app.services.i5.know02.eligibility import (
    claim_has_only_retracted_support,
    runtime_evidence_allowed,
    supporting_links_for_runtime,
)
from backend.app.services.i5.know02.seed_fixtures import seed_know02_foundation
from backend.app.services.i5.know02.taxonomy import query_kus_by_concept_and_dimension


def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def test_know02_no_p0_branching_in_core_services():
    root = Path("backend/app/services/i5/know02")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                # forbid identity compares against hard-coded disease string literals in ifs is soft;
                # stronger: no `if disease == "ALS"` Assign/Compare patterns with ALS/MS alone
                pass
        src = path.read_text(encoding="utf-8")
        assert 'if disease == "ALS"' not in src
        assert "elif disease == \"MS\"" not in src
        assert "if disease == 'ALS'" not in src


def test_know02_dimension_enum_covers_care_lifestyle():
    needed = {
        "NUTRITION",
        "EXERCISE",
        "LIFESTYLE",
        "SLEEP",
        "DAILY_ROUTINE",
        "PREVENTION",
        "CARE",
        "MENTAL_HEALTH",
    }
    assert needed <= {e.value for e in KnowledgeDimensionCode}


@pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")
def test_know02_foundation_universality_multi_evidence_queries():
    from backend.app import models

    url = _pg_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head not in {
            "063_i5_know02_artifacts_claims_taxonomy",
            "064_i5_know03_studies_effects_recs",
            "065_i5_know04_connectors_change_intelligence",
        }:
            pytest.skip(f"alembic head {head} not in KNOW-02+ chain")
        for t in (
            "i5_scientific_artifacts",
            "i5_scientific_artifact_versions",
            "i5_knowledge_unit_evidence_links",
            "i5_clinical_concepts",
            "i5_knowledge_claim_details",
            "i5_knowledge_dimensions",
        ):
            assert conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name=:t"), {"t": t}
            ).scalar()

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # clean prior know02-owned rows; do not CASCADE-break KNOW-03 RESTRICT graph
        for ku in (
            db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.canonical_unit_id.like("know02:%"))
            .all()
        ):
            db.delete(ku)
        # Probe KNOW-03 presence without aborting the outer transaction on missing relation.
        know03_present = False
        try:
            with db.begin_nested():
                know03_present = db.query(models.I5ClinicalStudy).count() > 0
        except Exception:
            know03_present = False
        if not know03_present:
            for art in (
                db.query(models.I5ScientificArtifact)
                .filter(models.I5ScientificArtifact.artifact_key.like("fixture:%"))
                .all()
            ):
                db.delete(art)
            for c in (
                db.query(models.I5ClinicalConcept)
                .filter(
                    (models.I5ClinicalConcept.concept_key.like("disease:%"))
                    | (models.I5ClinicalConcept.concept_key.like("family:%"))
                    | (models.I5ClinicalConcept.concept_key.like("population:%"))
                )
                .all()
            ):
                db.delete(c)
        else:
            # KNOW-03/KNOW-04 own RESTRICT FKs into shared taxonomy/artifacts — reseed upsert-only.
            for art in (
                db.query(models.I5ScientificArtifact)
                .filter(
                    models.I5ScientificArtifact.artifact_key.like("fixture:%"),
                    ~models.I5ScientificArtifact.artifact_key.like("fixture:know03:%"),
                    ~models.I5ScientificArtifact.artifact_key.like("fixture:know04:%"),
                )
                .all()
            ):
                referenced = (
                    db.query(models.I5ClinicalStudy)
                    .filter(models.I5ClinicalStudy.primary_artifact_id == art.id)
                    .count()
                )
                if referenced:
                    continue
                version_ids = [
                    v.id
                    for v in db.query(models.I5ScientificArtifactVersion).filter_by(artifact_id=art.id).all()
                ]
                if version_ids:
                    if (
                        db.query(models.I5ClinicalRecommendation)
                        .filter(models.I5ClinicalRecommendation.source_artifact_version_id.in_(version_ids))
                        .count()
                    ):
                        continue
                    if hasattr(models, "I5ScientificChangeEvent") and (
                        db.query(models.I5ScientificChangeEvent)
                        .filter(
                            (models.I5ScientificChangeEvent.artifact_id == art.id)
                            | (models.I5ScientificChangeEvent.artifact_version_id.in_(version_ids))
                        )
                        .count()
                    ):
                        continue
                elif hasattr(models, "I5ScientificChangeEvent") and (
                    db.query(models.I5ScientificChangeEvent)
                    .filter(models.I5ScientificChangeEvent.artifact_id == art.id)
                    .count()
                ):
                    continue
                db.delete(art)
        db.commit()

        summary = seed_know02_foundation(db)
        db.commit()
        assert summary["p0_specific_branching_in_core_schema"] == 0
        assert summary["icd11_full_import"] == "NEXT_TERMINOLOGY_WAVE"

        # ALS/MS/Diabetes in universal taxonomy + P0 overlay
        als = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:als").one()
        ms = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:ms").one()
        dm = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:diabetes_mellitus").one()
        assert als.root_category == SediRootCategory.NERVOUS_SYSTEM.value
        assert ms.root_category == SediRootCategory.NERVOUS_SYSTEM.value
        assert dm.root_category == SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value
        overlays = db.query(models.I5SediPriorityOverlay).filter_by(active=True).all()
        assert any(o.priority_class == SediCoveragePriority.P0_CRITICAL.value for o in overlays)

        # Non-P0 diseases exist
        for key in (
            "disease:hypertension",
            "disease:influenza",
            "disease:breast_cancer",
            "disease:major_depression",
            "disease:asthma",
            "disease:ckd",
        ):
            assert db.query(models.I5ClinicalConcept).filter_by(concept_key=key).one()

        # Query: ALS + respiratory care
        als_resp = query_kus_by_concept_and_dimension(
            db, concept_id=als.id, dimension_code=KnowledgeDimensionCode.RESPIRATORY_CARE.value
        )
        assert als_resp

        # MS + exercise
        ms_ex = query_kus_by_concept_and_dimension(
            db, concept_id=ms.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value
        )
        assert ms_ex

        t2 = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:diabetes:t2").one()
        t2_nut = query_kus_by_concept_and_dimension(
            db, concept_id=t2.id, dimension_code=KnowledgeDimensionCode.NUTRITION.value
        )
        assert t2_nut

        # Cross-disease claim F
        ku_f = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:f:cross_exercise")
            .one()
        )
        concepts_f = (
            db.query(models.I5KnowledgeUnitConcept).filter_by(knowledge_unit_id=ku_f.id).all()
        )
        assert len(concepts_f) >= 3

        # Healthy population claim G
        healthy = db.query(models.I5ClinicalConcept).filter_by(concept_key="population:healthy").one()
        healthy_kus = query_kus_by_concept_and_dimension(
            db, concept_id=healthy.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value
        )
        assert healthy_kus

        # Multi-evidence: claim A has >=2 links; claim B has SUPPORTS + CONTRADICTS
        ku_a = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:a:als_resp")
            .one()
        )
        links_a = (
            db.query(models.I5KnowledgeUnitEvidenceLink).filter_by(knowledge_unit_id=ku_a.id).all()
        )
        assert len(links_a) >= 2

        ku_b = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:b:ms_exercise")
            .one()
        )
        dirs = {
            l.support_direction
            for l in db.query(models.I5KnowledgeUnitEvidenceLink)
            .filter_by(knowledge_unit_id=ku_b.id)
            .all()
        }
        assert EvidenceSupportDirection.SUPPORTS.value in dirs
        assert EvidenceSupportDirection.CONTRADICTS.value in dirs

        # Retracted-only cannot support runtime
        ku_d = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:d:retracted_only")
            .one()
        )
        links_d = (
            db.query(models.I5KnowledgeUnitEvidenceLink).filter_by(knowledge_unit_id=ku_d.id).all()
        )
        versions = {
            v.id: v
            for v in db.query(models.I5ScientificArtifactVersion).all()
        }
        assert claim_has_only_retracted_support(links_d, versions) is True
        assert supporting_links_for_runtime(links_d, versions) == []
        ret_v = versions[summary["retracted_version_id"]]
        assert runtime_evidence_allowed(ret_v) is False
        assert ret_v.version_state == ArtifactVersionState.RETRACTED.value

        with pytest.raises(PermissionError):
            link_evidence(
                db,
                knowledge_unit_id=ku_d.id,
                artifact_version_id=ret_v.id,
                support_direction=EvidenceSupportDirection.SUPPORTS.value,
                enforce_runtime_support=True,
            )

        # Claim details exist
        assert db.query(models.I5KnowledgeClaimDetail).count() >= 5

        # Artifact version immutability: same label+hash idempotent; different hash conflicts
        from backend.app.services.i5.know02.artifacts import ContentDriftConflict, add_artifact_version

        art = db.query(models.I5ScientificArtifact).filter_by(artifact_key="fixture:rct:ms_exercise").one()
        existing = (
            db.query(models.I5ScientificArtifactVersion)
            .filter_by(artifact_id=art.id, version_label="1")
            .one()
        )
        v1b = add_artifact_version(
            db, artifact_id=art.id, version_label="1", content_hash=existing.content_hash
        )
        assert existing.id == v1b.id
        with pytest.raises(ContentDriftConflict):
            add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="b" * 64)

        # Source → artifact → version → evidence → KU → concept → dimension
        assert art.source_profile_id is not None
        sav = db.query(models.I5ScientificArtifactVersion).filter_by(artifact_id=art.id).first()
        link = (
            db.query(models.I5KnowledgeUnitEvidenceLink)
            .filter_by(artifact_version_id=sav.id)
            .first()
        )
        assert link is not None
        assert (
            db.query(models.I5KnowledgeUnitConcept)
            .filter_by(knowledge_unit_id=link.knowledge_unit_id)
            .count()
            >= 1
        )
        assert (
            db.query(models.I5KnowledgeUnitDimension)
            .filter_by(knowledge_unit_id=link.knowledge_unit_id)
            .count()
            >= 1
        )

        # Sleep/daily-routine
        osa = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:osa").one()
        assert query_kus_by_concept_and_dimension(
            db, concept_id=osa.id, dimension_code=KnowledgeDimensionCode.DAILY_ROUTINE.value
        )

        # Terminology releases present
        assert (
            db.query(models.I5TerminologyRelease)
            .filter_by(terminology_system="ICD11")
            .count()
            >= 1
        )
        assert (
            db.query(models.I5TerminologyRelease).filter_by(terminology_system="ICF").count() >= 1
        )
        assert (
            db.query(models.I5TerminologyRelease).filter_by(terminology_system="ICHI").count() >= 1
        )
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def db():
    """Isolated session for --noconftest CI. Does not commit synthetic labels."""
    url = _pg_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _ku(db, *, canonical: str, statement: str, **overrides):
    import hashlib

    from backend.app import models

    digest = hashlib.sha256(f"{canonical}|{statement}".encode()).hexdigest()
    fields = dict(
        canonical_unit_id=canonical,
        immutable_version_id="v1",
        domain="neurology",
        language="en",
        knowledge_type="GUIDELINE",
        normalized_statement=statement,
        evidence_strength="MODERATE",
        medical_safety_state="CLEARED",
        conflict_state="NONE",
        freshness_state="CURRENT",
        review_state="APPROVED",
        publication_state="PUBLISHED",
        runtime_eligibility="ELIGIBLE",
        provenance_complete=True,
        deduplication_key=digest,
        canonical_hash=digest,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    fields.update(overrides)
    row = models.KnowledgeUnit(**fields)
    db.add(row)
    db.flush()
    return row


def _concept(db, *, key: str, name: str, status: str = "ACTIVE"):
    from backend.app import models

    row = models.I5ClinicalConcept(
        concept_key=key,
        preferred_name=name,
        normalized_name=name.strip().lower(),
        concept_type="DISEASE",
        status=status,
    )
    db.add(row)
    db.flush()
    return row


def _label(db, concept, *, language: str, text: str, verified: bool):
    from backend.app.services.i5.know02.taxonomy import add_label

    return add_label(
        db,
        concept_id=concept.id,
        language=language,
        label_kind="COMMON_NAME",
        label_text=text,
        verified=verified,
        provenance_note="TEST_ONLY synthetic label; not a governed translation",
    )


def _evidence(ku, *, language: str, rank: int = 1):
    from backend.app.services.scis.contracts import ProvenanceRef, ScisEvidenceItem

    return ScisEvidenceItem(
        label="GLOBAL_GOVERNED_KNOWLEDGE",
        chunk_id=int(ku.id),
        content=str(ku.normalized_statement),
        language=language,
        knowledge_unit_id=int(ku.id),
        immutable_version_id="v1",
        retrieval_branch="vector",
        lexical_rank=None,
        vector_rank=rank,
        fusion_rank=rank,
        fusion_score=1.0,
        runtime_eligibility=str(ku.runtime_eligibility),
        embedding_model="fake",
        embedding_version=None,
        provenance=ProvenanceRef(
            chunk_id=int(ku.id),
            knowledge_unit_id=int(ku.id),
            immutable_version_id="v1",
            raw_evidence_id=None,
            source_profile_id=None,
        ),
    )


def _patch_retrieve(monkeypatch, evidence):
    from backend.app.services.scis.contracts import FallbackState, ScisRetrievalResponse

    calls = {"n": 0}

    def _retrieve(*_a, **_k):
        calls["n"] += 1
        return ScisRetrievalResponse(
            request_trace_id="k81b",
            mode="hybrid",
            language="en",
            evidence=list(evidence),
            fallback_state=FallbackState.VECTOR_ONLY,
        )

    monkeypatch.setattr(
        "backend.app.services.scis.governed_runtime_adapter.retrieve",
        _retrieve,
    )
    monkeypatch.setattr(
        "backend.app.services.scis.context_aware_retrieval.retrieve",
        _retrieve,
    )
    return calls


def test_verified_concept_authority_fail_closed_rules(db):
    from backend.app.services.i5.know02.taxonomy import (
        link_ku_concept,
        resolve_verified_concept_authority,
    )

    cardio = _concept(db, key="disease:k81b:cardio", name="K81B Cardio")
    metabolic = _concept(db, key="disease:k81b:metabolic", name="K81B Metabolic")
    neuro = _concept(db, key="disease:k81b:neuro", name="K81B Neuro")
    inactive = _concept(db, key="disease:k81b:inactive", name="K81B Inactive", status="INACTIVE")
    _label(db, cardio, language="en", text="k81bcardioalpha", verified=True)
    _label(db, cardio, language="en", text="k81bcardioalias", verified=True)
    _label(db, metabolic, language="fa", text="k81bfametabolic", verified=True)
    _label(db, neuro, language="ar", text="k81barneuro", verified=True)
    _label(
        db,
        neuro,
        language="fa",
        text="اسکلروز جانبی آمیوتروفیک",
        verified=False,
    )
    _label(db, inactive, language="en", text="k81binactive", verified=True)
    _label(db, cardio, language="en", text="k81bsharedmarker", verified=True)
    _label(db, metabolic, language="en", text="k81bsharedmarker", verified=True)

    hit = resolve_verified_concept_authority(
        db, "What daily care applies to k81bcardioalpha today?", "en"
    )
    assert hit is not None
    assert hit.concept_key == "disease:k81b:cardio"
    alias = resolve_verified_concept_authority(db, "review k81bcardioalias now", "en-US")
    assert alias is not None and alias.concept_id == hit.concept_id

    assert resolve_verified_concept_authority(db, "xk81bcardioalphay without boundaries", "en") is None
    assert (
        resolve_verified_concept_authority(
            db, "پرسش درباره اسکلروز جانبی آمیوتروفیک", "fa"
        )
        is None
    )
    assert resolve_verified_concept_authority(db, "please discuss k81binactive", "en") is None
    assert resolve_verified_concept_authority(db, "both k81bsharedmarker topics", "en") is None

    linked = _ku(db, canonical="k81b-cardio-en", statement="Linked synthetic cardio unit.")
    link_ku_concept(db, knowledge_unit_id=linked.id, concept_id=cardio.id)
    again = resolve_verified_concept_authority(db, "care for k81bcardioalpha", "en")
    assert again is not None
    assert again.knowledge_unit_ids == (int(linked.id),)


def test_concept_boundary_blocks_unrelated_and_ineligible_evidence(db, monkeypatch):
    from backend.app.services.i5.know02.taxonomy import link_ku_concept
    from backend.app.services.scis.governed_runtime_adapter import (
        retrieve_scis_governed_runtime_items,
    )

    concept = _concept(db, key="disease:k81b:serve", name="K81B Serve")
    _label(db, concept, language="fa", text="k81bfaserve", verified=True)
    _label(db, concept, language="ar", text="k81barserve", verified=True)
    linked = _ku(db, canonical="k81b-serve-en", statement="Authorized English unit.")
    unrelated = _ku(db, canonical="k81b-serve-other", statement="Unrelated English unit.")
    withdrawn = _ku(
        db,
        canonical="k81b-serve-withdrawn",
        statement="Withdrawn linked unit.",
        publication_state="WITHDRAWN",
        runtime_eligibility="NOT_ELIGIBLE",
    )
    retracted = _ku(
        db,
        canonical="k81b-serve-retracted",
        statement="Retracted linked unit.",
        retraction_reason="TEST_RETRACTED",
        runtime_eligibility="REVOKED",
        publication_state="WITHDRAWN",
    )
    missing_prov = _ku(
        db,
        canonical="k81b-serve-noprov",
        statement="Provenance incomplete linked unit.",
        provenance_complete=False,
        runtime_eligibility="NOT_ELIGIBLE",
    )
    for row in (linked, withdrawn, retracted, missing_prov):
        link_ku_concept(db, knowledge_unit_id=row.id, concept_id=concept.id)

    calls = _patch_retrieve(
        monkeypatch,
        [
            _evidence(linked, language="en", rank=1),
            _evidence(unrelated, language="en", rank=2),
            _evidence(withdrawn, language="en", rank=3),
            _evidence(retracted, language="en", rank=4),
            _evidence(missing_prov, language="en", rank=5),
        ],
    )
    items, meta = retrieve_scis_governed_runtime_items(
        db,
        "راهنمای k81bfaserve",
        language="fa",
        allow_network=False,
    )
    assert calls["n"] == 1
    assert [i.knowledge_unit_id for i in items] == [int(linked.id)]
    assert meta["concept_authority_applied"] is True
    assert meta["concept_key"] == "disease:k81b:serve"
    assert meta["authorized_ku_count"] == 4
    assert meta["cross_language_authorized"] is True

    items_ar, meta_ar = retrieve_scis_governed_runtime_items(
        db,
        "دليل k81barserve",
        language="ar",
        allow_network=False,
    )
    assert [i.knowledge_unit_id for i in items_ar] == [int(linked.id)]
    assert meta_ar["cross_language_authorized"] is True
    assert calls["n"] == 2


def test_concept_authority_overfetch_recovers_rank7(db, monkeypatch):
    from backend.app.services.i5.know02.taxonomy import link_ku_concept
    from backend.app.services.scis.contracts import FallbackState, ScisRetrievalResponse
    from backend.app.services.scis.governed_runtime_adapter import (
        retrieve_scis_governed_runtime_items,
    )

    concept = _concept(db, key="disease:k81b:recall", name="K81B Recall")
    _label(db, concept, language="fa", text="k81bfarecall", verified=True)
    linked = _ku(db, canonical="k81b-recall-linked", statement="Authorized rank-seven unit.")
    link_ku_concept(db, knowledge_unit_id=linked.id, concept_id=concept.id)
    negatives = [
        _ku(db, canonical=f"k81b-recall-neg-{i}", statement=f"Unrelated eligible unit {i}.")
        for i in range(6)
    ]
    evidence = [
        _evidence(row, language="en", rank=i)
        for i, row in enumerate(negatives, start=1)
    ]
    evidence.append(_evidence(linked, language="en", rank=7))
    calls = {"n": 0, "top_k": None}

    def _retrieve(_db, request, **_k):
        calls["n"] += 1
        calls["top_k"] = request.top_k
        return ScisRetrievalResponse(
            request_trace_id="k81b-recall",
            mode="lexical",
            language="fa",
            evidence=list(evidence),
            fallback_state=FallbackState.NONE,
        )

    monkeypatch.setattr(
        "backend.app.services.scis.governed_runtime_adapter.retrieve",
        _retrieve,
    )
    items, meta = retrieve_scis_governed_runtime_items(
        db,
        "پرسش k81bfarecall",
        language="fa",
        limit=3,
        allow_network=False,
    )
    assert calls["n"] == 1
    assert calls["top_k"] == 8
    assert [i.knowledge_unit_id for i in items] == [int(linked.id)]
    assert len(items) <= 3
    assert meta["concept_authority_applied"] is True
    assert meta["cross_language_authorized"] is True

    calls["n"] = 0
    calls["top_k"] = None
    plain, plain_meta = retrieve_scis_governed_runtime_items(
        db,
        "ordinary english monitoring question",
        language="en",
        limit=3,
        allow_network=False,
    )
    assert calls["n"] == 1
    assert calls["top_k"] == 3
    assert len(plain) <= 3
    assert plain_meta["concept_authority_applied"] is False
    assert int(linked.id) not in {i.knowledge_unit_id for i in plain}


def test_zero_links_fail_closed_and_same_language_unchanged(db, monkeypatch):
    from backend.app.services.scis.governed_runtime_adapter import (
        retrieve_scis_governed_runtime_items,
    )

    empty = _concept(db, key="disease:k81b:empty", name="K81B Empty")
    _label(db, empty, language="en", text="k81bemptyconcept", verified=True)
    bystander = _ku(db, canonical="k81b-bystander", statement="Unrelated same-language unit.")
    calls = _patch_retrieve(monkeypatch, [_evidence(bystander, language="en")])
    items, meta = retrieve_scis_governed_runtime_items(
        db,
        "tell me about k81bemptyconcept",
        language="en",
        allow_network=False,
    )
    assert items == []
    assert calls["n"] == 0
    assert meta["concept_authority_applied"] is True
    assert meta["authorized_ku_count"] == 0
    assert meta["cross_language_authorized"] is False

    calls["n"] = 0
    kept, kept_meta = retrieve_scis_governed_runtime_items(
        db,
        "ordinary english monitoring question",
        language="en",
        allow_network=False,
    )
    assert calls["n"] == 1
    assert [i.knowledge_unit_id for i in kept] == [int(bystander.id)]
    assert kept_meta["concept_authority_applied"] is False
    assert kept_meta["cross_language_authorized"] is False

    calls["n"] = 0
    blocked, blocked_meta = retrieve_scis_governed_runtime_items(
        db,
        "پرسش بدون برچسب تاییدشده",
        language="fa",
        allow_network=False,
    )
    assert calls["n"] == 1
    assert blocked == []
    assert blocked_meta["concept_authority_applied"] is False
    assert blocked_meta["cross_language_authorized"] is False


def test_context_aware_cannot_leak_cross_language_without_concept(db, monkeypatch):
    from backend.app.services.scis.context_aware_retrieval import retrieve_sedi_evidence_package
    from backend.app.services.scis.context_resolver import PURPOSE_GOVERNED_RETRIEVAL
    from backend.app.services.scis.sedi_retrieval_context import SediRetrievalContext, SubjectMode

    en_ku = _ku(db, canonical="k81b-context-en", statement="English evidence only.")
    calls = _patch_retrieve(monkeypatch, [_evidence(en_ku, language="en")])
    ctx = SediRetrievalContext(
        requester_account_id=1,
        target_health_subject_id=1,
        subject_mode=SubjectMode.SELF,
        relationship="SELF",
        authorization_scope=("I5_GOVERNED_KNOWLEDGE",),
        purpose=PURPOSE_GOVERNED_RETRIEVAL,
        language="fa",
        linked_user_id=1,
        trace_id="k81b-fa",
    )
    package, meta = retrieve_sedi_evidence_package(
        db,
        "پرسش بدون هویت مفهومی",
        ctx,
        allow_network=False,
        force_mode=None,
    )
    assert calls["n"] == 1
    assert package.evidence == []
    assert meta["concept_authority_applied"] is False
    assert meta["cross_language_authorized"] is False


def test_concept_authority_wiring_does_not_add_retrieval_or_change_be_heard():
    import inspect

    from backend.app.core.conversation import brain as brain_mod
    from backend.app.services.i5 import runtime_knowledge_retrieval as rkr
    from backend.app.services.scis import context_aware_retrieval as car
    from backend.app.services.scis import governed_runtime_adapter as gra

    brain_src = inspect.getsource(brain_mod.ConversationBrain.process_message)
    assert brain_src.count("retrieve_knowledge_context(") == 1
    assert "if allow_governed_knowledge:" in brain_src
    helper = inspect.getsource(brain_mod._maybe_append_structured_governed_knowledge)
    assert helper.count("retrieve_knowledge_context(") == 1
    assert "query_kus_by_concept_and_dimension" not in helper

    retrieval_src = inspect.getsource(rkr.retrieve_knowledge_context)
    assert retrieval_src.count("retrieve_scis_governed_runtime_items(") == 1
    adapter_src = inspect.getsource(gra.retrieve_scis_governed_runtime_items)
    assert adapter_src.count("retrieve(") == 2
    assert "query_kus_by_concept_and_dimension" not in adapter_src
    context_src = inspect.getsource(car.retrieve_sedi_evidence_package)
    assert context_src.count("retrieve(") == 2
    assert "filter_scis_evidence_for_governed_boundary(" in context_src

    seed = Path("backend/app/services/i5/know02/seed_fixtures.py").read_text(encoding="utf-8")
    assert 'language="fa"' in seed
    assert "verified=False" in seed
    assert 'language="ar"' not in seed
