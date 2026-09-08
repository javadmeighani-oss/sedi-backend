"""SCIS → I5 runtime retrieval adapter (Phase1 hybrid foundation).

Canonical governed path: SCIS HYBRID (lexical + KCE 1024 semantic) with
KnowledgeUnit revalidation. OpenAI failure → SAFE_CANONICAL_LEXICAL.
Stage17 rag_embeddings and Cohere are never used here.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.runtime_knowledge_retrieval import RetrievedKnowledgeItem
from backend.app.services.scis import RESULT_LABEL_GOVERNED
from backend.app.services.scis.contracts import FallbackState, RetrievalMode, ScisRetrievalRequest
from backend.app.services.scis.embedding.providers import (
    ScisEmbeddingProvider,
    resolve_product_governed_embedding,
)
from backend.app.services.scis.retrieval import retrieve

# Bounded serving context (chars per evidence statement).
MAX_SERVING_CONTEXT_CHARS = 600
DEFAULT_SERVING_TOP_K = 5

# Phase1 supported languages for governed semantic/hybrid retrieval.
_SUPPORTED_LANG_ROOTS = frozenset({"fa", "en", "ar"})
_SUPPORTED_LANG_ALIASES = frozenset(
    {
        "fa",
        "en",
        "ar",
        "persian",
        "farsi",
        "arabic",
        "fa-ir",
        "en-us",
        "en-gb",
        "ar-sa",
        "ar-eg",
    }
)


class UnsupportedGovernedLanguageError(ValueError):
    """Governed semantic/hybrid retrieval refused for unsupported language."""

    def __init__(self, language: str) -> None:
        self.language = language
        super().__init__(f"UNSUPPORTED_GOVERNED_LANGUAGE:{language}")


def normalize_governed_language(language: Optional[str]) -> str:
    if language is None or not str(language).strip():
        return "en"
    return str(language).strip().lower()


def is_supported_governed_language(language: Optional[str]) -> bool:
    lang = normalize_governed_language(language)
    if lang in _SUPPORTED_LANG_ALIASES:
        return True
    root = lang.split("-", 1)[0]
    return root in _SUPPORTED_LANG_ROOTS


def _lang_matches(item_lang: Optional[str], filter_lang: Optional[str]) -> bool:
    if not filter_lang:
        return True
    fl = filter_lang.strip().lower()
    il = (item_lang or "").strip().lower()
    if not fl:
        return True
    if not il:
        return False
    return il == fl or il.startswith(fl) or fl.startswith(il[:2])


def _map_evidence_to_items(
    db: Session,
    evidence: Sequence[Any],
    *,
    language: Optional[str],
    domain: Optional[str],
    top_k: int,
    mode_tag: str,
) -> List[RetrievedKnowledgeItem]:
    from backend.app import models

    ku_ids = [e.knowledge_unit_id for e in evidence if e.knowledge_unit_id is not None]
    units: dict[int, Any] = {}
    if ku_ids:
        for ku in db.query(models.KnowledgeUnit).filter(models.KnowledgeUnit.id.in_(ku_ids)).all():
            units[int(ku.id)] = ku

    items: List[RetrievedKnowledgeItem] = []
    seen_canon: set[str] = set()
    for ev in evidence:
        if ev.knowledge_unit_id is None:
            continue
        ku = units.get(int(ev.knowledge_unit_id))
        if ku is None:
            continue
        if not _lang_matches(str(ku.language), language) and not _lang_matches(ev.language, language):
            continue
        if domain and str(ku.domain) != domain:
            continue
        if evaluate_knowledge_unit_eligibility(ku) != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            continue
        if str(ku.runtime_eligibility) != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            continue
        if not bool(ku.provenance_complete):
            continue
        if getattr(ku, "retraction_reason", None):
            continue
        pub = str(getattr(ku, "publication_state", "") or "")
        if pub in {"SUPERSEDED", "WITHDRAWN"}:
            continue
        if not ev.immutable_version_id:
            continue
        canon = str(ku.canonical_unit_id)
        if canon in seen_canon:
            continue
        seen_canon.add(canon)

        statement = (ev.content or str(ku.normalized_statement) or "").strip()
        if len(statement) > MAX_SERVING_CONTEXT_CHARS:
            statement = statement[: MAX_SERVING_CONTEXT_CHARS - 1].rstrip() + "…"

        prov = ev.provenance
        rank = int(ev.fusion_rank or ev.lexical_rank or ev.vector_rank or (len(items) + 1))
        branch = str(getattr(ev, "retrieval_branch", None) or "lexical")
        items.append(
            RetrievedKnowledgeItem(
                knowledge_unit_id=int(ku.id),
                canonical_unit_id=canon,
                immutable_version_id=str(ev.immutable_version_id),
                memory_item_id=f"SCIS_KCE:{int(ev.chunk_id)}",
                memory_row_id=0,
                source_profile_id=getattr(prov, "source_profile_id", None),
                provenance_id=None,
                raw_evidence_id=getattr(prov, "raw_evidence_id", None),
                domain=str(ku.domain),
                language=str(ku.language),
                topic_taxonomy=getattr(ku, "topic_taxonomy", None),
                normalized_statement=statement,
                evidence_strength=str(ku.evidence_strength),
                freshness_state=str(ku.freshness_state),
                conflict_state=str(ku.conflict_state),
                medical_safety_state=str(ku.medical_safety_state),
                runtime_eligibility=str(ku.runtime_eligibility),
                rank_score=max(1, 1000 - rank),
                inclusion_reasons=[
                    RESULT_LABEL_GOVERNED,
                    mode_tag,
                    "KU_ELIGIBLE_MATRIX",
                    "PROVENANCE_COMPLETE",
                    "CANONICAL_KU_REVALIDATED",
                    f"CHUNK:{int(ev.chunk_id)}",
                    f"BRANCH:{branch}",
                ],
            )
        )
        if len(items) >= top_k:
            break
    return items


def retrieve_scis_governed_runtime_items(
    db: Session,
    query: str,
    *,
    language: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = DEFAULT_SERVING_TOP_K,
    allow_network: bool = True,
    provider: Optional[ScisEmbeddingProvider] = None,
    force_mode: Optional[RetrievalMode] = None,
) -> Tuple[List[RetrievedKnowledgeItem], dict]:
    """Canonical governed I5 runtime: HYBRID when OpenAI available, else lexical.

    Unsupported language → raises UnsupportedGovernedLanguageError (fail-closed).
    """
    lang = normalize_governed_language(language)
    if not is_supported_governed_language(lang):
        raise UnsupportedGovernedLanguageError(lang)

    top_k = max(1, min(int(limit), DEFAULT_SERVING_TOP_K))
    meta: dict = {
        "requested_mode": None,
        "effective_mode": None,
        "fallback_state": None,
        "authority_label": RESULT_LABEL_GOVERNED,
        "openai_failure_lexical_fallback": False,
        "cohere_used": False,
        "stage17_rag_embeddings_used": False,
    }

    if force_mode == RetrievalMode.LEXICAL:
        mode = RetrievalMode.LEXICAL
        prov = None
    else:
        resolved, mode_name = resolve_product_governed_embedding(
            allow_network=allow_network,
            provider=provider,
        )
        mode = RetrievalMode(mode_name) if force_mode is None else force_mode
        if force_mode == RetrievalMode.HYBRID and resolved is None:
            mode = RetrievalMode.LEXICAL
        elif force_mode is None:
            mode = RetrievalMode(mode_name)
        prov = resolved

    meta["requested_mode"] = (force_mode or mode).value
    meta["effective_mode"] = mode.value

    resp = retrieve(
        db,
        ScisRetrievalRequest(
            query_text=query or "",
            query_language=lang,
            target_domain=domain,
            top_k=top_k,
            retrieval_mode=mode,
        ),
        provider=prov,
    )
    meta["fallback_state"] = getattr(resp.fallback_state, "value", str(resp.fallback_state))

    # OpenAI / embedding failure → SAFE_CANONICAL_LEXICAL (never Cohere / Stage17).
    if mode == RetrievalMode.HYBRID and resp.fallback_state in {
        FallbackState.EMBEDDING_FAILURE,
        FallbackState.VECTOR_BACKEND_UNAVAILABLE,
        FallbackState.BOTH_BRANCHES_UNAVAILABLE,
    }:
        meta["openai_failure_lexical_fallback"] = True
        if not resp.evidence or resp.fallback_state == FallbackState.EMBEDDING_FAILURE:
            resp = retrieve(
                db,
                ScisRetrievalRequest(
                    query_text=query or "",
                    query_language=lang,
                    target_domain=domain,
                    top_k=top_k,
                    retrieval_mode=RetrievalMode.LEXICAL,
                ),
            )
            meta["effective_mode"] = RetrievalMode.LEXICAL.value
            meta["fallback_state"] = getattr(resp.fallback_state, "value", str(resp.fallback_state))

    mode_tag = (
        "SCIS_HYBRID"
        if meta["effective_mode"] == RetrievalMode.HYBRID.value
        else "SCIS_LEXICAL"
    )
    items = _map_evidence_to_items(
        db,
        resp.evidence,
        language=language,
        domain=domain,
        top_k=top_k,
        mode_tag=mode_tag,
    )
    return items, meta


def retrieve_scis_lexical_runtime_items(
    db: Session,
    query: str,
    *,
    language: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = DEFAULT_SERVING_TOP_K,
) -> List[RetrievedKnowledgeItem]:
    """Backward-compatible lexical-only entry (explicit LEXICAL force)."""
    items, _meta = retrieve_scis_governed_runtime_items(
        db,
        query,
        language=language,
        domain=domain,
        limit=limit,
        allow_network=False,
        force_mode=RetrievalMode.LEXICAL,
    )
    return items
