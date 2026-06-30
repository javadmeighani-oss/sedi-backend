"""Gate 3 risk classification and safety policy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.rag_context.medical_risk_gate_v1 import is_high_risk_medical
from backend.app.services.gate3.emergency_templates import get_template


@dataclass
class RiskResult:
    risk_level: str
    reasons: List[str]


class RiskClassifier:
    def classify(self, message: str, language: str = "fa", context: Optional[Dict[str, Any]] = None) -> RiskResult:
        reasons: List[str] = []
        text = (message or "").strip()
        lang = language or "fa"

        if is_high_risk_medical(text, lang):
            return RiskResult("emergency", ["high_risk_medical_keywords"])

        norm = text.lower()
        if re.search(r"\b(dose|dosage|mg|میلی\s*گرم|دوز)\b", norm, re.I) or "دوز" in text:
            reasons.append("medication_dose_topic")
            return RiskResult("medium", reasons)

        if re.search(r"\b(stop|start)\s+(taking\s+)?(my\s+)?(med|medication|medicine|pill)\b", norm, re.I):
            reasons.append("stop_start_medication")
            return RiskResult("medium", reasons)

        if any(p in norm for p in ("pregnant", "باردار", "کودک", "سالمند", "elderly", "child")):
            reasons.append("high_risk_segment")
            return RiskResult("high", reasons)

        severe_symptoms = ("severe", "شدید", "خونریزی", "تنگی نفس")
        if any(s in text for s in severe_symptoms):
            reasons.append("severe_symptom_language")
            return RiskResult("high", reasons)

        medical_words = ("symptom", "pain", "علائم", "درد", "دارو", "medication", "condition")
        if any(w in norm or w in text for w in medical_words):
            return RiskResult("medium", ["medical_topic"])

        return RiskResult("low", reasons or ["general"])


class SafetyPolicy:
    FORBIDDEN_ACTIONS = frozenset({
        "definitive_diagnosis",
        "medication_dose_change",
        "stop_medication",
        "start_medication",
        "emergency_treatment_instruction",
        "unsupported_provider_ranking",
        "single_provider_endorsement",
    })

    def evaluate(self, risk_level: str, intent: str = "general") -> Dict[str, Any]:
        rl = risk_level or "low"
        rag_allowed = rl in ("low", "medium")
        kb_allowed = rl in ("low", "medium")
        llm_allowed = rl in ("low", "medium")
        if rl == "high":
            llm_allowed = False
            kb_allowed = False
        if rl == "emergency":
            rag_allowed = False
            kb_allowed = False
            llm_allowed = False
        template_key = None
        if rl == "emergency":
            template_key = "emergency"
        elif rl == "high":
            template_key = "high_risk"
        return {
            "risk_level": rl,
            "rag_allowed": rag_allowed,
            "kb_allowed": kb_allowed,
            "llm_allowed": llm_allowed,
            "template_key": template_key,
            "forbidden_actions": list(self.FORBIDDEN_ACTIONS),
        }

    def response_for_level(self, risk_level: str, language: str) -> Optional[str]:
        policy = self.evaluate(risk_level)
        key = policy.get("template_key")
        if key:
            return get_template(key, language)
        return None


def persist_risk_assessment(
    db: Session,
    user_id: int,
    result: RiskResult,
    message: str,
    source: str = "api",
) -> Dict[str, Any]:
    h = hashlib.sha256((message or "").encode("utf-8")).hexdigest()[:64]
    row = models.CareRiskAssessment(
        user_id=user_id,
        risk_level=result.risk_level,
        reasons_json=json.dumps(result.reasons, ensure_ascii=False),
        message_hash=h,
        source=source,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "risk_level": row.risk_level,
        "reasons": result.reasons,
        "created_at": row.created_at.isoformat() + "Z",
    }
