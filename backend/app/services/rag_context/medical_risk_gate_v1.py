# backend.app.services.rag_context.medical_risk_gate_v1
"""
Stage 23 Step 5: Lightweight medical risk gate (keyword-based V1).
When True, RAG should not be used; recommend urgent care/clinician.
"""

import re
from typing import Set

# English high-risk phrases (lowercase; we match case-insensitive)
_HIGH_RISK_EN: Set[str] = {
    "chest pain",
    "stroke",
    "can't move",
    "can't feel",
    "numbness face",
    "numbness arm",
    "slurred speech",
    "vision loss",
    "sudden headache",
    "severe headache",
    "suicidal",
    "kill myself",
    "want to die",
    "severe bleeding",
    "unconscious",
    "not breathing",
    "difficulty breathing",
    "severe allergic",
    "anaphylaxis",
    "seizure",
    "convulsion",
    "severe pain",
    "heart attack",
    "myocardial",
    "paralysis",
    "sudden weakness",
    "confusion sudden",
    "severe dizziness",
    "poisoning",
    "overdose",
    "suicide attempt",
    "cut my wrist",
    "hanging myself",
}

# Persian (minimal)
_HIGH_RISK_FA: Set[str] = {
    "درد قفسه سینه",
    "سکته",
    "سکته مغزی",
    "خونریزی شدید",
    "خودکشی",
    "میخوام بمیرم",
    "دیگه نفس نمیکشم",
    "تشنج",
    "فلج",
    "بیهوش",
}

# Arabic (minimal)
_HIGH_RISK_AR: Set[str] = {
    "ألم في الصدر",
    "سكتة",
    "نزيف شديد",
    "انتحار",
    "أريد أن أموت",
    "لا أستطيع التنفس",
    "تشنج",
    "شلل",
}


def _normalize_for_match(text: str) -> str:
    """Lowercase, collapse whitespace."""
    if not text:
        return ""
    return " ".join(re.split(r"\s+", text.lower().strip()))


def is_high_risk_medical(query: str, language: str) -> bool:
    """
    V1 keyword-based gate: True if query suggests high-risk medical situation.
    Used to avoid RAG for urgent/serious topics; model should recommend clinician.
    """
    if not query or not isinstance(query, str):
        return False
    norm = _normalize_for_match(query)
    if not norm:
        return False
    lang = (language or "en").strip().lower()
    if lang.startswith("fa"):
        for phrase in _HIGH_RISK_FA:
            if phrase in query or phrase in norm:
                return True
    if lang.startswith("ar"):
        for phrase in _HIGH_RISK_AR:
            if phrase in query or phrase in norm:
                return True
    for phrase in _HIGH_RISK_EN:
        if phrase in norm:
            return True
    return False


def rag_allowed(query: str, language: str) -> bool:
    """
    Returns False for high-risk medical topics (RAG should not be used;
    recommend urgent care/clinician instead).
    """
    return not is_high_risk_medical(query, language or "en")
