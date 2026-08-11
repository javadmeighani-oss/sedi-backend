"""Guideline authority promotion — illegal jumps must fail closed.

DISCOVERED → VERIFIED_ARTIFACT_POINTER → VERIFIED_GUIDELINE → PARSED_RECOMMENDATION
only when each transition has supporting evidence.
"""

from __future__ import annotations

from typing import Mapping, Optional

# Lightweight stage vocabulary (string-driven; no schema migration).
STAGE_DISCOVERED = "DISCOVERED"
STAGE_VERIFIED_ARTIFACT_POINTER = "VERIFIED_ARTIFACT_POINTER"
STAGE_VERIFIED_GUIDELINE = "VERIFIED_GUIDELINE"
STAGE_PARSED_RECOMMENDATION = "PARSED_RECOMMENDATION"

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STAGE_DISCOVERED: frozenset({STAGE_VERIFIED_ARTIFACT_POINTER}),
    STAGE_VERIFIED_ARTIFACT_POINTER: frozenset({STAGE_VERIFIED_GUIDELINE}),
    STAGE_VERIFIED_GUIDELINE: frozenset({STAGE_PARSED_RECOMMENDATION}),
    STAGE_PARSED_RECOMMENDATION: frozenset(),
}

_ILLEGAL_JUMPS = frozenset(
    {
        (STAGE_DISCOVERED, STAGE_PARSED_RECOMMENDATION),
        (STAGE_DISCOVERED, STAGE_VERIFIED_GUIDELINE),
        (STAGE_VERIFIED_ARTIFACT_POINTER, STAGE_PARSED_RECOMMENDATION),
    }
)


class AuthorityPromotionError(ValueError):
    pass


def validate_promotion(*, from_stage: str, to_stage: str) -> None:
    if (from_stage, to_stage) in _ILLEGAL_JUMPS:
        raise AuthorityPromotionError(f"ILLEGAL_AUTHORITY_JUMP:{from_stage}->{to_stage}")
    allowed = _ALLOWED_TRANSITIONS.get(from_stage, frozenset())
    if to_stage not in allowed:
        raise AuthorityPromotionError(f"DISALLOWED_AUTHORITY_TRANSITION:{from_stage}->{to_stage}")


def assert_news_not_guideline_authority(
    *,
    source_role: str,
    resource_type: str,
    clinical_guideline: bool,
    clinical_recommendation: bool,
    runtime_medical_authority: bool,
    recommendation_text: Optional[str] = None,
) -> None:
    """NF14 invariant: news/discovery signals are never guideline authority."""
    if source_role in {"NEWS_OR_DISCOVERY_SIGNAL", "WHO_NEWS"}:
        if clinical_guideline or clinical_recommendation or runtime_medical_authority:
            raise AuthorityPromotionError("WHO_NEWS_ITEM_CLASSIFIED_AS_GUIDELINE")
        if recommendation_text:
            raise AuthorityPromotionError("WHO_NEWS_ITEM_RECOMMENDATION_TEXT_PROMOTION")
    if resource_type in {"NEWS_ITEM", "DISCOVERY_ITEM", "WHO_NEWS"}:
        if clinical_guideline or clinical_recommendation:
            raise AuthorityPromotionError("NEWS_ITEM_AS_GUIDELINE_OR_RECOMMENDATION")
        if recommendation_text:
            raise AuthorityPromotionError("WHO_NEWS_ITEM_RECOMMENDATION_TEXT_PROMOTION")


def assert_catalogue_not_recommendation(
    *,
    who_artifact_kind: str,
    clinical_recommendation: bool,
    recommendation_text: Optional[str] = None,
) -> None:
    """Catalogue/publication pointers are not parsed recommendations."""
    if who_artifact_kind in {
        "WHO_GUIDELINE_CATALOGUE_ENTRY",
        "WHO_PUBLICATION",
        "WHO_GUIDELINE_CATALOGUE",
    }:
        if clinical_recommendation or recommendation_text:
            raise AuthorityPromotionError("GUIDELINE_CATALOGUE_RECORD_IS_NOT_RECOMMENDATION")


def payload_authority_flags(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "clinical_guideline": bool(payload.get("clinical_guideline")),
        "clinical_recommendation": bool(payload.get("clinical_recommendation")),
        "runtime_medical_authority": bool(payload.get("runtime_medical_authority")),
        "who_artifact_kind": payload.get("who_artifact_kind"),
        "authority_stage": payload.get("authority_stage"),
        "recommendation_extraction": payload.get("recommendation_extraction", "NOT_EXERCISED"),
    }
