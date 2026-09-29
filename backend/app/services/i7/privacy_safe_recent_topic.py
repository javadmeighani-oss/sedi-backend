"""I7 read-only privacy-safe recent-topic projection for lock-screen / push copy.

Coarse safe labels only. No schema. No durable write. No raw chat/memory dump.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.services.i6.consent_service import PERM_READ, has_permission
from backend.app.services.i7.derived_continuity import get_bounded_continuity_topic

# Coarse lock-screen-safe labels (never clinical / medication / diagnosis).
SAFE_TOPIC_LABELS = frozenset(
    {
        "activity_plan",
        "lifestyle",
        "general",
        "breathing",
        "hydration",
        "sleep_routine",
        "movement",
    }
)

_SENSITIVE_MARKERS = re.compile(
    r"("
    r"medication|medicine|drug|dose|pill|prescription|"
    r"lab|blood|symptom|diagnos|cancer|pain|surgery|"
    r"pregnant|depression|anxiety|suicid|hiv|std|"
    r"دارو|دوز|آزمایش|تشخیص|علائم|بیماری|"
    r"دواء|تشخيص|أعراض"
    r")",
    re.IGNORECASE,
)

_SAFE_KEYWORD_MAP = (
    (re.compile(r"activit|exercise|walk|run|حرکت|فعالیت|رياض|نشاط", re.I), "activity_plan"),
    (re.compile(r"lifestyle|routine|habit|سبک|روال|نمط", re.I), "lifestyle"),
    (re.compile(r"breath|نفس|تنفس", re.I), "breathing"),
    (re.compile(r"hydrat|water|آب|ماء", re.I), "hydration"),
    (re.compile(r"sleep|خواب|نوم", re.I), "sleep_routine"),
    (re.compile(r"move|step|قدم|مشي", re.I), "movement"),
)


def _classify_coarse_label(raw: str) -> Optional[str]:
    text = " ".join((raw or "").split()).strip()
    if not text:
        return None
    if _SENSITIVE_MARKERS.search(text):
        return None  # HEALTH_SENSITIVE / uncertain → no lock-screen topic
    for pattern, label in _SAFE_KEYWORD_MAP:
        if pattern.search(text):
            return label
    # Uncertain free text → generic only (no raw topic on lock screen)
    return None


def get_privacy_safe_recent_topic_label(db: Session, user_id: int) -> Optional[str]:
    """
    READ-ONLY: map governed I7 continuity topic to a coarse safe label, or None.

    PRIVATE/HEALTH_SENSITIVE/uncertain → None (caller must use generic continuation).
    Never returns raw prior chat text.
    """
    if not has_permission(db, user_id, PERM_READ):
        return None
    topic = get_bounded_continuity_topic(db, user_id)
    if not topic:
        return None
    label = _classify_coarse_label(topic)
    if label is None:
        return None
    return label if label in SAFE_TOPIC_LABELS else None


# Localized display phrases for safe labels (lock-screen friendly).
TOPIC_DISPLAY = {
    "activity_plan": {
        "en": "your activity plan",
        "fa": "برنامه فعالیتت",
        "ar": "خطة نشاطك",
    },
    "lifestyle": {
        "en": "your lifestyle routine",
        "fa": "روال سبک زندگی‌ات",
        "ar": "روتين نمط حياتك",
    },
    "breathing": {
        "en": "breathing practice",
        "fa": "تمرین تنفس",
        "ar": "تمرين التنفس",
    },
    "hydration": {
        "en": "hydration",
        "fa": "نوشیدن آب",
        "ar": "الترطيب",
    },
    "sleep_routine": {
        "en": "sleep routine",
        "fa": "روال خواب",
        "ar": "روتين النوم",
    },
    "movement": {
        "en": "movement",
        "fa": "تحرک",
        "ar": "الحركة",
    },
    "general": {
        "en": "our last chat",
        "fa": "آخرین گفتگویمان",
        "ar": "آخر محادثة لنا",
    },
}


def display_phrase_for_topic_label(label: Optional[str], language: str = "en") -> Optional[str]:
    if not label or label not in TOPIC_DISPLAY:
        return None
    lang = (language or "en").strip().lower().split("-")[0]
    block = TOPIC_DISPLAY[label]
    return block.get(lang) or block["en"]
