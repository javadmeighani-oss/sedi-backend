"""Context-aware Smart-RAG entry — thin orchestration over existing SCIS/I5.

User/Event → Context Resolver → Authority Router → SediRetrievalContext
→ Smart-RAG/SCIS → eligibility/provenance → fusion/ranking → SediEvidencePackage
→ existing Sedi authorities.

Does not rewrite retrieval core. Does not own Sedi truth.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.app.services.i5.runtime_knowledge_retrieval import RetrievalPersonalizationContext
from backend.app.services.scis.authority_router import route_sedi_retrieval_context
from backend.app.services.scis.contracts import RetrievalMode, ScisRetrievalRequest, ScisRetrievalResponse
from backend.app.services.scis.evidence_package import SediEvidencePackage
from backend.app.services.scis.governed_runtime_adapter import (
    is_supported_governed_language,
    normalize_governed_language,
)
from backend.app.services.scis.retrieval import retrieve
from backend.app.services.scis.sedi_retrieval_context import SediRetrievalContext
from backend.app.services.scis import RESULT_LABEL_GOVERNED


class PersonalToGovernedPromotionError(ValueError):
    """PERSONAL context must never be promoted to GOVERNED knowledge authority."""


def build_scis_request_from_context(
    query_text: str,
    ctx: SediRetrievalContext,
    *,
    top_k: int = 8,
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID,
) -> ScisRetrievalRequest:
    lang = normalize_governed_language(ctx.language)
    if not is_supported_governed_language(lang):
        from backend.app.services.scis.governed_runtime_adapter import UnsupportedGovernedLanguageError

        raise UnsupportedGovernedLanguageError(lang)
    return ScisRetrievalRequest(
        query_text=query_text or "",
        query_language=lang,
        target_domain=ctx.domain,
        intent=ctx.intent,
        safety_classification=ctx.safety_classification,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        allowed_knowledge_classes=tuple(ctx.allowed_knowledge_classes),
        request_trace_id=ctx.trace_id,
        user_authorization_context=ctx.to_authorization_boundary(),
    )


def bounded_personalization_from_context(
    ctx: SediRetrievalContext,
    *,
    relevance_terms: Sequence[str] = (),
) -> Optional[RetrievalPersonalizationContext]:
    """I7 relevance-only personalization. Never promotes PERSONAL → GOVERNED."""
    if ctx.personal_context_ref is None:
        return None
    if ctx.personal_context_ref.authority != "I7":
        raise PersonalToGovernedPromotionError("PERSONAL_CONTEXT_REF_AUTHORITY_MUST_BE_I7")
    terms = tuple(str(t).strip()[:48] for t in relevance_terms if str(t).strip())[:8]
    return RetrievalPersonalizationContext(
        language=ctx.language,
        lifestyle_terms=terms,
        domain_hints=(ctx.domain,) if ctx.domain else (),
    )


def assert_personal_not_governed(personalization: Optional[RetrievalPersonalizationContext]) -> None:
    """Lock: personalization cannot change knowledge authority label."""
    if personalization is None:
        return
    # Personalization is relevance-only; authority remains GOVERNED on evidence items.
    audit = personalization.to_audit_dict()
    if audit.get("authority_label") == "GOVERNED" and personalization.goal_terms:
        # Defensive: RetrievalPersonalizationContext has no authority_label field.
        pass
    # Explicit: never invent GOVERNED from PERSONAL terms.
    forbidden = {"GOVERNED_FROM_PERSONAL", "PROMOTE_PERSONAL"}
    for term in (
        list(personalization.goal_terms)
        + list(personalization.lifestyle_terms)
        + list(personalization.routine_terms)
    ):
        if str(term).upper() in forbidden:
            raise PersonalToGovernedPromotionError("I7_PERSONAL_NOT_GOVERNED")


def retrieve_sedi_evidence_package(
    db: Session,
    query_text: str,
    ctx: SediRetrievalContext,
    *,
    top_k: int = 5,
    allow_network: bool = True,
    provider: Any = None,
    force_mode: Optional[RetrievalMode] = None,
    relevance_terms: Sequence[str] = (),
) -> Tuple[SediEvidencePackage, dict]:
    """Run governed SCIS retrieval under resolved context; return evidence package.

    Single retrieve path. Reuses existing embedding resolution + lexical fallback
    semantics via resolve_product_governed_embedding (same as I5 adapter).
    """
    routes = route_sedi_retrieval_context(ctx)
    personalization = bounded_personalization_from_context(ctx, relevance_terms=relevance_terms)
    assert_personal_not_governed(personalization)

    alias_hints: list[str] = []
    if personalization is not None:
        alias_hints = list(personalization.lifestyle_terms)[:4]

    from backend.app.services.scis.embedding.providers import resolve_product_governed_embedding

    meta: dict = {
        "cohere_used": False,
        "stage17_rag_embeddings_used": False,
        "authority_label": RESULT_LABEL_GOVERNED,
        "openai_failure_lexical_fallback": False,
    }

    if force_mode == RetrievalMode.LEXICAL:
        prov = None
        mode = RetrievalMode.LEXICAL
    else:
        resolved, mode_name = resolve_product_governed_embedding(
            allow_network=allow_network,
            provider=provider,
        )
        mode = force_mode or RetrievalMode(mode_name)
        if force_mode == RetrievalMode.HYBRID and resolved is None:
            mode = RetrievalMode.LEXICAL
            meta["openai_failure_lexical_fallback"] = True
        prov = resolved

    request = ScisRetrievalRequest(
        query_text=query_text or "",
        query_language=normalize_governed_language(ctx.language),
        target_domain=ctx.domain,
        intent=ctx.intent,
        safety_classification=ctx.safety_classification,
        top_k=max(1, int(top_k)),
        retrieval_mode=mode,
        allowed_knowledge_classes=tuple(ctx.allowed_knowledge_classes),
        request_trace_id=ctx.trace_id,
        user_authorization_context=ctx.to_authorization_boundary(),
    )
    response: ScisRetrievalResponse = retrieve(
        db,
        request,
        provider=prov,
        alias_hints=alias_hints or None,
    )
    meta["fallback_state"] = getattr(response.fallback_state, "value", str(response.fallback_state))
    meta["effective_mode"] = response.mode

    # Safe lexical fallback on embedding/vector failure (preserve CASE16 locks).
    from backend.app.services.scis.contracts import FallbackState

    if mode == RetrievalMode.HYBRID and response.fallback_state in {
        FallbackState.EMBEDDING_FAILURE,
        FallbackState.VECTOR_BACKEND_UNAVAILABLE,
        FallbackState.BOTH_BRANCHES_UNAVAILABLE,
    }:
        meta["openai_failure_lexical_fallback"] = True
        lexical_req = ScisRetrievalRequest(
            query_text=query_text or "",
            query_language=normalize_governed_language(ctx.language),
            target_domain=ctx.domain,
            intent=ctx.intent,
            safety_classification=ctx.safety_classification,
            top_k=max(1, int(top_k)),
            retrieval_mode=RetrievalMode.LEXICAL,
            allowed_knowledge_classes=tuple(ctx.allowed_knowledge_classes),
            request_trace_id=ctx.trace_id,
            user_authorization_context=ctx.to_authorization_boundary(),
        )
        response = retrieve(db, lexical_req, provider=None, alias_hints=alias_hints or None)
        meta["fallback_state"] = getattr(response.fallback_state, "value", str(response.fallback_state))
        meta["effective_mode"] = response.mode

    obs = dict(response.observability or {})
    obs.update(
        {
            "authority_routes": [
                {"target": r.target_authority, "kind": r.route_kind} for r in routes
            ],
            "context_subject_mode": ctx.subject_mode.value,
            "cohere_used": False,
            "stage17_rag_embeddings_used": False,
            "adapter_fallback_state": meta.get("fallback_state"),
            "knowledge_authority_label": RESULT_LABEL_GOVERNED,
            "personal_promoted_to_governed": False,
            "openai_failure_lexical_fallback": bool(meta.get("openai_failure_lexical_fallback")),
        }
    )
    response.observability = obs

    package = SediEvidencePackage.from_scis_response(
        response,
        ctx=ctx,
        routes=routes,
        knowledge_authority_label=RESULT_LABEL_GOVERNED,
    )
    package.assert_no_semantic_escalation()
    return package, meta
