"""I8 weekly plan composer (Stage 06 / B1.5-b): rule-based, catalog-driven, no LLM.

Builds a 7-day nutrition or exercise plan from `config/i8/plan_catalog_v1.yaml`, filtered by the user's own
answers (allergies, food/exercise preferences, budget, cooking time, meal times, body-function status), and
persists it as timed I8 actions (one daily plan per local date, shared with the other domain) so the Lifestyle
screens, reminders and the end-of-day/week review read the same I8 truth.

Not a therapeutic diet: the catalog holds general healthy-eating / gentle-activity items only (no calories,
doses or condition prescriptions). Users with a registered condition or reported difficulty get the
conservative variant (soft texture, seated/light movement) and the supportive-boundary line.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml
from sqlalchemy.orm import Session

_CATALOG = Path(__file__).resolve().parents[3] / "config" / "i8" / "plan_catalog_v1.yaml"
SOURCE_TAG = "sedi_plan_catalog_v1"
_DEFAULT_MEAL_TIMES = {"breakfast": "08:00", "lunch": "13:00", "dinner": "20:00", "snack": "16:30"}
_DEFAULT_EXERCISE_TIME = "17:00"
_SLOT_LABEL = {
    "fa": {"breakfast": "صبحانه", "lunch": "ناهار", "dinner": "شام", "snack": "میان‌وعده"},
    "en": {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"},
    "ar": {"breakfast": "الفطور", "lunch": "الغداء", "dinner": "العشاء", "snack": "وجبة خفيفة"},
}
_SLOT_ALIASES = {
    "breakfast": ("صبحانه", "breakfast", "الفطور"),
    "lunch": ("ناهار", "lunch", "الغداء"),
    "dinner": ("شام", "dinner", "العشاء"),
    "snack": ("میان", "snack", "خفيفة"),
}
_NEG_CUES = ("دوست ندارم", "نمی‌خورم", "نمیخورم", "نمی خورم", "بدم میاد", "خوشم نمیاد", "don't like", "do not like", "dislike", "hate", "avoid", "can't eat", "لا أحب", "لا آكل", "أتجنب")
_NO_ISSUE = ("مشکلی ندارم", "مشکلی نیست", "بدون مشکل", "خوبه", "عالیه", "no problem", "no issue", "fine", "none", "all good", "لا مشكلة", "بخير", "جيد")
_DIFFICULTY = (
    "سخت", "مشکل", "سرفه", "گیر", "درد", "ضعف", "خسته", "زمین خوردم", "سرگیجه", "نمی‌تونم", "نمیتونم", "کند",
    "hard", "difficult", "trouble", "cough", "choke", "pain", "weak", "tired", "fall", "fell", "dizz", "can't", "cannot", "struggle",
    "صعب", "مشكلة", "سعال", "اختناق", "ألم", "تعب", "سقط", "دوار", "لا أستطيع",
)
_LOW_BUDGET = ("کم", "ضعیف", "تنگ", "tight", "low", "limited", "محدود", "ضيقة")
_HIGH_BUDGET = ("راحت", "خوب", "comfortable", "high", "good", "مريحة", "جيدة")
_QUICK = ("سریع", "ساده", "کم", "quick", "simple", "little", "سريع", "بسيطة", "قليل")
_BAND = ("کش", "band", "حبل", "مطاطي")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    return yaml.safe_load(_CATALOG.read_text(encoding="utf-8"))


def _norm(text: Any) -> str:
    return " ".join(str(text or "").translate(_PERSIAN_DIGITS).lower().split())


@dataclass
class Constraints:
    allergens: set = field(default_factory=set)
    avoid_kw: set = field(default_factory=set)
    like_kw: set = field(default_factory=set)
    max_budget: int = 3
    quick: bool = False
    soft: bool = False
    seated_only: bool = False
    light_only: bool = False
    has_band: bool = False
    meal_times: dict = field(default_factory=lambda: dict(_DEFAULT_MEAL_TIMES))
    exercise_time: str = _DEFAULT_EXERCISE_TIME
    minutes_cap: Optional[int] = None
    has_condition: bool = False

    @property
    def conservative(self) -> bool:
        return self.light_only or self.seated_only or self.soft or self.has_condition


# ---------- pure parsing ----------
def parse_allergens(text: str) -> set:
    t = _norm(text)
    if not t or any(c in t for c in ("ندارم", "none", "no ", "لا يوجد", "لا ")) and not any(
        a in t for al in catalog()["allergen_aliases"].values() for a in al
    ):
        return set()
    return {k for k, aliases in catalog()["allergen_aliases"].items() if any(_norm(a) in t for a in aliases)}


def parse_preferences(text: str) -> tuple[set, set]:
    """(like_keywords, avoid_keywords) found per clause; negation cue in a clause -> avoid."""
    likes, avoids = set(), set()
    kws = {_norm(k) for it in catalog()["meals"] for k in it.get("keywords", [])}
    for clause in re.split(r"[،,;؛\n.]|\bbut\b|\band\b|اما|ولی", _norm(text)):
        hit = {k for k in kws if k and k in clause}
        if not hit:
            continue
        (avoids if any(n in clause for n in _NEG_CUES) else likes).update(hit)
    return likes - avoids, avoids


def parse_budget(text: str) -> int:
    t = _norm(text)
    if any(c in t for c in _LOW_BUDGET):
        return 1
    if any(c in t for c in _HIGH_BUDGET):
        return 3
    return 2 if t else 3


def parse_time(text: str, default: str) -> str:
    m = re.search(r"(\d{1,2})(?::(\d{2}))?", _norm(text))
    if not m:
        return default
    h = int(m.group(1))
    return f"{h:02d}:{m.group(2) or '00'}" if 0 <= h <= 23 else default


def parse_meal_times(text: str) -> dict:
    out = dict(_DEFAULT_MEAL_TIMES)
    t = _norm(text)
    for slot, names in _SLOT_ALIASES.items():
        for n in names:
            m = re.search(rf"{re.escape(n)}\D{{0,8}}(\d{{1,2}})(?::(\d{{2}}))?", t)
            if m and 0 <= int(m.group(1)) <= 23:
                out[slot] = f"{int(m.group(1)):02d}:{m.group(2) or '00'}"
                break
    return out


def has_difficulty(text: str) -> bool:
    t = _norm(text)
    if not t or any(n in t for n in _NO_ISSUE):
        return False
    return any(c in t for c in _DIFFICULTY)


def constraints_from_answers(answers: dict, *, has_condition: bool = False) -> Constraints:
    c = Constraints(has_condition=has_condition)
    c.allergens = parse_allergens(answers.get("allergies", "")) | parse_allergens(answers.get("medical_allergies", ""))
    c.like_kw, c.avoid_kw = parse_preferences(answers.get("food_preferences", ""))
    c.max_budget = parse_budget(answers.get("budget", ""))
    c.quick = any(q in _norm(answers.get("cooking_time", "")) for q in _QUICK)
    c.meal_times = parse_meal_times(answers.get("meal_times", ""))
    c.exercise_time = parse_time(answers.get("exercise_time", ""), _DEFAULT_EXERCISE_TIME)
    m = re.search(r"(\d{1,3})\s*(دقیقه|min|دقيقة)", _norm(answers.get("exercise_time", "")))
    c.minutes_cap = int(m.group(1)) if m else None
    c.has_band = any(b in _norm(answers.get("equipment", "")) for b in _BAND)
    c.soft = has_difficulty(answers.get("function_swallowing", ""))
    c.seated_only = has_difficulty(answers.get("function_mobility", "")) or has_difficulty(answers.get("function_balance", ""))
    c.light_only = any(
        has_difficulty(answers.get(f"function_{d}", ""))
        for d in ("breathing", "mobility", "balance", "pain_fatigue", "general", "cognition")
    ) or has_condition
    return c


# ---------- pure selection ----------
def _meal_candidates(slot: str, c: Constraints, relax: int) -> list[dict]:
    out = []
    for it in catalog()["meals"]:
        if slot not in it["slots"] or set(it["allergens"]) & c.allergens:
            continue
        if c.soft and it["texture"] != "soft":
            continue
        kws = {_norm(k) for k in it.get("keywords", [])}
        if relax < 3 and kws & c.avoid_kw:
            continue
        if relax < 2 and it["budget"] > c.max_budget:
            continue
        if relax < 1 and c.quick and it["prep"] > 25:
            continue
        out.append(it)
    return out


def select_nutrition_week(c: Constraints, seed: str) -> list[list[dict]]:
    """7 days x [breakfast, lunch, dinner, snack] picks: {item, slot, why[]} (allergens never relaxed)."""
    rnd = random.Random(seed)
    week: list[list[dict]] = [[] for _ in range(7)]
    for slot in ("breakfast", "lunch", "dinner", "snack"):
        pool: list[dict] = []
        for relax in range(4):
            pool = _meal_candidates(slot, c, relax)
            if pool:
                break
        if not pool:
            continue
        liked = [it for it in pool if {_norm(k) for k in it.get("keywords", [])} & c.like_kw]
        rest = [it for it in pool if it not in liked]
        rnd.shuffle(liked)
        rnd.shuffle(rest)
        order = liked + rest
        for i in range(7):
            # Rotate through the pool, but never serve a dish already planned earlier the same day.
            taken = {e["item"]["id"] for e in week[i]}
            start = i % len(order)
            it = next(
                (order[(start + k) % len(order)] for k in range(len(order)) if order[(start + k) % len(order)]["id"] not in taken),
                order[start],
            )
            why = []
            if c.soft and it["texture"] == "soft":
                why.append("soft")
            if c.max_budget == 1 and it["budget"] == 1:
                why.append("low_budget")
            if c.quick and it["prep"] <= 15:
                why.append("quick")
            if it in liked:
                why.append("preference")
            week[i].append({"item": it, "slot": slot, "why": why})  # no filler reason: only real ones (R-008)
    return week


def _exercise_candidates(c: Constraints) -> list[dict]:
    out = []
    for it in catalog()["exercises"]:
        if c.seated_only and it["needs_stand"]:
            continue
        if c.light_only and it["intensity"] != "light":
            continue
        if it["equipment"] == "band" and not c.has_band:
            continue
        out.append(it)
    return out


def select_exercise_week(c: Constraints, seed: str) -> list[list[dict]]:
    rnd = random.Random(seed)
    active = {1, 3, 5, 6} if c.conservative else {1, 2, 4, 5, 6}
    pool = _exercise_candidates(c)
    breathing = [it for it in pool if it["type"] == "breathing"]
    movers = [it for it in pool if it["type"] != "breathing"] or pool
    rnd.shuffle(movers)
    week: list[list[dict]] = []
    for i in range(7):
        day: list[dict] = []
        if (i + 1) in active and movers:
            main = movers[i % len(movers)]
            why = ["seated"] if not main["needs_stand"] else (["light"] if main["intensity"] == "light" else [])
            day.append({"item": main, "slot": "exercise", "why": why})
            if c.conservative and breathing and (i + 1) in (1, 5):
                day.append({"item": breathing[0], "slot": "exercise", "why": ["light"]})
        else:
            day.append({"item": {"id": "rest", "type": "rest", "minutes": 0}, "slot": "rest", "why": []})
        week.append(day)
    return week


# ---------- rendering ----------
def _lang(language: Optional[str]) -> str:
    lang = (language or "fa").strip().lower().split("-")[0]
    return lang if lang in ("fa", "en", "ar") else "en"


def render_item(entry: dict, language: str, voiced: Optional[dict] = None) -> tuple[str, str]:
    lang = _lang(language)
    cat = catalog()
    title, how = cat["texts"][entry["item"]["id"]][lang]
    if voiced and voiced.get(entry["item"]["id"]):
        how = voiced[entry["item"]["id"]]  # Sedi's own voice (plan_voice); the rules still chose the item
    why = [cat["why"][k][lang] for k in entry["why"] if k in cat["why"]]
    sep = {"fa": "؛ چرا: ", "en": "; why: ", "ar": "؛ لماذا: "}[lang]
    detail = how + (sep + "، ".join(why[:2]) if why else "")
    if entry["slot"] == "exercise":
        detail += " " + cat["safety_line"][lang]
    return title, detail


def _day_header(lang: str) -> str:
    return {
        "fa": "برنامه‌ی ۷ روزه‌ات رو با دقت و به‌اندازه‌ی خودت چیدم، عزیزم؛ همه‌ی روزها رو توی «سبک زندگی» می‌بینی. امروز:",
        "en": "I put your 7-day plan together carefully, just for you; you can see every day in Lifestyle. Today:",
        "ar": "رتّبتُ لك خطة السبعة أيام بعناية وعلى مقياسك؛ تجد كل الأيام في «نمط الحياة». اليوم:",
    }[lang]


# ---------- persistence ----------
@dataclass
class ComposeResult:
    status: str
    user_message: str = ""
    plan_id: Optional[int] = None
    action_id: Optional[int] = None
    created: int = 0
    today: list = field(default_factory=list)
    knowledge_refs: list = field(default_factory=list)


def _fact_text(row: Any) -> str:
    raw = str(getattr(row, "value_json", "") or "")
    try:
        val = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)


def read_answers(db: Session, user_id: int) -> tuple[dict, bool]:
    """User-stated answers (I6 intake/function/medical allergies) + whether a condition is on file."""
    from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty

    answers: dict = {}
    for domain in ("intake", "function"):
        for row in list_facts_readonly_or_empty(db, user_id, domain=domain):
            answers[row.key if domain == "intake" else f"function_{row.key}"] = _fact_text(row)
    for row in list_facts_readonly_or_empty(db, user_id, domain="medical"):
        if row.key == "allergies":
            answers["medical_allergies"] = _fact_text(row)
    try:
        from backend.app.services.rag_context.rag_context_builder import _get_medical_conditions_for_user

        has_condition = any(str(c).strip() for c in (_get_medical_conditions_for_user(db, user_id) or []))
    except Exception:
        has_condition = False
    return answers, has_condition


def compose_week_plan(
    db: Session,
    *,
    user_id: int,
    domain: str,
    language: str,
    constraints: Optional[Constraints] = None,
    persist: bool = True,
    knowledge_refs_json: str = "[]",
) -> ComposeResult:
    """Compose (and persist) the 7-day plan of `domain` ('nutrition' | 'exercise'). Idempotent per cycle/day/slot."""
    from backend.app.services.i6.consent_service import PERM_READ, ConsentDenied, has_permission
    from backend.app.services.i8.lifecycle import I8OperationalLifecycle
    from backend.app.services.i8.local_day import resolve_local_day_window_for_date
    from backend.app.services.i8.rolling_cycle import resolve_persist_cycle_bounds
    from backend.app.services.i8.unified_core import _build_display_meta, _default_action_type, _shared_daily_plan_key

    lang = _lang(language)
    if not has_permission(db, user_id, PERM_READ):
        return ComposeResult(status="CONSENT_REQUIRED")
    if constraints is None:
        answers, has_condition = read_answers(db, user_id)
        constraints = constraints_from_answers(answers, has_condition=has_condition)
    bounds = resolve_persist_cycle_bounds(db, user_id)
    cycle_start = bounds.cycle_start
    if bounds.is_new_cycle:
        from backend.app.services.i8.action_review import LOW_ADHERENCE_PERCENT, last_cycle_adherence_percent

        last = last_cycle_adherence_percent(db, user_id, domain)
        if last is not None and last < LOW_ADHERENCE_PERCENT:
            constraints.light_only = True  # the previous week was too hard to keep up: go lighter
    seed = f"{user_id}:{domain}:{cycle_start.isoformat()}"
    week = select_nutrition_week(constraints, seed) if domain == "nutrition" else select_exercise_week(constraints, seed)
    voiced: dict = {}
    try:
        from backend.app.services.i8 import plan_voice

        if plan_voice.plan_voice_enabled():
            voiced = plan_voice.voice_week(week, lang, constraints)
    except Exception:
        voiced = {}
    today_local = bounds.today_local
    lifecycle = I8OperationalLifecycle()
    result = ComposeResult(status="ACTION_PERSISTED")
    for i, day in enumerate(week):
        local_date = cycle_start + timedelta(days=i)
        if local_date < today_local:
            continue
        window = resolve_local_day_window_for_date(db, user_id, local_date)
        lines = []
        try:
            plan = None
            for n, entry in enumerate(day):
                title, detail = render_item(entry, lang, voiced)
                slot = entry["slot"]
                minutes = int(entry["item"].get("minutes", 0) or 0)
                if constraints.minutes_cap and minutes:
                    minutes = min(minutes, constraints.minutes_cap)
                local_time = (
                    constraints.meal_times.get(slot) if domain == "nutrition" else constraints.exercise_time
                )
                if entry["slot"] == "rest":
                    local_time = None
                meta = {"title": title, "local_time": local_time}
                if domain == "nutrition":
                    meta["meal_slot"] = slot
                else:
                    meta.update({"activity_type": entry["item"]["type"], "activity_title": title, "duration_minutes": minutes or None})
                presentation = _build_display_meta(window=window, day_index=i + 1, cycle_start=cycle_start, display_meta=meta)
                presentation.update({"detail": detail, "source": SOURCE_TAG, "domain": domain})
                if entry["slot"] != "rest":
                    presentation["item_id"] = entry["item"]["id"]
                lines.append((slot, local_time, title, detail))
                if not persist:
                    continue
                if plan is None:
                    plan, _ = lifecycle.ensure_active_plan(
                        db,
                        user_id=user_id,
                        window=window,
                        generation_mode="reactive",
                        plan_idempotency_key=_shared_daily_plan_key(
                            user_id=user_id, user_local_date_iso=window.user_local_date.isoformat(), generation_mode="reactive"
                        ),
                    )
                action, was_created = lifecycle.ensure_action(
                    db,
                    user_id=user_id,
                    plan=plan,
                    window=window,
                    action_domain=domain,
                    action_type=_default_action_type(domain),
                    action_idempotency_key=f"composer:{domain}:{user_id}:{cycle_start.isoformat()}:{local_date.isoformat()}:{n}",
                    summary_text=title[:256],
                    presentation_json=json.dumps(presentation, ensure_ascii=False, separators=(",", ":")),
                    knowledge_refs_json=knowledge_refs_json,
                    safety_state="SAFE",
                    context_refs_json="[]",
                )
                result.created += 1 if was_created else 0
                if result.plan_id is None:
                    result.plan_id, result.action_id = int(plan.id), int(action.id)
        except ConsentDenied:
            db.rollback()
            return ComposeResult(status="CONSENT_REQUIRED")
        if local_date == today_local:
            result.today = lines
    if persist:
        db.commit()
    result.user_message = _today_message(domain, lang, result.today)
    try:
        result.knowledge_refs = json.loads(knowledge_refs_json or "[]")
    except ValueError:
        result.knowledge_refs = []
    return result


def _today_message(domain: str, lang: str, lines: list) -> str:
    if not lines:
        return _day_header(lang)
    body = []
    for slot, local_time, title, detail in lines:
        label = _SLOT_LABEL[lang].get(slot, {"fa": "ورزش", "en": "Exercise", "ar": "تمرين"}[lang])
        if slot == "rest":
            label = {"fa": "امروز", "en": "Today", "ar": "اليوم"}[lang]
        when = f" ({local_time})" if local_time else ""
        body.append(f"• {label}{when}: {title} — {detail}")
    return _day_header(lang) + "\n" + "\n".join(body)


def try_compose_for_chat(
    db: Session,
    *,
    user_id: int,
    actor_user_id: int,
    request: str,
    domain: str,
    language: str,
    health_subject_id: Optional[int] = None,
) -> Optional[ComposeResult]:
    """Composer entry for chat plan intents; None means "use the legacy grounded path" (other subject,
    identity mismatch, safety block, consent or any failure) so every existing fail-safe still applies."""
    if actor_user_id != user_id or health_subject_id is not None:
        return None
    try:
        if domain == "nutrition":
            # R-008: never build a week of meals before the user's allergies are known (hard safety input).
            answers, _ = read_answers(db, user_id)
            if not (answers.get("allergies") or answers.get("medical_allergies")):
                return None
        # I5 stays the grounding authority: the same retrieval + safety gates as the legacy path must pass
        # (otherwise the legacy fail-safe answer is used), and the governed refs are stored on every action.
        from backend.app.services.i8 import unified_core as uc
        from backend.app.services.i8.context import load_trusted_context

        ctx = load_trusted_context(db, user_id)
        if not uc.evaluate_safety(request=request, ctx=ctx, retrieval=None, domain=domain).allowed:
            return None
        retrieval = uc.retrieve_governed_knowledge(db, user_id=user_id, query=request, domain=domain, ctx=ctx)
        if not uc.evaluate_safety(request=request, ctx=ctx, retrieval=retrieval, domain=domain).allowed:
            return None
        composition = uc.compose_grounded_action(retrieval, domain=domain, ctx=ctx)
        if composition is None:
            return None
        if not uc.evaluate_composed_safety(candidate_text=uc._candidate_text(composition.suggestions), ctx=ctx).allowed:
            return None
        res = compose_week_plan(
            db,
            user_id=user_id,
            domain=domain,
            language=language,
            knowledge_refs_json=uc.knowledge_refs_payload(composition.used_items),
        )
    except Exception:
        db.rollback()
        return None
    return res if res.status == "ACTION_PERSISTED" and res.action_id is not None else None
