"""AI/rule-based knowledge content review before activation (Gate 3G)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.app import models
from backend.app.services.gate3.constants import (
    LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES,
    PROVIDER_CATEGORIES,
    SENSITIVE_REVIEW_REQUIRED_CATEGORIES,
)


CRISIS_TERMS = (
    "suicide", "self-harm", "kill myself", "خودکشی", "میخوام بمیرم", "خودآزاری",
)

PROMO_TERMS = (
    "best doctor", "best lab", "guaranteed cure", "بهترین دکتر", "قطعی درمان",
)


@dataclass
class AIReviewResult:
    ai_review_status: str
    source_quality_score: float
    parse_quality_score: float
    evidence_quality_score: float
    medical_risk_level: str
    psychological_risk_level: str
    advertising_risk_level: str
    requires_human_review: bool
    auto_approve_allowed: bool
    recommended_action: str
    review_findings: List[Dict[str, Any]]


class KnowledgeAIReviewService:
    PREVIEW_MAX = 50_000

    def review(
        self,
        source: models.KnowledgeSource,
        parsed_text: str,
        *,
        parser_type: str,
        title: str = "",
    ) -> AIReviewResult:
        findings: List[Dict[str, Any]] = []
        text = (parsed_text or "").strip()
        norm = text.lower()

        source_score = 0.5
        if source.trust_level in ("official", "clinical_guideline"):
            source_score = 0.95
        elif source.trust_level == "vetted_partner":
            source_score = 0.8
        if source.source_url:
            source_score += 0.05
        if not source.allowed_domain and source.source_fetch_enabled:
            findings.append({"code": "missing_allowed_domain", "severity": "medium"})
            source_score -= 0.1
        source_score = max(0.0, min(1.0, source_score))

        parse_score = 0.2
        if len(text) >= 200:
            parse_score = 0.7
        if len(text) >= 800:
            parse_score = 0.85
        if parser_type == "unsupported_pdf":
            parse_score = 0.1
            findings.append({"code": "unsupported_pdf", "severity": "high"})
        if parser_type in ("html", "text", "markdown"):
            parse_score = min(1.0, parse_score + 0.1)

        evidence_score = parse_score * source_score

        med_risk = "low"
        if source.category in SENSITIVE_REVIEW_REQUIRED_CATEGORIES:
            med_risk = "high"
        if any(w in norm for w in ("diagnosis", "dose", "prescribe", "تشخیص", "دوز", "نسخه")):
            med_risk = "high"
        if source.category in ("emergency_education",):
            med_risk = "critical"

        psych_risk = "low"
        if source.category in ("mental_wellbeing", "psychological_support", "emotional_support", "stress_management"):
            psych_risk = "medium"
        if any(t in norm for t in CRISIS_TERMS):
            psych_risk = "critical"
            findings.append({"code": "psychological_crisis_content", "severity": "critical"})

        ad_risk = "low"
        if any(p in norm for p in PROMO_TERMS):
            ad_risk = "high"
            findings.append({"code": "promotional_language", "severity": "high"})
        if source.category in PROVIDER_CATEGORIES and "ranking" in norm:
            ad_risk = "medium"

        requires_human = source.review_required or source.category in SENSITIVE_REVIEW_REQUIRED_CATEGORIES
        if med_risk in ("high", "critical"):
            requires_human = True
        if psych_risk in ("high", "critical"):
            requires_human = True
        if ad_risk == "high":
            requires_human = True

        auto_ok = (
            source.category in LOW_RISK_AUTO_APPROVE_ELIGIBLE_CATEGORIES
            and not requires_human
            and source.auto_approve_low_risk
            and med_risk == "low"
            and psych_risk == "low"
            and ad_risk == "low"
            and source_score >= 0.75
            and parse_score >= 0.75
            and parser_type != "unsupported_pdf"
        )

        if psych_risk == "critical":
            recommended = "reject"
            ai_status = "failed"
        elif auto_ok:
            recommended = "auto_approve"
            ai_status = "passed"
        elif requires_human:
            recommended = "pending_review"
            ai_status = "needs_review"
        else:
            recommended = "pending_review"
            ai_status = "needs_review"

        return AIReviewResult(
            ai_review_status=ai_status,
            source_quality_score=round(source_score, 3),
            parse_quality_score=round(parse_score, 3),
            evidence_quality_score=round(evidence_score, 3),
            medical_risk_level=med_risk,
            psychological_risk_level=psych_risk,
            advertising_risk_level=ad_risk,
            requires_human_review=requires_human,
            auto_approve_allowed=auto_ok,
            recommended_action=recommended,
            review_findings=findings,
        )

    def findings_json(self, result: AIReviewResult) -> str:
        return json.dumps(result.review_findings, ensure_ascii=False)
