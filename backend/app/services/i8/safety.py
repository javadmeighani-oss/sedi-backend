"""Deterministic I8 safety and applicability gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, RetrievalResult
from backend.app.services.i8.constants import (
    DISEASE_AWARE_HINTS,
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
        if restriction and restriction.casefold() in req_lower:
            return SafetyDecision(
                allowed=False,
                safety_state="BLOCKED",
                status="RESTRICTION_BLOCKED",
                message="Request conflicts with an active restriction.",
            )

    disease_aware = _contains_any(request, DISEASE_AWARE_HINTS) or bool(ctx.conditions)
    if disease_aware:
        if retrieval is None or retrieval.status != STATUS_OK or not retrieval.items:
            return SafetyDecision(
                allowed=False,
                safety_state="CLARIFY",
                status="UNSUPPORTED_CLINICAL_APPLICABILITY",
                clarification_required=True,
                message="Governed disease-aware applicability is insufficient; fail-closed.",
            )
        unsafe_items = [
            i
            for i in retrieval.items
            if str(getattr(i, "medical_safety_state", "")).upper() not in {"SAFE", "LOW_RISK"}
        ]
        if unsafe_items:
            return SafetyDecision(
                allowed=False,
                safety_state="CLARIFY",
                status="UNSUPPORTED_CLINICAL_APPLICABILITY",
                clarification_required=True,
                message="Retrieved knowledge is not eligible for disease-aware action.",
            )

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
