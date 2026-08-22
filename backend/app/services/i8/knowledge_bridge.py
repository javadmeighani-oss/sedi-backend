"""I5 knowledge gateway boundary for I8 — no direct vector access."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i5.reference_renderer import extract_handoffs_from_retrieval
from backend.app.services.i5.runtime_knowledge_retrieval import (
    RetrievalPersonalizationContext,
    RetrievalResult,
    RetrievedKnowledgeItem,
    retrieve_knowledge_context,
    STATUS_OK,
)
from backend.app.services.i8.constants import MAX_KNOWLEDGE_REFS, SUMMARY_TEXT_MAX_LEN
from backend.app.services.i8.context import I8TrustedContext
from backend.app.services.i8.contracts import I8ActionSuggestion


@dataclass(frozen=True)
class GroundedComposition:
    suggestions: list[I8ActionSuggestion]
    used_items: list[RetrievedKnowledgeItem]
    rationale: str


_DOMAIN_LABELS: dict[str, str] = {
    "nutrition": "Nutrition action",
    "exercise": "Activity action",
    "routine": "Routine action",
    "lifestyle": "Lifestyle action",
    "wellbeing": "Wellbeing action",
    "cross_domain": "Cross-domain action",
}


def build_personalization(ctx: I8TrustedContext, *, domain: str) -> RetrievalPersonalizationContext:
    return RetrievalPersonalizationContext(
        goal_terms=tuple(ctx.goals[:8]),
        restriction_terms=tuple(ctx.restrictions[:8]),
        lifestyle_terms=tuple(ctx.conditions[:4]),
        domain_hints=(domain,) if domain != "cross_domain" else ("nutrition", "exercise", "routine"),
    )


def retrieve_governed_knowledge(
    db: Session,
    *,
    user_id: int,
    query: str,
    domain: str,
    ctx: I8TrustedContext,
) -> RetrievalResult:
    return retrieve_knowledge_context(
        db,
        query,
        user_id=user_id,
        domain=domain if domain != "cross_domain" else None,
        enqueue_gap_on_empty=False,
        personalization=build_personalization(ctx, domain=domain),
    )


def knowledge_refs_payload(items: list[RetrievedKnowledgeItem]) -> str:
    refs: list[dict[str, Any]] = []
    for item in items[:MAX_KNOWLEDGE_REFS]:
        refs.append(
            {
                "knowledge_unit_id": item.knowledge_unit_id,
                "immutable_version_id": item.immutable_version_id,
                "provenance_id": item.provenance_id,
                "source_profile_id": item.source_profile_id,
                "evidence_strength": item.evidence_strength,
            }
        )
    return json.dumps(refs)


def compose_grounded_action(
    retrieval: RetrievalResult,
    *,
    domain: str,
) -> Optional[GroundedComposition]:
    """Derive bounded action content only from eligible retrieved I5 knowledge."""
    if retrieval.status != STATUS_OK or not retrieval.items:
        return None

    handoffs = extract_handoffs_from_retrieval(retrieval)
    if not handoffs:
        return None

    primary = handoffs[0]
    statement = (primary.normalized_statement or "").strip()
    if not statement:
        return None

    used_items = [
        item
        for item in retrieval.items
        if item.knowledge_unit_id == primary.knowledge_unit_id
    ]
    if not used_items:
        used_items = [retrieval.items[0]]

    label = _DOMAIN_LABELS.get(domain, "Health action")
    detail = statement[:SUMMARY_TEXT_MAX_LEN]
    suggestions = [I8ActionSuggestion(label=label, detail=detail)]
    rationale = (
        f"Action derived from governed knowledge "
        f"{primary.canonical_unit_id}:{primary.immutable_version_id}."
    )
    return GroundedComposition(
        suggestions=suggestions,
        used_items=used_items[:1],
        rationale=rationale,
    )
