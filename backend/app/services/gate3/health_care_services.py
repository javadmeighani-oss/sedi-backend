"""Gate 3 health Q&A and structured symptom reports."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate3 import HealthQuestionIn, SymptomReportIn, SymptomReportPatchIn
from backend.app.services.gate3.care_intelligence import Gate3NotFoundError
from backend.app.services.gate3.emergency_templates import get_template
from backend.app.services.gate3.knowledge_retrieval_service import search_knowledge
from backend.app.services.gate3.safety_core import RiskClassifier, SafetyPolicy, persist_risk_assessment
from backend.app.services.gate3.safety_validator import validate_response_text


def list_symptom_reports(db: Session, user_id: int) -> List[dict]:
    rows = (
        db.query(models.HealthSymptomReport)
        .filter(models.HealthSymptomReport.user_id == user_id)
        .order_by(models.HealthSymptomReport.reported_at.desc())
        .all()
    )
    return [_symptom_dict(r) for r in rows]


def _symptom_dict(row: models.HealthSymptomReport) -> dict:
    return {
        "id": row.id,
        "symptom_label": row.symptom_label,
        "symptom_code": row.symptom_code,
        "severity": row.severity,
        "body_area": row.body_area,
        "duration": row.duration,
        "notes": row.notes,
        "status": row.status,
        "resolved_at": row.resolved_at.isoformat() + "Z" if row.resolved_at else None,
        "reported_at": row.reported_at.isoformat() + "Z",
        "created_at": row.created_at.isoformat() + "Z",
    }


def create_symptom_report(db: Session, user_id: int, body: SymptomReportIn, source: str = "api") -> dict:
    risk = RiskClassifier().classify(body.symptom_label + " " + (body.notes or ""), "fa")
    if body.severity == "severe":
        risk = RiskClassifier().classify("severe " + body.symptom_label, "fa")
    now = datetime.utcnow()
    row = models.HealthSymptomReport(
        user_id=user_id,
        reported_at=body.reported_at or now,
        symptom_label=body.symptom_label.strip(),
        symptom_code=body.symptom_code,
        severity=body.severity,
        body_area=body.body_area,
        duration=body.duration,
        notes=body.notes,
        source=source,
        status="active",
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    out = _symptom_dict(row)
    out["risk_level"] = risk.risk_level
    if risk.risk_level in ("emergency", "high"):
        out["safety_message"] = SafetyPolicy().response_for_level(risk.risk_level, "fa")
    return out


def update_symptom_report(db: Session, user_id: int, report_id: int, body: SymptomReportPatchIn) -> dict:
    if body.status is None and body.notes is None:
        raise ValueError("At least one of status or notes is required")
    row = (
        db.query(models.HealthSymptomReport)
        .filter(
            models.HealthSymptomReport.id == report_id,
            models.HealthSymptomReport.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise Gate3NotFoundError()
    now = datetime.utcnow()
    if body.status is not None:
        row.status = body.status
        if body.status == "resolved":
            row.resolved_at = now
        elif body.status == "active":
            row.resolved_at = None
    if body.notes is not None:
        row.notes = body.notes
    db.commit()
    db.refresh(row)
    return _symptom_dict(row)


def list_health_questions(db: Session, user_id: int) -> List[dict]:
    rows = (
        db.query(models.HealthQuestion)
        .filter(models.HealthQuestion.user_id == user_id)
        .order_by(models.HealthQuestion.created_at.desc())
        .limit(50)
        .all()
    )
    return [_question_dict(r) for r in rows]


def _question_dict(row: models.HealthQuestion) -> dict:
    return {
        "id": row.id,
        "question_text": row.question_text,
        "answer_text": row.answer_text,
        "safety_level": row.safety_level,
        "risk_level": row.risk_level,
        "citations": json.loads(row.citations_json) if row.citations_json else [],
        "created_at": row.created_at.isoformat() + "Z",
    }


def answer_health_question(db: Session, user_id: int, body: HealthQuestionIn, source: str = "api") -> dict:
    lang = body.language or "fa"
    question = body.question.strip()
    risk = RiskClassifier().classify(question, lang)
    persist_risk_assessment(db, user_id, risk, question, source=source)
    policy = SafetyPolicy().evaluate(risk.risk_level)

    if policy.get("template_key"):
        answer = SafetyPolicy().response_for_level(risk.risk_level, lang)
        citations = []
    else:
        kb = search_knowledge(db, question, locale=lang[:2] if lang else None, limit=5, risk_level=risk.risk_level)
        chunks = kb.get("chunks") or []
        if chunks:
            parts = []
            citations = []
            for ch in chunks[:3]:
                cit = ch.get("citation") or {}
                parts.append(ch.get("content", ""))
                citations.append(cit)
            prefix = "بر اساس منابع معتبر ثبت‌شده: " if lang.startswith("fa") else "Based on registered curated sources: "
            answer = prefix + " ".join(parts)[:1200]
            answer += "\n\n" + (
                "این اطلاعات آموزشی است و جایگزین مشورت با پزشک نیست."
                if lang.startswith("fa")
                else "This is educational information and not a substitute for medical advice."
            )
        else:
            answer = get_template("no_source", lang)
            citations = []

    safe, violation = validate_response_text(answer or "")
    if not safe:
        answer = get_template("safe_fallback", lang)

    row = models.HealthQuestion(
        user_id=user_id,
        question_text=question,
        answer_text=answer,
        safety_level=risk.risk_level if risk.risk_level in ("low", "medium") else "high",
        risk_level=risk.risk_level,
        citations_json=json.dumps(citations, ensure_ascii=False) if citations else None,
        source=source,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _question_dict(row)


def get_health_education(db: Session, topic: str, language: str = "fa", user_id: Optional[int] = None) -> Dict[str, Any]:
    risk = RiskClassifier().classify(topic, language)
    if risk.risk_level == "emergency":
        return {"topic": topic, "content": get_template("emergency", language), "citations": []}
    kb = search_knowledge(db, topic, limit=5, risk_level=risk.risk_level)
    chunks = kb.get("chunks") or []
    if not chunks:
        return {"topic": topic, "content": get_template("no_source", language), "citations": []}
    content_parts = [c.get("content", "") for c in chunks[:3]]
    citations = [c.get("citation") for c in chunks[:3]]
    disclaimer = "Based on registered curated sources. Not medical advice."
    if language.startswith("fa"):
        disclaimer = "بر اساس منابع معتبر ثبت‌شده. جایگزین مشورت پزشکی نیست."
    return {
        "topic": topic,
        "content": " ".join(content_parts)[:1500] + "\n\n" + disclaimer,
        "citations": citations,
    }
