"""Gate 3 emergency and high-risk fixed templates (no LLM)."""

TEMPLATES = {
    "emergency": {
        "fa": (
            "این وضعیت ممکن است اورژانسی باشد. لطفاً فوراً با خدمات اورژانس محلی یا پزشک تماس بگیرید. "
            "من نمی‌توانم تشخیص بدهم یا درمان اورژانسی ارائه کنم."
        ),
        "en": (
            "This may be a medical emergency. Please contact local emergency services or a clinician immediately. "
            "I cannot provide a diagnosis or emergency treatment instructions."
        ),
        "ar": (
            "قد تكون هذه حالة طارئة. يرجى الاتصال فوراً بخدمات الطوارئ المحلية أو بطبيب. "
            "لا يمكنني تقديم تشخيص أو تعليمات علاج طارئة."
        ),
    },
    "high_risk": {
        "fa": (
            "این موضوع نیاز به بررسی فوری توسط پزشک دارد. لطفاً در اسرع وقت با پزشک معتمد مشورت کنید. "
            "من فقط اطلاعات عمومی و حمایتی ارائه می‌دهم، نه تشخیص یا دستور درمان."
        ),
        "en": (
            "This needs prompt review by a qualified clinician. Please consult a doctor as soon as possible. "
            "I can only offer general supportive information, not diagnosis or treatment orders."
        ),
        "ar": (
            "يتطلب هذا مراجعة عاجلة من طبيب مؤهل. يرجى استشارة طبيب في أقرب وقت. "
            "يمكنني تقديم معلومات داعمة عامة فقط."
        ),
    },
    "no_source": {
        "fa": (
            "اطلاعات کافی از منابع معتبر ثبت‌شده ندارم. لطفاً با پزشک معتمد مشورت کنید."
        ),
        "en": (
            "I do not have enough information from registered trusted sources. Please consult a qualified clinician."
        ),
        "ar": (
            "ليس لدي معلومات كافية من مصادر موثوقة مسجلة. يرجى استشارة طبيب مؤهل."
        ),
    },
    "safe_fallback": {
        "fa": (
            "برای ایمنی شما، نمی‌توانم این پاسخ را ارائه دهم. لطفاً با پزشک معتمد مشورت کنید."
        ),
        "en": (
            "For your safety, I cannot provide that response. Please consult a qualified clinician."
        ),
        "ar": (
            "لسلامتك، لا يمكنني تقديم هذا الجواب. يرجى استشارة طبيب مؤهل."
        ),
    },
}


def get_template(key: str, language: str) -> str:
    lang = (language or "fa").strip().lower()
    if lang.startswith("fa"):
        bucket = "fa"
    elif lang.startswith("ar"):
        bucket = "ar"
    else:
        bucket = "en"
    return TEMPLATES.get(key, {}).get(bucket) or TEMPLATES[key]["en"]
