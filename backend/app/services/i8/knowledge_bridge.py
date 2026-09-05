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
from backend.app.services.i8.constants import MAX_KNOWLEDGE_REFS, OPERATIONAL_SUMMARY_LABELS, SUMMARY_TEXT_MAX_LEN
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
    from backend.app.services.i8.context import I8_PERSONAL_CONTEXT_TERM_SLICE

    habit_names = tuple(h.name for h in ctx.habits[:I8_PERSONAL_CONTEXT_TERM_SLICE] if h.name)
    event_types = tuple(
        e.event_type for e in ctx.lifestyle_events[:I8_PERSONAL_CONTEXT_TERM_SLICE] if e.event_type
    )
    # Habit names → routine_terms; lifestyle event types → lifestyle_terms (alongside conditions).
    # Mirrors I5 build_personalization_context_from_memory habit→lifestyle/routine pattern.
    lifestyle_terms = tuple(list(ctx.conditions[:4]) + list(event_types))[:I8_PERSONAL_CONTEXT_TERM_SLICE]
    return RetrievalPersonalizationContext(
        goal_terms=tuple(ctx.goals[:I8_PERSONAL_CONTEXT_TERM_SLICE]),
        restriction_terms=tuple(ctx.restrictions[:I8_PERSONAL_CONTEXT_TERM_SLICE]),
        lifestyle_terms=lifestyle_terms,
        routine_terms=habit_names,
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
    # I8 operational domains are not KU taxonomy keys — do not hard-filter SCIS by them.
    # Domain remains a personalization hint only. Serving is query-driven and side-effect free.
    return retrieve_knowledge_context(
        db,
        query,
        user_id=user_id,
        domain=None,
        enqueue_gap_on_empty=False,
        personalization=build_personalization(ctx, domain=domain),
    )


def retrieve_governed_knowledge_for_subject(
    db: Session,
    *,
    actor_account_user_id: int,
    health_subject_id: int,
    query: str,
    domain: str = "cross_domain",
) -> RetrievalResult:
    """Subject-aware I8 knowledge: actor Account ≠ patient HealthSubject.

    Authorizes AccountHealthSubjectAccess, loads Mother/managed conditions into
    personalization, retrieves governed SCIS evidence. Does not require linked_user_id.
    """
    from backend.app.services.i8.subject_context import (
        load_subject_trusted_context,
        to_i8_trusted_context_compat,
    )

    subject_ctx = load_subject_trusted_context(
        db,
        actor_account_user_id=actor_account_user_id,
        health_subject_id=health_subject_id,
    )
    ctx = to_i8_trusted_context_compat(subject_ctx)
    return retrieve_governed_knowledge(
        db,
        user_id=actor_account_user_id,
        query=query,
        domain=domain,
        ctx=ctx,
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
    ctx: Optional[I8TrustedContext] = None,
) -> Optional[GroundedComposition]:
    """Derive bounded action content from eligible I5 knowledge; optional personal context.

    Personal habit/lifestyle facts may annotate relevance only. They never replace I5 grounding.
    """
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
    personal_note = _personal_context_note(domain=domain, ctx=ctx)
    if personal_note:
        combined = f"{detail} {personal_note}".strip()
        detail = combined[:SUMMARY_TEXT_MAX_LEN]
    suggestions = [I8ActionSuggestion(label=label, detail=detail)]
    rationale = (
        f"Action derived from governed knowledge "
        f"{primary.canonical_unit_id}:{primary.immutable_version_id}."
    )
    if personal_note:
        rationale = f"{rationale} Personalized with bounded stored personal context (not clinical)."
    return GroundedComposition(
        suggestions=suggestions,
        used_items=used_items[:1],
        rationale=rationale,
    )


def _personal_context_note(*, domain: str, ctx: Optional[I8TrustedContext]) -> Optional[str]:
    """Non-clinical personal-context annotation for routine/lifestyle domains only."""
    if ctx is None:
        return None
    if domain == "routine" and ctx.habits:
        name = ctx.habits[0].name.strip()
        if name:
            return f"(Personal context: stored habit '{name[:64]}'.)"
    if domain == "lifestyle" and ctx.lifestyle_events:
        et = ctx.lifestyle_events[0].event_type.strip()
        if et:
            return f"(Personal context: recent lifestyle event type '{et[:64]}'.)"
    return None


def operational_summary_label(domain: str) -> str:
    return OPERATIONAL_SUMMARY_LABELS.get(domain, "Governed health action")


def build_persisted_operational_snapshot(
    *,
    domain: str,
    action_type: str,
    used_items: list[RetrievedKnowledgeItem],
    request_fingerprint: str,
    safety_state: str = "SAFE",
) -> tuple[str, dict]:
    """Sanitized durable I8 state: metadata and ID-only refs, no I5 statement text."""
    refs = json.loads(knowledge_refs_payload(used_items))
    summary_text = operational_summary_label(domain)
    presentation = {
        "domain": domain,
        "action_type": action_type,
        "grounding": "governed_i5_reference",
        "knowledge_unit_ids": [r["knowledge_unit_id"] for r in refs],
        "request_fingerprint": request_fingerprint,
        "safety_state": safety_state,
    }
    return summary_text, presentation
