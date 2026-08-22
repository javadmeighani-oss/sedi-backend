"""I5 knowledge gateway boundary for I8 — no direct vector access."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i5.runtime_knowledge_retrieval import (
    RetrievalPersonalizationContext,
    RetrievalResult,
    RetrievedKnowledgeItem,
    retrieve_knowledge_context,
)
from backend.app.services.i8.constants import MAX_KNOWLEDGE_REFS
from backend.app.services.i8.context import I8TrustedContext


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
