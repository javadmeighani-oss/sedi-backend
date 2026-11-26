"""R-120 am.2 (Javad 2026-11-26): AFTER the doctor introduction Sedi gives care suggestions built from what she understood of the user's own
explanation - not a fixed block - until the visit.

Guards (R-109 am.3, R-014, R-033): non-drug suggestions only (no medicine, dose, supplement, diagnosis, reassurance, link); 2-4 short
lines in the user's language (standard polite Persian, «تو»); no questions; the emergency warning is NEVER left to the model - it is the
fixed catalog line for the body area. The model (gpt-6-luna, approved 2026-11-26) sees the user's explanation and the kind of doctor only.
Any failure, no key, or ``SEDI_CARE_FOLLOWUP_MODEL_DISABLED`` = None, and the caller keeps the catalog care block (fail-open).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional, Sequence

from backend.app import sedi_copy
from backend.app.services.care_journey import followup_questions as fq

logger = logging.getLogger(__name__)

MAX_LINES = 4
MAX_CHARS = 200
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["suggestions"],
    "properties": {"suggestions": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_LINES}},
}
_FORBIDDEN = re.compile(
    r"https?://|www\.|\d+\s*(?:mg|ml|میلی|گرم|عدد\s*قرص)|"
    r"قرص|کپسول|دارو|آسپرین|استامینوفن|ایبوپروفن|مسکن|مکمل|آنتی\s*بیوتیک|تشخیص|احتمالا\s*(?:سکته|سرطان|بیماری)|نگران\s*نباش|"
    r"\b(?:pill|tablet|capsule|medicine|medication|aspirin|ibuprofen|paracetamol|painkiller|supplement|antibiotic|dose|diagnos|don.?t worry)\b|"
    r"دواء|حبوب|جرعة|مسكن|تشخيص|لا\s*تقلق",
    re.I,
)


def _instructions(lang: str, specialty: Optional[str]) -> str:
    language_name = {"fa": "Persian (standard polite spoken Persian, full verb forms, address the user as «تو», no slang)",
                     "ar": "Arabic (Modern Standard, warm and polite)", "en": "English (warm, plain)"}[lang]
    who = f" They are about to see a {specialty} specialist." if specialty else ""
    return (
        "You are Sedi, a caring health companion. Below is what the user told you about their situation." + who + " "
        f"Write 2 to {MAX_LINES} short, practical CARE suggestions in {language_name} for the time until the doctor's visit, built on what "
        "THEY said (their activity, sleep, stress, food, what makes it better or worse, what to note down for the doctor). "
        "Non-drug only: never a medicine, supplement, dose, diagnosis, reassurance or link. No questions. No emergency advice (it is added "
        f"separately). Each suggestion at most {MAX_CHARS} characters."
    )


def _clean(lines: Any) -> list:
    out: list = []
    for line in lines if isinstance(lines, list) else []:
        text = " ".join(str(line or "").split()).lstrip("-–•* ").strip()
        if not text or len(text) > MAX_CHARS or text.endswith(("?", "؟")) or _FORBIDDEN.search(text):
            continue
        if text not in out:
            out.append(text)
        if len(out) >= MAX_LINES:
            break
    return out


def _call_model(explanation: str, lang: str, specialty: Optional[str], client: Any = None) -> list:
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=fq.TIMEOUT_SECONDS)
    from backend.app.core.conversation.prompts import DEFAULT_OPENAI_CHAT_MODEL

    resp = client.responses.create(
        model=(os.getenv("OPENAI_CHAT_MODEL") or "").strip() or DEFAULT_OPENAI_CHAT_MODEL,
        instructions=_instructions(lang, specialty),
        input=explanation[:1500],
        text={"format": {"type": "json_schema", "name": "care_suggestions", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(getattr(resp, "output_text", "") or "{}")
    return data.get("suggestions") if isinstance(data, dict) else []


def personal_care_block(explanations: Sequence[str], language: Optional[str], area: str, specialty: Optional[str] = None,
                        *, client: Any = None) -> Optional[str]:
    """«Until you see the doctor, based on what you told me:» + 2-4 suggestions from the user's own words + the FIXED emergency line.
    None = nothing usable (no explanation, model off / failed / every line broke a guard): the caller keeps the catalog block."""
    told = " ".join(" ".join(str(x or "").split()) for x in explanations if str(x or "").strip())
    if len(told) < 6 or not fq.enabled():
        return None
    lang = fq._lang(language)
    try:
        lines = _clean(_call_model(told, lang, specialty, client))
    except Exception:  # noqa: BLE001
        logger.info("[R-120] personal care suggestions skipped")
        return None
    if len(lines) < 2:
        return None
    body = "\n".join("– " + line for line in lines)
    emergency = sedi_copy.t(f"journey.care.emergency.{'chest' if area == 'chest' else 'generic'}", lang)
    return sedi_copy.t("journey.care.personal.lead", lang) + "\n" + body + "\n\n" + emergency
