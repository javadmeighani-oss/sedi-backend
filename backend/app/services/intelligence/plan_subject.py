"""Who is the plan for? (I1, pure; Stage 06 / B1).

A personalized nutrition/activity plan is stored for the signed-in account's own profile. When the message
is about someone else ("برای پدرم", "for my mother"), Sedi asks who the plan is for instead of silently
saving a plan on the wrong person. No DB, no LLM, no new storage; other-person care stays on the existing
HealthSubject / care-network path.
"""
from __future__ import annotations

from typing import Optional

_THIRD_PERSON_CUES = {
    "fa": (
        "پدرم", "مادرم", "همسرم", "شوهرم", "زنم", "فرزندم", "پسرم", "دخترم", "برادرم", "خواهرم",
        "پدربزرگ", "مادربزرگ", "دوستم", "بیمارم", "مادرشوهر", "پدرشوهر", "پدر من", "مادر من",
    ),
    "ar": ("أبي", "امي", "أمي", "زوجتي", "زوجي", "ابني", "ابنتي", "أخي", "أختي", "جدي", "جدتي", "صديقي", "مريضي"),
    "en": (
        "my father", "my mother", "my dad", "my mom", "my wife", "my husband", "my son", "my daughter",
        "my brother", "my sister", "my grandmother", "my grandfather", "my friend", "my patient", "my parent",
    ),
}
_SELF_CUES = {
    "fa": ("برای خودم", "برای خودمه", "مال خودم"),
    "ar": ("لنفسي", "لي أنا"),
    "en": ("for myself", "for me,", "my own plan"),
}

_QUESTION = {
    "fa": (
        "این برنامه رو برای خودت می‌خوای یا برای کسی که گفتی؟ برنامه‌ی ذخیره‌شده توی اپ فقط برای پروفایل خودته؛ "
        "برای فرد دیگه می‌تونم اطلاعات کلی بدم و اگه خواستی از بخش مراقبت از دیگران اضافه‌اش کنی. "
        "بگو برای کدوم شروع کنیم؟"
    ),
    "en": (
        "Is this plan for you or for the person you mentioned? The plan saved in the app belongs to your own "
        "profile only; for someone else I can share general guidance, and you can add them from the care-for-others "
        "section. Which one should we start with?"
    ),
    "ar": (
        "هل هذه الخطة لك أم للشخص الذي ذكرته؟ الخطة المحفوظة في التطبيق تخص ملفك أنت فقط؛ "
        "وللشخص الآخر يمكنني تقديم معلومات عامة، ويمكنك إضافته من قسم رعاية الآخرين. بأيهما نبدأ؟"
    ),
}


def _root(language: Optional[str]) -> str:
    lang = (language or "fa").strip().lower().split("-")[0]
    return lang if lang in _QUESTION else "en"


def mentions_other_person(message: str, language: Optional[str]) -> bool:
    text = " ".join((message or "").lower().split())
    if not text:
        return False
    root = _root(language)
    if any(c in text for c in _SELF_CUES[root]):
        return False
    return any(c in text for c in _THIRD_PERSON_CUES[root])


def plan_subject_question(language: Optional[str]) -> str:
    return _QUESTION[_root(language)]
