"""R-120 (Javad 2026-11-26): the health interview asks the REASON openly; the user explains in his own words; Sedi's NEXT questions about his
physical or mental state come FROM that explanation - never a fixed symptom checklist.

This module turns the user's explanation into one to three short follow-up questions with the chat model (gpt-6-luna, Javad's approval
2026-11-26), inside fixed guards:
  * questions only: no diagnosis, no medicine / dose, no reassurance, no advice, no links, no numbers with units;
  * each question short, in the user's language, ending with a question mark; at most three; nothing repeated from the explanation;
  * standard polite Persian (R-057), addressed with «تو»;
  * emergencies never reach here (the triage red flag owns that turn before any interview);
  * any failure (no key, timeout, malformed answer, a question that breaks a guard) = the deterministic catalog question (fail-open).
The model sees the explanation and the kind of doctor only - no name, no stored memory, no other user data.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from backend.app import sedi_copy

logger = logging.getLogger(__name__)

DISABLED_ENV = "SEDI_CARE_FOLLOWUP_MODEL_DISABLED"  # «true» = the deterministic catalog question only
MAX_QUESTIONS = 3
MAX_CHARS = 160
TIMEOUT_SECONDS = 20.0

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions"],
    "properties": {"questions": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_QUESTIONS}},
}
# what a follow-up QUESTION must never carry (it is a question, not advice): medicines/doses, diagnoses, links, reassurance
_FORBIDDEN = re.compile(
    r"https?://|www\.|\b\d+\s*(?:mg|ml|میلی|گرم|قرص)\b|"
    r"مصرف\s*کن|بخور|نخور|دوز|تشخیص\s*(?:می|داده)|احتمالا\s*(?:سکته|سرطان)|نگران\s*نباش|"
    r"\b(?:take|stop taking|dose|diagnos|don.?t worry)\b|تناول|جرعة|لا\s*تقلق",
    re.I,
)
_QMARK = ("؟", "?")


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"} and bool((os.getenv("OPENAI_API_KEY") or "").strip())


def _lang(language: Optional[str]) -> str:
    raw = (language or "fa").lower()[:2]
    return raw if raw in ("fa", "ar", "en") else "en"


def _instructions(lang: str, specialty: Optional[str]) -> str:
    language_name = {"fa": "Persian (standard polite spoken Persian, full verb forms, address the user as «تو», no slang)",
                     "ar": "Arabic (Modern Standard, warm and polite)", "en": "English (warm, plain)"}[lang]
    who = f" The user is about to see a {specialty} specialist." if specialty else ""
    return (
        "You are Sedi, a caring health companion. The user has just explained, in their own words, why they want to see a doctor." + who + " "
        f"Write 1 to {MAX_QUESTIONS} short follow-up QUESTIONS in {language_name} that build on what the user actually said, to understand "
        "their physical and emotional situation better (for example what makes it better or worse, how it affects sleep, work or mood, "
        "what they have already tried, what worries them most). Ask only what the explanation leaves open; never repeat what they already said. "
        "Questions only: no diagnosis, no medicine or dose, no advice, no reassurance, no links, no numbers with units. "
        f"Each question at most {MAX_CHARS} characters and ending with a question mark."
    )


def _clean(questions: Any, explanation: str) -> list:
    out: list = []
    told = re.sub(r"\s+", " ", explanation or "").strip()
    for q in questions if isinstance(questions, list) else []:
        text = " ".join(str(q or "").split())
        if not text or len(text) > MAX_CHARS or not text.endswith(_QMARK) or _FORBIDDEN.search(text):
            continue
        if told and len(text) > 12 and text.rstrip("؟?") in told:
            continue  # an echo of the user's own words is not a question
        if text not in out:
            out.append(text)
        if len(out) >= MAX_QUESTIONS:
            break
    return out


def _call_model(explanation: str, lang: str, specialty: Optional[str], client: Any = None) -> list:
    if client is None:
        from openai import OpenAI

        client = OpenAI(max_retries=0, timeout=TIMEOUT_SECONDS)
    from backend.app.core.conversation.prompts import DEFAULT_OPENAI_CHAT_MODEL

    resp = client.responses.create(
        model=(os.getenv("OPENAI_CHAT_MODEL") or "").strip() or DEFAULT_OPENAI_CHAT_MODEL,
        instructions=_instructions(lang, specialty),
        input=explanation[:1200],  # the explanation ONLY (no name, no memory)
        text={"format": {"type": "json_schema", "name": "followup_questions", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(getattr(resp, "output_text", "") or "{}")
    return data.get("questions") if isinstance(data, dict) else []


def followup_message(explanation: str, language: Optional[str], specialty: Optional[str] = None, *, client: Any = None) -> str:
    """Sedi's reply to the user's explanation: one thanks line + the interview marker + 1-3 questions built from the explanation.
    The deterministic catalog question replaces the model whenever it is off, fails or breaks a guard."""
    lang = _lang(language)
    questions: list = []
    if enabled():
        try:
            questions = _clean(_call_model(explanation or "", lang, specialty, client), explanation or "")
        except Exception:  # noqa: BLE001 - the interview never breaks: the catalog question answers
            logger.info("[R-120] follow-up questions from the model skipped")
            questions = []
    body = " ".join(questions) if questions else sedi_copy.t("journey.followup.fallback", lang)
    return sedi_copy.t("journey.followup.lead", lang) + "\n\n" + sedi_copy.t("journey.followup.marker", lang) + " " + body
