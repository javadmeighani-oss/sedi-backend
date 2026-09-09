"""Authority Router Boundary — routes context/evidence to existing authorities.

NOT a new authority. Does not mint I4/I5/I6/I7/I8/I9/I10 semantics.
SMART_RAG_CANNOT_DIAGNOSE / MINT_I8 / MINT_I9 / MINT_I10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from backend.app.services.scis.sedi_retrieval_context import SediRetrievalContext, SubjectMode


@dataclass(frozen=True)
class AuthorityRoute:
    target_authority: str
    route_kind: str
    note: str


# Explicit non-ownership locks exposed for tests / observability.
ROUTER_IS_AUTHORITY = False
SMART_RAG_OWNS_SEDI_TRUTH = False
RANKING_CANNOT_INCREASE_AUTHORITY = True


def route_sedi_retrieval_context(ctx: SediRetrievalContext) -> Tuple[AuthorityRoute, ...]:
    """Produce ordered routes for orchestration. Router never executes authority."""
    routes: List[AuthorityRoute] = []

    # I6 consent already enforced by Context Resolver when personal context requested.
    if ctx.personal_context_ref is not None:
        routes.append(
            AuthorityRoute(
                target_authority="I6",
                route_kind="CONSENT_ALREADY_CHECKED",
                note="personal_or_managed_context_requires_active_consent",
            )
        )
        routes.append(
            AuthorityRoute(
                target_authority="I7",
                route_kind="BOUNDED_PERSONAL_RELEVANCE_REF",
                note="PERSONAL_NE_GOVERNED; relevance_only",
            )
        )

    # I5 is the sole governed knowledge retrieval authority for Smart-RAG evidence.
    routes.append(
        AuthorityRoute(
            target_authority="I5",
            route_kind="GOVERNED_KNOWLEDGE_RETRIEVAL",
            note="SCIS_HYBRID_EVIDENCE_ONLY",
        )
    )

    if ctx.device_status_ref is not None:
        routes.append(
            AuthorityRoute(
                target_authority="I9",
                route_kind="DEVICE_STATUS_CONTEXT_REF",
                note="STABLE_UNSTABLE_REF_ONLY;I9_CANNOT_DIAGNOSE",
            )
        )

    if ctx.governed_action_ref is not None:
        routes.append(
            AuthorityRoute(
                target_authority="I8",
                route_kind="EXISTING_ACTION_REF_INPUT",
                note="EVIDENCE_MAY_INFORM_I8;SMART_RAG_CANNOT_MINT_I8_ACTION",
            )
        )
    else:
        routes.append(
            AuthorityRoute(
                target_authority="I8",
                route_kind="EVIDENCE_INPUT_ONLY",
                note="RAG_EVIDENCE_CANNOT_MINT_I8_ACTION",
            )
        )

    if ctx.safety_classification:
        routes.append(
            AuthorityRoute(
                target_authority="I4",
                route_kind="CLINICAL_SAFETY_AUTHORITY_PRESERVED",
                note="SMART_RAG_CANNOT_DIAGNOSE;I4_SOLE_CLINICAL_SAFETY",
            )
        )
    else:
        routes.append(
            AuthorityRoute(
                target_authority="I4",
                route_kind="NO_CLINICAL_INTERPRETATION_FROM_RAG",
                note="I4_CLINICAL_SAFETY_AUTHORITY_PRESERVED",
            )
        )

    # I10 explicitly not routed / not mintable from Smart-RAG in this Gate.
    routes.append(
        AuthorityRoute(
            target_authority="I10",
            route_kind="NOT_TOUCHED",
            note="SMART_RAG_CANNOT_MINT_I10_SEMANTIC",
        )
    )

    # Identity isolation signal for family scenarios.
    if ctx.subject_mode == SubjectMode.SELF:
        routes.append(
            AuthorityRoute(
                target_authority="IDENTITY",
                route_kind="SON_SELF",
                note="SON_SELF_NE_MOTHER_MANAGED",
            )
        )
    else:
        routes.append(
            AuthorityRoute(
                target_authority="IDENTITY",
                route_kind="MOTHER_MANAGED",
                note="MANAGED_LINKED_USER_ID_NULL",
            )
        )

    return tuple(routes)


def assert_router_not_authority() -> None:
    assert ROUTER_IS_AUTHORITY is False
    assert SMART_RAG_OWNS_SEDI_TRUTH is False
    assert RANKING_CANNOT_INCREASE_AUTHORITY is True
