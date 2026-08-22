"""Deterministic I8 safety and applicability gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievalResult
from backend.app.services.i8.constants import (
    DISEASE_AWARE_HINTS,
    GOVERNED_DISEASE_APPLICABILITY_AVAILABLE,
    THERAPEUTIC_TOKENS,
    UNSAFE_DIAGNOSIS_TOKENS,
)
from backend.app.services.i8.context import I8TrustedContext


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    safety_state: str
    status: str
    clarification_required: bool = False
    message: str = ""


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = (text or "").casefold()
    return any(tok in lowered for tok in tokens)


def requires_disease_aware_applicability(*, request: str, ctx: I8TrustedContext) -> bool:
    return bool(ctx.conditions) or _contains_any(request, DISEASE_AWARE_HINTS)


def evaluate_disease_applicability(*, request: str, ctx: I8TrustedContext) -> Optional[SafetyDecision]:
    """Fail-closed unless explicit governed disease applicability exists (KNOW-06 hook)."""
    if not requires_disease_aware_applicability(request=request, ctx=ctx):
        return None
    if GOVERNED_DISEASE_APPLICABILITY_AVAILABLE:
        return None
    return SafetyDecision(
        allowed=False,
        safety_state="CLARIFY",
        status="UNSUPPORTED_CLINICAL_APPLICABILITY",
        clarification_required=True,
        message="Governed disease-aware applicability is unavailable; fail-closed.",
    )


def evaluate_safety(
    *,
    request: str,
    ctx: I8TrustedContext,
    retrieval: Optional[RetrievalResult] = None,
    domain: str = "cross_domain",
) -> SafetyDecision:
    if _contains_any(request, UNSAFE_DIAGNOSIS_TOKENS):
        return SafetyDecision(
            allowed=False,
            safety_state="BLOCKED",
            status="UNSAFE_REQUEST_BLOCKED",
            message="Sedi will not diagnose or replace a physician.",
        )
    if _contains_any(request, THERAPEUTIC_TOKENS):
        return SafetyDecision(
            allowed=False,
            safety_state="BLOCKED",
            status="THERAPEUTIC_FAIL_CLOSED",
            message="Medication change or therapeutic instructions are not supported.",
        )

    req_lower = request.casefold()
    for allergy in ctx.allergies:
        if allergy and allergy.casefold() in req_lower:
            return SafetyDecision(
                allowed=False,
                safety_state="BLOCKED",
                status="ALLERGY_HARD_CONSTRAINT",
                message="Request conflicts with a confirmed allergy constraint.",
            )

    if ctx.unverified_allergy_signals and any(
        sig and sig.casefold() in req_lower for sig in ctx.unverified_allergy_signals
    ):
        return SafetyDecision(
            allowed=False,
            safety_state="CLARIFY",
            status="UNVERIFIED_ALLERGY_SIGNAL",
            clarification_required=True,
            message="Allergy signal is unverified; clarification required.",
        )

    for restriction in ctx.restrictions:
        r = restriction.casefold()
        if r and (r in req_lower or any(tok in req_lower for tok in r.split() if len(tok) > 3)):
            return SafetyDecision(
                allowed=False,
                safety_state="BLOCKED",
                status="RESTRICTION_BLOCKED",
                message="Request conflicts with an active restriction.",
            )

    disease_block = evaluate_disease_applicability(request=request, ctx=ctx)
    if disease_block is not None:
        return disease_block

    if retrieval is not None and retrieval.status != STATUS_OK and domain != "wellbeing":
        return SafetyDecision(
            allowed=False,
            safety_state="CLARIFY",
            status="MISSING_ELIGIBLE_KNOWLEDGE",
            clarification_required=True,
            message="Approved governed knowledge is unavailable.",
        )

    return SafetyDecision(
        allowed=True,
        safety_state="SAFE",
        status="SAFE",
        message="Passed deterministic safety gate.",
    )


def evaluate_composed_safety(
    *,
    candidate_text: str,
    ctx: I8TrustedContext,
) -> SafetyDecision:
    """Post-composition deterministic safety over generated user-facing content."""
    text = (candidate_text or "").casefold()
    if not text.strip():
        return SafetyDecision(
            allowed=False,
            safety_state="BLOCKED",
            status="MISSING_GROUNDED_ACTION_CONTENT",
            message="No grounded candidate action content.",
        )

    if _contains_any(text, UNSAFE_DIAGNOSIS_TOKENS):
        return SafetyDecision(
            allowed=False,
            safety_state="BLOCKED",
            status="UNSAFE_REQUEST_BLOCKED",
            message="Generated content crosses diagnosis boundary.",
        )
    if _contains_any(text, THERAPEUTIC_TOKENS):
        return SafetyDecision(
            allowed=False,
            safety_state="BLOCKED",
            status="THERAPEUTIC_FAIL_CLOSED",
            message="Generated content includes therapeutic instructions.",
        )

    for allergy in ctx.allergies:
        if allergy and allergy.casefold() in text:
            return SafetyDecision(
                allowed=False,
                safety_state="BLOCKED",
                status="ALLERGY_HARD_CONSTRAINT",
                message="Generated content conflicts with a confirmed allergy.",
            )

    if ctx.unverified_allergy_signals and any(
        sig and sig.casefold() in text for sig in ctx.unverified_allergy_signals
    ):
        return SafetyDecision(
            allowed=False,
            safety_state="CLARIFY",
            status="UNVERIFIED_ALLERGY_SIGNAL",
            clarification_required=True,
            message="Generated content touches an unverified allergy signal.",
        )

    for restriction in ctx.restrictions:
        r = restriction.casefold()
        if r and (r in text or any(tok in text for tok in r.split() if len(tok) > 3)):
            return SafetyDecision(
                allowed=False,
                safety_state="BLOCKED",
                status="RESTRICTION_BLOCKED",
                message="Generated content conflicts with an active restriction.",
            )

    disease_block = evaluate_disease_applicability(request=candidate_text, ctx=ctx)
    if disease_block is not None:
        return disease_block

    return SafetyDecision(
        allowed=True,
        safety_state="SAFE",
        status="SAFE",
        message="Passed post-composition safety gate.",
    )
