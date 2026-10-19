"""Fixed trailer lines for I8 plan replies (Stage 06 / B1).

1) Always: where the saved plan lives in the app (Lifestyle section).
2) Only when the user has a registered condition: the supportive boundary — a general supportive plan to
   coordinate with the care team / dietitian, never a therapeutic diet, calories or doses (I4 boundary).
Deterministic, no LLM; the clinical wording needs the founder's approval (see Stage 06 / D3).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

_POINTER = {
    ("nutrition", "fa"): "برنامه‌ات رو توی بخش «سبک زندگی» ← «برنامه‌ی غذایی» هم می‌تونی ببینی.",
    ("nutrition", "en"): "You can also see your plan in Lifestyle > Nutrition plan.",
    ("nutrition", "ar"): "يمكنك أيضاً رؤية خطتك في «نمط الحياة» ← «خطة التغذية».",
    ("exercise", "fa"): "برنامه‌ات رو توی بخش «سبک زندگی» ← «برنامه‌ی ورزشی» هم می‌تونی ببینی.",
    ("exercise", "en"): "You can also see your plan in Lifestyle > Exercise plan.",
    ("exercise", "ar"): "يمكنك أيضاً رؤية خطتك في «نمط الحياة» ← «خطة التمارين».",
}
_BOUNDARY = {
    "fa": (
        "این یه برنامه‌ی حمایتی و عمومیه، نه رژیم یا نسخه‌ی درمانی؛ با توجه به بیماری‌ات حتماً با تیم درمان یا "
        "کارشناس تغذیه هماهنگش کن. اگه خودشون برنامه‌ی مشخصی دادن، همون ملاک است."
    ),
    "en": (
        "This is a general supportive plan, not a therapeutic diet or prescription; because of your condition, "
        "please coordinate it with your care team or dietitian. If they gave you a specific plan, theirs takes priority."
    ),
    "ar": (
        "هذه خطة داعمة وعامة وليست حمية علاجية أو وصفة؛ وبسبب حالتك يرجى تنسيقها مع فريقك العلاجي أو أخصائي التغذية. "
        "وإن أعطوك خطة محددة فهي المرجع."
    ),
}


def _lang(language: Optional[str]) -> str:
    lang = (language or "fa").strip().lower().split("-")[0]
    return lang if lang in ("fa", "en", "ar") else "en"


def has_registered_condition(db: Optional[Session], user_id: int) -> bool:
    if db is None:
        return False
    try:
        from backend.app.services.rag_context.rag_context_builder import _get_medical_conditions_for_user

        return any(str(c).strip() for c in (_get_medical_conditions_for_user(db, user_id) or []))
    except Exception:
        return False


def build_plan_trailer(db: Optional[Session], user_id: int, language: Optional[str], domain: str) -> str:
    lang = _lang(language)
    lines = [_POINTER[(domain if domain in ("nutrition", "exercise") else "nutrition", lang)]]
    if has_registered_condition(db, user_id):
        lines.append(_BOUNDARY[lang])
    return "\n".join(lines)
