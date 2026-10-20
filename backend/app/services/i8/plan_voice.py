# backend.app.services.i8.plan_voice
"""Sedi's human voice for the rule-built weekly plan (R-011, 2026-10-20).

The rules (plan_composer) still choose every item and every allergen/safety filter. An LLM may ONLY re-voice the short
instruction of each already-chosen item in Sedi's warm persona. Anything that is not clearly safe falls back, item by
item, to the deterministic catalog text. Default OFF (flag SEDI_PLAN_VOICE_LLM) until Javad enables it in production.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENV_FLAG = "SEDI_PLAN_VOICE_LLM"
_MIN_LEN, _MAX_LEN = 12, 320
_LANG_NAME = {"fa": "Persian (Farsi), colloquial and warm", "ar": "Arabic", "en": "English"}
# No quantities, calories, doses, medication, links or markdown may appear in a voiced instruction.
_FORBIDDEN = re.compile(
    r"(\d\s*(kcal|cal|calories?|mg|g|gr|grams?|ml|گرمی|گرم|میلی‌?گرم|سی‌?سی))|(کالری|دوز|دارو|قرص|kcal|calorie|dose|dosage|medicat|جرعة|دواء|سعرات)|(https?://)|[*#`_]",
    re.IGNORECASE,
)


def plan_voice_enabled() -> bool:
    return (os.getenv(ENV_FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


def _norm(text: Any) -> str:
    return " ".join(str(text or "").lower().split())


def _call_llm(system: str, user: str) -> str:
    """Single LLM call through the same primary chat path the rest of Sedi uses."""
    from backend.app.core.conversation.prompts import create_primary_chat_response

    completion = create_primary_chat_response(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return (getattr(completion, "output_text", "") or "").strip()


def _parse_json_object(raw: str) -> dict:
    try:
        start, end = raw.index("{"), raw.rindex("}")
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def validate_voiced(base_by_id: dict, voiced: dict, constraints: Any, catalog: dict) -> dict:
    """Keep only voiced texts that are safe; every other item keeps its deterministic catalog text."""
    banned_terms: set = set()
    aliases = (catalog or {}).get("allergen_aliases", {})
    for allergen in getattr(constraints, "allergens", set()) or set():
        banned_terms.update(_norm(a) for a in aliases.get(allergen, []))
    banned_terms.update(getattr(constraints, "avoid_kw", set()) or set())
    banned_terms.discard("")
    ok: dict = {}
    for item_id, text in (voiced or {}).items():
        if item_id not in base_by_id or not isinstance(text, str):
            continue
        t = " ".join(text.split())
        if not (_MIN_LEN <= len(t) <= _MAX_LEN) or _FORBIDDEN.search(t):
            continue
        low, base_low = _norm(t), _norm(base_by_id[item_id])
        # A term the user must avoid may not appear unless the deterministic text already (safely) contained it.
        if any(term in low and term not in base_low for term in banned_terms):
            continue
        ok[item_id] = t
    return ok


def voice_week(week: list, lang: str, constraints: Any) -> dict:
    """{item_id: voiced instruction} for the distinct items of the week; {} on any problem (caller falls back)."""
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
    from backend.app.services.i8 import plan_composer as pc

    cat = pc.catalog()
    base_by_id: dict = {}
    items: list = []
    for day in week:
        for entry in day:
            item = entry["item"]
            item_id = item["id"]
            if item_id in base_by_id or item_id not in cat["texts"] or item_id == "rest":
                continue
            title, how = cat["texts"][item_id][lang]
            base_by_id[item_id] = how
            items.append({"id": item_id, "slot": entry["slot"], "title": title, "instruction": how})
    if not items:
        return {}
    context = {
        "likes": sorted(getattr(constraints, "like_kw", set()) or set()),
        "needs_soft_texture": bool(getattr(constraints, "soft", False)),
        "short_on_time": bool(getattr(constraints, "quick", False)),
        "light_only": bool(getattr(constraints, "light_only", False)),
    }
    system = (
        PersonaPolicyV1.system_prompt(lang)
        + "\n\nTask: rewrite the short instruction of each plan item below in Sedi's own warm, personal voice. "
        "Rules: 1-2 short sentences, plain text, no markdown, no emoji; keep exactly the same dish/exercise and the same "
        "ingredients — do NOT add or remove ingredients, and give no quantities, calories, medical claims or medication "
        f"advice. Language: {_LANG_NAME.get(lang, 'English')}. Output ONLY a JSON object mapping each id to its rewritten text."
    )
    user = json.dumps({"items": items, "about_the_user": context}, ensure_ascii=False)
    try:
        raw = _call_llm(system, user)
    except Exception as exc:  # never let a model hiccup block a plan
        logger.warning("[PLAN_VOICE] llm call failed (%s); using catalog text", type(exc).__name__)
        return {}
    voiced = validate_voiced(base_by_id, _parse_json_object(raw), constraints, cat)
    logger.info("[PLAN_VOICE] voiced=%s of %s items", len(voiced), len(base_by_id))
    return voiced
