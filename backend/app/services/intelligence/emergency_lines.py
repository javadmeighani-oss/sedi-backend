"""F1 + F3 (D-402): the country layer for I4 terminal safety replies, and the anonymous crisis counter.

The I4 templates are country-neutral on purpose (section15 guard, R-098): they say «local emergency services». For a region whose
numbers are verified, ONE catalog sentence with the real numbers is appended to the terminal reply. Today only Iran is listed
(115 emergency, 123 social emergency - free, 24 h). Unknown region = the neutral template alone (never a guessed number).

Region: the user's phone prefix (+98), else the profile timezone Asia/Tehran, else Persian language (pilot = Iran first, R-098).

F3: every self-harm terminal reply writes ONE structured log line (``I4_SELF_HARM_EVENT level=.. lang=..``) - no user id, no text -
which the daily monitoring report counts. Fail-open everywhere: this module must never break a safety reply.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Verified numbers only (D-398). A new region is added here with its source, never guessed.
REGION_LINES = {
    "IR": {"emergency": "115", "social": "123", "counselling": "1480"},
}


def region_for(db: Any, user_id: Optional[int], language: str) -> Optional[str]:
    """Where the user probably is, for emergency numbers. Explicit evidence wins over the language fallback (Codex P1):
    1. the profile timezone (where the device is NOW): Asia/Tehran -> IR, any other timezone -> unknown region;
    2. else the phone prefix: +98 / 0098 / 09xx -> IR, any other international prefix -> unknown region;
    3. only with NO evidence at all: Persian language -> IR (pilot = Iran first, R-098).
    ``None`` = no verified numbers: the country-neutral wording is used."""
    try:
        if db is not None and user_id:
            from backend.app import models

            profile = db.query(models.UserProfileCore).filter(models.UserProfileCore.user_id == user_id).first()
            tz = str(getattr(profile, "timezone", "") or "").strip()
            if tz:
                return "IR" if tz == "Asia/Tehran" else None
            user = db.query(models.User).filter(models.User.id == user_id).first()
            phone = str(getattr(user, "phone", "") or "").replace(" ", "")
            if phone.startswith(("+98", "0098", "09")):
                return "IR"
            if phone.startswith(("+", "00")):
                return None
    except Exception:  # noqa: BLE001
        logger.debug("emergency_lines.region_for failed", exc_info=True)
    return "IR" if language == "fa" else None


def local_lines_sentence(db: Any, user_id: Optional[int], language: str, *, self_harm: bool) -> str:
    """The help-line sentence for this user's region, in their language ('' when the region is not verified)."""
    try:
        region = region_for(db, user_id, language)
        lines = REGION_LINES.get(region or "")
        if not lines:
            return ""
        from backend.app import sedi_copy
        from backend.app.typography import normalize

        lang = language if language in ("fa", "ar", "en") else "en"
        key = "safety.lines.self_harm" if self_harm else "safety.lines.medical"
        return normalize(sedi_copy.t(key, lang, **lines), lang)
    except Exception:  # noqa: BLE001
        return ""


def finalize_terminal_message(message: str, assessment: Any, db: Any, user_id: Optional[int]) -> str:
    """Add the regional line to an I4 terminal reply and count self-harm events. Returns ``message`` unchanged on any failure."""
    try:
        from backend.app.services.intelligence.contracts import RiskDomain

        language = str(getattr(assessment, "language", "") or "en")
        self_harm = getattr(assessment, "domain", None) is RiskDomain.SELF_HARM_CRISIS
        if self_harm:
            logger.warning("I4_SELF_HARM_EVENT level=%s lang=%s", getattr(getattr(assessment, "level", None), "name", "?"), language)
        from backend.app.services.intelligence.contracts import RiskLevel

        if not self_harm and getattr(assessment, "level", None) is not RiskLevel.EMERGENCY:
            return message  # a HIGH / fail-closed medical reply keeps its neutral wording
        extra = local_lines_sentence(db, user_id, language, self_harm=self_harm)
        if extra and extra not in message:
            return f"{message.rstrip()}\n\n{extra}"
    except Exception:  # noqa: BLE001
        logger.debug("emergency_lines.finalize failed", exc_info=True)
    return message
