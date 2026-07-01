"""Fail-safe review policy normalization for knowledge sources (Gate 3G)."""

from __future__ import annotations

from backend.app.services.gate3.constants import (
    LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES,
    SENSITIVE_REVIEW_REQUIRED_CATEGORIES,
)


def normalize_source_review_policy(
    category: str,
    *,
    review_required: bool = True,
    auto_approve_low_risk: bool = False,
) -> tuple[bool, bool]:
    """
    Normalize admin-provided review flags for a source category.
    Sensitive categories always require review and never allow auto-approve.
    Low-risk eligible categories preserve explicit admin configuration.
    All other categories fail safe to review_required=True, auto_approve_low_risk=False.
    """
    cat = (category or "other").strip()
    if cat in SENSITIVE_REVIEW_REQUIRED_CATEGORIES:
        return True, False
    if cat in LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES:
        return review_required, auto_approve_low_risk
    return True, False
