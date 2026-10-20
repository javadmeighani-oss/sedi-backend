"""CR-01 / CR-04B / CR-04F.1 / CR-04F.2 / Q2 — Pure Next Best Question (NBQ) selector.

Deterministic. No DB, network, LLM, writes, or legacy KC reads.
CR-01 stores metadata only; user-visible discovery belongs to CR-02.
CR-04B adds optional message-scoped contextual candidates that may outrank
legacy NBQ only when relevance evidence is present in the current message.
CR-04F.1 adds request-local coverage-aware Tier-A progressive discovery on GENERAL.
CR-04F.2 adds CONFLICTED/STALE confirmation ahead of missing discovery.
Q2 adds bounded explicit discovery-invitation handling (one low-risk missing target).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from backend.app.services.intelligence.context_types import (
    ContextItem,
    ContextSnapshot,
)
from backend.app.services.intelligence.contracts import (
    DiscoveryDirective,
    IntentId,
    IntentResult,
    LanguageCode,
    ReadinessResult,
    ReadinessStatus,
)
from backend.app.services.intelligence.user_understanding_coverage import (
    REGISTERED_TARGETS,
    TIER_A_GENERAL_PRIORITY,
    TIER_A_TARGETS,
    TIER_C_NEVER_MISSING_DRIVEN,
    CoverageState,
    coverage_state_for_key,
    is_safe_missing_for_discovery,
)

# Intents where soft discovery is never appropriate (safety / specialized paths).
_NBQ_SUPPRESSED_INTENTS: frozenset[IntentId] = frozenset(
    {
        IntentId.SYMPTOM,
        IntentId.MEDICATION,
        IntentId.VITALS,
        IntentId.REMINDER,
        IntentId.NOTIFICATION_FOLLOW_UP,
    }
)

# Ordered soft-discovery candidates per supported intent (stable priority).
# Each entry: (target_key, sensitivity, template_id, priority)
# GENERAL uses Tier-A progressive order (CR-04F.1).
_SOFT_DISCOVERY_CANDIDATES: dict[IntentId, tuple[tuple[str, str, str, int], ...]] = {
    IntentId.SLEEP: (
        ("routines.bedtime", "medium", "nbq.sleep.bedtime.v1", 10),
        ("routines.wake_time", "medium", "nbq.sleep.wake_time.v1", 20),
        ("lifestyle.sleep_quality", "medium", "nbq.sleep.sleep_quality.v1", 30),
    ),
    IntentId.NUTRITION: (
        ("lifestyle.food_habits", "medium", "nbq.nutrition.food_habits.v1", 10),
    ),
    IntentId.ACTIVITY: (
        ("lifestyle.activity_level", "medium", "nbq.activity.activity_level.v1", 10),
        (
            "routines.exercise_schedule",
            "medium",
            "nbq.activity.exercise_schedule.v1",
            20,
        ),
    ),
    IntentId.GENERAL: (
        (
            "preferences.interests",
            "medium",
            "nbq.general.interests.v1",
            10,
        ),
        # R-008: Sedi never asks the style / listen-first / length questionnaire; those
        # preferences are only learned when the user states them (or from behaviour).
    ),
}

_TIER_A_TEMPLATE_BY_KEY: dict[str, tuple[str, str, int]] = {
    "preferences.interests": ("medium", "nbq.general.interests.v1", 10),
    "preferences.communication_style": (
        "medium",
        "nbq.general.communication_style.v1",
        20,
    ),
    "preferences.listen_before_advice": (
        "medium",
        "nbq.general.listen_before_advice.v1",
        30,
    ),
    "preferences.response_length": ("medium", "nbq.general.response_length.v1", 40),
}

# Q2/Q4 — invitation soft order over existing safe I6 targets (templates reused).
# barriers.time_constraints stays contextual-only (never in this list).
_INVITATION_SOFT_PRIORITY: tuple[str, ...] = (
    "preferences.interests",
    "work.occupation",
    "work.work_schedule",
    "lifestyle.activity_level",
    "lifestyle.food_habits",
    "lifestyle.sleep_quality",
    "routines.exercise_schedule",
    "routines.bedtime",
    "routines.wake_time",
)

_INVITATION_TEMPLATE_BY_KEY: dict[str, tuple[str, str, int]] = {
    "preferences.interests": ("medium", "nbq.general.interests.v1", 10),
    "work.occupation": ("medium", "nbq.general.occupation.v1", 20),
    "work.work_schedule": ("medium", "nbq.contextual.work_schedule.v1", 30),
    "lifestyle.activity_level": ("medium", "nbq.activity.activity_level.v1", 40),
    "lifestyle.food_habits": ("medium", "nbq.nutrition.food_habits.v1", 50),
    "lifestyle.sleep_quality": ("medium", "nbq.sleep.sleep_quality.v1", 60),
    "routines.exercise_schedule": ("medium", "nbq.activity.exercise_schedule.v1", 70),
    "routines.bedtime": ("medium", "nbq.sleep.bedtime.v1", 80),
    "routines.wake_time": ("medium", "nbq.sleep.wake_time.v1", 90),
    "preferences.communication_style": (
        "medium",
        "nbq.general.communication_style.v1",
        100,
    ),
    "preferences.listen_before_advice": (
        "medium",
        "nbq.general.listen_before_advice.v1",
        110,
    ),
    "preferences.response_length": ("medium", "nbq.general.response_length.v1", 120),
}

# Q4.2B — invited-only tightly-related pairs (no arbitrary pairing).
_INVITED_SAFE_PAIRS: tuple[frozenset[str], ...] = (
    frozenset({"work.occupation", "work.work_schedule"}),
    frozenset({"lifestyle.activity_level", "routines.exercise_schedule"}),
    frozenset({"routines.bedtime", "routines.wake_time"}),
)


def _invited_companion_key(primary: str) -> Optional[str]:
    for pair in _INVITED_SAFE_PAIRS:
        if primary in pair:
            for key in pair:
                if key != primary:
                    return key
    return None

# Explicit discovery invitation cues (bounded; not a new intent subsystem).
_DISCOVERY_INVITATION_CUES: dict[str, tuple[str, ...]] = {
    "en": (
        "ask me something",
        "what do you want to know",
        "what do you need to know about me",
        "do you want more information about me",
        "want to know more about me",
        "get to know me better",
        "ask me whatever you need",
    ),
    "fa": (
        "چی میخوای بدونی",
        "چی می‌خوای بدونی",
        "چی میخوایی بدونی",
        "چی می‌خوایی بدونی",
        "ازم سوال بپرس",
        "چه اطلاعاتی لازم داری",
        "میخوای منو بیشتر بشناسی",
        "اطلاعات بیشتری داشته باشی",
        "نمیخوای اطلاعات بیشتری داشته باشی",
        "نمی‌خوای اطلاعات بیشتری داشته باشی",
        "نمیخوای بیشتر از من بدونی",
        "نمی‌خوای بیشتر از من بدونی",
        "بیشتر منو بشناس",
        "هرچی لازم داری بپرس",
    ),
    "ar": (
        "اسألني شيئا",
        "اسألني شيء",
        "ماذا تريد أن تعرف",
        "ماذا تحتاج أن تعرف عني",
        "هل تريد معلومات أكثر عني",
        "هل تريد معرفة المزيد عني",
        "تعرف علي أكثر",
        "اسألني ما تحتاج",
    ),
}

# Intent-scoped confirmation keys (sleep/nutrition/activity).
_INTENT_CONFIRM_KEYS: dict[IntentId, frozenset[str]] = {
    IntentId.SLEEP: frozenset(
        {"routines.bedtime", "routines.wake_time", "lifestyle.sleep_quality"}
    ),
    IntentId.NUTRITION: frozenset({"lifestyle.food_habits"}),
    IntentId.ACTIVITY: frozenset(
        {"lifestyle.activity_level", "routines.exercise_schedule"}
    ),
}

# Stable confirmation priority across all confirmable targets (lower = first).
_CONFIRMATION_PRIORITY: tuple[str, ...] = (
    "preferences.interests",
    "preferences.communication_style",
    "preferences.listen_before_advice",
    "preferences.response_length",
    "work.work_schedule",
    "barriers.time_constraints",
    "routines.bedtime",
    "routines.wake_time",
    "lifestyle.sleep_quality",
    "lifestyle.food_habits",
    "lifestyle.activity_level",
    "routines.exercise_schedule",
)

_CONFIRMATION_PRIORITY_INDEX: dict[str, int] = {
    k: i for i, k in enumerate(_CONFIRMATION_PRIORITY)
}

# Bounded localized field labels for confirmation templates.
_FIELD_LABELS: dict[str, dict[str, str]] = {
    "preferences.interests": {
        "en": "interests",
        "fa": "علاقه‌مندی‌ها",
        "ar": "الاهتمامات",
    },
    "preferences.communication_style": {
        "en": "communication style",
        "fa": "سبک گفت‌وگو",
        "ar": "أسلوب التواصل",
    },
    "preferences.listen_before_advice": {
        "en": "listen-first preference",
        "fa": "ترجیح گوش‌دادن پیش از پیشنهاد",
        "ar": "تفضيل الاستماع قبل الاقتراح",
    },
    "preferences.response_length": {
        "en": "response length",
        "fa": "طول پاسخ",
        "ar": "طول الإجابة",
    },
    "routines.bedtime": {"en": "bedtime", "fa": "ساعت خواب", "ar": "وقت النوم"},
    "routines.wake_time": {
        "en": "wake time",
        "fa": "ساعت بیداری",
        "ar": "وقت الاستيقاظ",
    },
    "lifestyle.sleep_quality": {
        "en": "sleep quality",
        "fa": "کیفیت خواب",
        "ar": "جودة النوم",
    },
    "lifestyle.food_habits": {
        "en": "eating habits",
        "fa": "عادت‌های غذایی",
        "ar": "العادات الغذائية",
    },
    "lifestyle.activity_level": {
        "en": "activity level",
        "fa": "سطح فعالیت",
        "ar": "مستوى النشاط",
    },
    "routines.exercise_schedule": {
        "en": "exercise schedule",
        "fa": "برنامه ورزش",
        "ar": "جدول الرياضة",
    },
    "work.work_schedule": {
        "en": "work schedule",
        "fa": "برنامه کاری",
        "ar": "جدول العمل",
    },
    "barriers.time_constraints": {
        "en": "time constraints",
        "fa": "محدودیت زمانی",
        "ar": "قيود الوقت",
    },
}

# CR-04B — contextual candidates. Lower priority number wins among relevant hits.
# These outrank legacy NBQ only when message relevance is true.
_WORK_SCHEDULE_RELEVANCE_CUES: tuple[str, ...] = (
    "night shift",
    "night shifts",
    "shift work",
    "work schedule",
    "work shifts",
    "my shifts",
    "on shift",
    "working nights",
    "شیفت کاری",
    "شیفت شب",
    "شیفت",
    "ساعات کاری",
    "دوام العمل",
    "دوام ليلي",
    "دوام لیلي",
    "ورديات",
)

_TIME_CONSTRAINT_RELEVANCE_CUES: tuple[str, ...] = (
    "don't have enough time",
    "do not have enough time",
    "dont have enough time",
    "not enough time",
    "no time to",
    "lack of time",
    "limited time",
    "too busy to",
    "وقت کم",
    "وقت ندارم",
    "وقت خیلی کم",
    "وقت کافی ندارم",
    "ليس لدي وقت",
    "ليس لدي وقت كاف",
    "ما عندي وقت",
    "لا وقت لدي",
)


@dataclass(frozen=True)
class _ContextualCandidate:
    target_key: str
    sensitivity: str
    template_id: str
    priority: int
    compatible_intents: frozenset[IntentId]
    relevance_cues: tuple[str, ...]


_CONTEXTUAL_CANDIDATES: tuple[_ContextualCandidate, ...] = (
    _ContextualCandidate(
        target_key="work.work_schedule",
        sensitivity="medium",
        template_id="nbq.contextual.work_schedule.v1",
        priority=1,
        compatible_intents=frozenset({IntentId.GENERAL, IntentId.SLEEP}),
        relevance_cues=_WORK_SCHEDULE_RELEVANCE_CUES,
    ),
    _ContextualCandidate(
        target_key="barriers.time_constraints",
        sensitivity="high",
        template_id="nbq.contextual.time_constraints.v1",
        priority=2,
        compatible_intents=frozenset(
            {
                IntentId.GENERAL,
                IntentId.SLEEP,
                IntentId.NUTRITION,
                IntentId.ACTIVITY,
            }
        ),
        relevance_cues=_TIME_CONSTRAINT_RELEVANCE_CUES,
    ),
)

_TEMPLATES: dict[str, dict[str, str]] = {
    # Stage 06 / B1.5-a: friendly plan-intake questions.
    "nbq.intake.goal_nutrition.v1": {
        "en": 'Before I build your plan, let me get to know you a little. Why do you want a meal plan? Is there a condition or problem, or do you simply want to take better care of your health?',
        "fa": 'قبل از اینکه برنامه بچینم، بذار یه کم بیشتر بشناسمت. چرا برنامه\u200cی غذایی می\u200cخوای؟ مشکل یا بیماری خاصی هست، یا فقط می\u200cخوای بیشتر به سلامتت برسی؟',
        "ar": 'قبل أن أضع خطتك دعني أتعرف عليك قليلاً. لماذا تريد خطة غذائية؟ هل هناك مرض أو مشكلة معينة، أم تريد فقط العناية بصحتك أكثر؟',
    },
    "nbq.intake.goal_exercise.v1": {
        "en": 'To make your exercise plan really fit you, let me get to know you first. Why do you want an exercise plan? Is there a condition or problem, or do you just want to be more active?',
        "fa": 'برای اینکه برنامه\u200cی ورزشی\u200cات واقعاً به درد خودت بخوره، بذار اول بیشتر بشناسمت. چرا ورزش می\u200cخوای؟ مشکل یا بیماری خاصی هست، یا فقط می\u200cخوای فعال\u200cتر بشی؟',
        "ar": 'كي تناسبك خطة التمارين حقاً، دعني أتعرف عليك أولاً. لماذا تريد خطة تمارين؟ هل هناك مرض أو مشكلة، أم تريد فقط أن تكون أكثر نشاطاً؟',
    },
    "nbq.intake.allergies.v1": {
        "en": 'Do you have any food allergy or intolerance? If not, just say none.',
        "fa": 'به غذای خاصی آلرژی یا عدم تحمل داری؟ اگه نه، بگو «ندارم».',
        "ar": 'هل لديك حساسية أو عدم تحمل لأي طعام؟ إن لم يكن، قل «لا يوجد».',
    },
    "nbq.intake.food_preferences.v1": {
        "en": 'Which foods do you like, and which ones do you dislike or avoid?',
        "fa": 'چه غذاهایی دوست داری و از چی خوشت نمیاد یا نمی\u200cخوری؟',
        "ar": 'ما الأطعمة التي تحبها وما التي لا تحبها أو تتجنبها؟',
    },
    "nbq.intake.budget.v1": {
        "en": 'How comfortable is your budget for groceries? Keep it simple: tight, medium or comfortable.',
        "fa": 'برای خرید مواد غذایی چقدر امکانات مالی داری؟ ساده بگو: کم، متوسط یا راحت.',
        "ar": 'ما مدى راحة ميزانيتك لشراء الطعام؟ ببساطة: محدودة أو متوسطة أو مريحة.',
    },
    "nbq.intake.cooking_time.v1": {
        "en": 'How much time and energy do you have for cooking? Quick and simple meals, or can you spend more time?',
        "fa": 'برای آشپزی چقدر وقت و حال داری؟ غذای ساده و سریع یا می\u200cتونی وقت بیشتری بذاری؟',
        "ar": 'كم من الوقت والطاقة لديك للطبخ؟ وجبات سريعة وبسيطة أم يمكنك قضاء وقت أطول؟',
    },
    "nbq.intake.meal_times.v1": {
        "en": 'What times do you usually eat? Breakfast, lunch, dinner and snacks.',
        "fa": 'معمولاً چه ساعت\u200cهایی غذا می\u200cخوری؟ صبحانه، ناهار، شام و میان\u200cوعده.',
        "ar": 'في أي أوقات تأكل عادة؟ الفطور والغداء والعشاء والوجبات الخفيفة.',
    },
    "nbq.intake.exercise_preferences.v1": {
        "en": 'What kind of movement do you enjoy or can you do? For example walking, stretching or chair exercises.',
        "fa": 'چه نوع حرکتی دوست داری یا می\u200cتونی انجام بدی؟ مثلاً پیاده\u200cروی، کشش یا تمرین روی صندلی.',
        "ar": 'ما نوع الحركة التي تحبها أو تستطيع القيام بها؟ مثل المشي أو التمدد أو تمارين الكرسي.',
    },
    "nbq.intake.exercise_time.v1": {
        "en": 'How much time per day and at what hour could you move?',
        "fa": 'روزی چقدر وقت و چه ساعتی برای حرکت داری؟',
        "ar": 'كم من الوقت يومياً وفي أي ساعة يمكنك أن تتحرك؟',
    },
    "nbq.intake.equipment.v1": {
        "en": 'Where will you exercise, and do you have any equipment or assistive aid? Home, park, gym, chair, band.',
        "fa": 'کجا تمرین می\u200cکنی و وسیله\u200cی خاصی داری؟ خونه، پارک، باشگاه، صندلی، کش ورزشی یا وسیله\u200cی کمکی.',
        "ar": 'أين ستتمرن وهل لديك معدات أو وسيلة مساعدة؟ المنزل أو الحديقة أو النادي أو كرسي أو حبل مطاطي.',
    },
    # Stage 06 / B1: body-function questions (open, conversational; asked only for plan intents).
    "nbq.function.swallowing.v1": {
        "en": 'How are eating, chewing and swallowing going these days? Tell me if anything is hard.',
        "fa": 'خوردن، جویدن و قورت دادن غذا این روزها برات چطوره؟ اگه چیزی سخته بگو.',
        "ar": 'كيف حال الأكل والمضغ والبلع هذه الأيام؟ قل لي إن كان شيء صعباً.',
    },
    "nbq.function.mobility.v1": {
        "en": 'How is moving around, walking and getting about at home these days?',
        "fa": 'راه رفتن و حرکت کردن توی خونه این روزها چطوره؟',
        "ar": 'كيف حال المشي والحركة داخل البيت هذه الأيام؟',
    },
    "nbq.function.breathing.v1": {
        "en": 'How is your breathing when you are active or eating? Do you tire quickly?',
        "fa": 'نفس کشیدنت موقع فعالیت یا غذا خوردن چطوره؟ زود خسته می\u200cشی؟',
        "ar": 'كيف تنفسك أثناء النشاط أو الأكل؟ هل تتعب بسرعة؟',
    },
    "nbq.function.balance.v1": {
        "en": 'How is your balance? Any falls or dizziness lately?',
        "fa": 'تعادلت چطوره؟ این اواخر زمین خوردی یا سرگیجه داشتی؟',
        "ar": 'كيف حال توازنك؟ هل سقطت أو شعرت بدوار مؤخراً؟',
    },
    "nbq.function.cognition.v1": {
        "en": 'How are your focus and memory lately? Would reminders help you follow a plan?',
        "fa": 'تمرکز و حافظه\u200cت این روزها چطوره؟ یادآور برای دنبال کردن برنامه کمکت می\u200cکنه؟',
        "ar": 'كيف تركيزك وذاكرتك مؤخراً؟ هل تساعدك التذكيرات في اتباع الخطة؟',
    },
    "nbq.function.senses.v1": {
        "en": 'How are your vision and hearing? Anything that makes reading a plan or hearing reminders hard?',
        "fa": 'دید و شنوایی\u200cت چطوره؟ چیزی هست که خوندن برنامه یا شنیدن یادآور رو سخت کنه؟',
        "ar": 'كيف بصرك وسمعك؟ هل هناك ما يصعّب قراءة الخطة أو سماع التذكيرات؟',
    },
    "nbq.function.pain_fatigue.v1": {
        "en": 'How much do pain or tiredness affect your day?',
        "fa": 'درد یا خستگی چقدر روی روزت اثر می\u200cذاره؟',
        "ar": 'إلى أي مدى يؤثر الألم أو التعب على يومك؟',
    },
    "nbq.function.digestion.v1": {
        "en": 'How is your digestion? Are there foods that bother you?',
        "fa": 'هضم و گوارشت چطوره؟ غذایی هست که اذیتت کنه؟',
        "ar": 'كيف حال هضمك؟ هل هناك أطعمة تزعجك؟',
    },
    "nbq.function.glucose.v1": {
        "en": 'How do you keep your blood sugar or pressure in check? Has your care team given you a food plan?',
        "fa": 'قند یا فشارت رو چطور کنترل می\u200cکنی؟ تیم درمان برنامه\u200cی غذایی مشخصی بهت داده؟',
        "ar": 'كيف تضبط سكر الدم أو الضغط؟ هل أعطاك فريقك العلاجي خطة غذائية؟',
    },
    "nbq.function.appetite.v1": {
        "en": 'How is your appetite lately? Any change in weight or in how much you eat?',
        "fa": 'اشتهات این روزها چطوره؟ تو وزن یا مقدار غذا خوردنت تغییری بوده؟',
        "ar": 'كيف شهيتك مؤخراً؟ هل تغير وزنك أو كمية أكلك؟',
    },
    "nbq.function.general.v1": {
        "en": 'Has your condition affected eating, moving or breathing? If so, tell me briefly.',
        "fa": 'این بیماری روی غذا خوردن، حرکت یا نفس کشیدنت اثری گذاشته؟ اگه آره کوتاه بگو.',
        "ar": 'هل أثّر مرضك على الأكل أو الحركة أو التنفس؟ إن كان نعم فأخبرني باختصار.',
    },
    "nbq.sleep.bedtime.v1": {
        "en": "If you're open to it, what time do you usually go to bed?",
        "fa": "اگه دوست داری بگی، معمولاً چه ساعتی می‌خوابی؟",
        "ar": "إن رغبت، في أي وقت تنام عادة؟",
    },
    "nbq.sleep.wake_time.v1": {
        "en": "What time do you usually wake up?",
        "fa": "معمولاً چه ساعتی از خواب بیدار می‌شی؟",
        "ar": "في أي وقت تستيقظ عادةً؟",
    },
    "nbq.sleep.sleep_quality.v1": {
        "en": "How would you describe your sleep lately, if you'd like to share?",
        "fa": "این روزها خوابت چطوره؟ اگه دوست داری برام بگو.",
        "ar": "إن أحببت، كيف تصف جودة نومك مؤخراً؟",
    },
    "nbq.nutrition.food_habits.v1": {
        "en": "If helpful, what do your usual eating habits look like?",
        "fa": "عادت‌های غذایی‌ات معمولاً چطوره؟",
        "ar": "إن كان مفيداً، كيف تبدو عاداتك الغذائية المعتادة؟",
    },
    "nbq.activity.activity_level.v1": {
        "en": "How active are you on a typical day?",
        "fa": "تو یه روز معمولی چقدر فعالی؟",
        "ar": "ما مدى نشاطك في يوم عادي؟",
    },
    "nbq.activity.exercise_schedule.v1": {
        "en": "If you'd like, when do you usually exercise?",
        "fa": "معمولاً چه موقع ورزش می‌کنی؟",
        "ar": "إن رغبت، متى تمارس الرياضة عادة؟",
    },
    "nbq.general.interests.v1": {
        "en": (
            "If you feel like sharing: what would you like Sedi to help you with most from here on?"
        ),
        "fa": "دوست داری صدی بیشتر تو چه زمینه‌ای کمکت کنه؟",
        "ar": "بماذا تود أن يساعدك صدی أكثر من الآن؟",
    },
    "nbq.general.communication_style.v1": {
        "en": (
            "If you're open to it, do you prefer a direct style, a supportive "
            "conversational style, or something in between?"
        ),
        "fa": (
            "ترجیح می‌دی رک و مستقیم باشم، یا بیشتر همدلانه و گفت‌وگومحور، "
            "یا چیزی بین این دو؟"
        ),
        "ar": (
            "إن رغبت، هل تفضل أسلوباً مباشراً، أم أسلوباً حوارياً داعماً، "
            "أم شيئاً بينهما؟"
        ),
    },
    "nbq.general.listen_before_advice.v1": {
        "en": (
            "When something is bothering you, do you usually prefer that I "
            "listen first before suggesting solutions?"
        ),
        "fa": (
            "وقتی چیزی ناراحتت می‌کنه، معمولاً ترجیح می‌دی اول گوش کنم "
            "و بعد پیشنهاد بدم؟"
        ),
        "ar": (
            "عندما يزعجك أمر ما، هل تفضل عادة أن أستمع أولاً قبل اقتراح الحلول؟"
        ),
    },
    "nbq.general.response_length.v1": {
        "en": "Would you prefer brief answers, or a bit more detail?",
        "fa": "ترجیح می‌دی جواب‌ها کوتاه باشه یا کمی مفصل‌تر؟",
        "ar": "هل تفضل إجابات مختصرة أم أكثر تفصيلاً قليلاً؟",
    },
    "nbq.general.occupation.v1": {
        "en": "What kind of work do you do?",
        "fa": "شغلت چیه؟",
        "ar": "ما نوع عملك؟",
    },
    "nbq.contextual.work_schedule.v1": {
        "en": "If you're open to it, what does your work schedule usually look like?",
        "fa": "برنامه کاری‌ت معمولاً چطوره؟",
        "ar": "إن رغبت، كيف يبدو جدول عملك عادة؟",
    },
    "nbq.contextual.time_constraints.v1": {
        "en": "How much time do you usually have for this?",
        "fa": "معمولاً برای این کار چقدر وقت داری؟",
        "ar": "كم من الوقت يتوفر لديك عادة لهذا؟",
    },
    # CR-04F.2 confirmation templates ({field} substituted at render time).
    "nbq.confirm.stale.v1": {
        "en": "I may have an older value for your {field}. What should I use now?",
        "fa": (
            "ممکنه برای {field} یه مقدار قدیمی‌تر ازت داشته باشم. "
            "الان چی رو درست بدونم؟"
        ),
        "ar": "قد يكون لدي قيمة أقدم لـ {field} لديك. ماذا يجب أن أستخدم الآن؟",
    },
    "nbq.confirm.conflict.v1": {
        "en": (
            "I have conflicting information about your {field}. "
            "What should I use going forward?"
        ),
        "fa": (
            "دربارهٔ {field} دو جواب متفاوت ازت دارم. "
            "از این به بعد کدوم رو درست بدونم؟"
        ),
        "ar": (
            "لدي معلومات متعارضة حول {field} لديك. "
            "ماذا يجب أن أستخدم من الآن فصاعداً؟"
        ),
    },
}


def _localized(template_id: str, language: LanguageCode) -> str:
    block = _TEMPLATES[template_id]
    return block.get(language) or block["en"]


def _field_label(target_key: str, language: LanguageCode) -> str:
    block = _FIELD_LABELS.get(target_key) or {}
    return block.get(language) or block.get("en") or target_key.split(".", 1)[-1]


def _localized_confirmation(
    kind: str, target_key: str, language: LanguageCode
) -> str:
    template_id = (
        "nbq.confirm.conflict.v1" if kind == "conflict" else "nbq.confirm.stale.v1"
    )
    return _localized(template_id, language).format(
        field=_field_label(target_key, language)
    )


def _items_for_key(
    items: Sequence[ContextItem], target_key: str
) -> list[ContextItem]:
    return [i for i in items if i.canonical_key == target_key]


def _key_unavailable_for_discovery(
    items: Sequence[ContextItem], target_key: str
) -> bool:
    """True when the key is present, conflicted, denied, or stale (needs confirm)."""
    matched = _items_for_key(items, target_key)
    if not matched:
        return False
    for item in matched:
        if item.conflicted:
            return True
        if item.consent == "denied":
            return True
        if getattr(item, "freshness", None) == "stale":
            return True
        if item.active:
            return True
    return False


def _coverage_blocks_discovery(snapshot: ContextSnapshot, target_key: str) -> bool:
    """CR-04F.1: ask only MISSING; skip KNOWN/DENIED/CONFLICTED/STALE."""
    state = coverage_state_for_key(snapshot, target_key)
    if state is CoverageState.NOT_APPLICABLE:
        # Unregistered soft keys fall back to legacy presence gate.
        return _key_unavailable_for_discovery(snapshot.items, target_key)
    return state is not CoverageState.MISSING


def _norm_message(message: str) -> str:
    text = (message or "").strip().lower()
    text = text.replace("\u200c", "").replace("\u200d", "")
    return text


def detect_discovery_invitation(
    message: str, language: LanguageCode = "en"
) -> bool:
    """True when the user explicitly invites one optional discovery question."""
    text = _norm_message(message)
    if not text:
        return False
    lang = language if language in _DISCOVERY_INVITATION_CUES else "en"
    cues = _DISCOVERY_INVITATION_CUES.get(lang, _DISCOVERY_INVITATION_CUES["en"])
    # Also accept EN cues in any language (common bilingual phrasing).
    ordered = sorted(
        {*_DISCOVERY_INVITATION_CUES["en"], *cues},
        key=len,
        reverse=True,
    )
    return any(_cue_present(text, cue) for cue in ordered)


def _cue_present(text: str, cue: str) -> bool:
    needle = _norm_message(cue)
    if not needle:
        return False
    if " " in needle:
        return bool(
            re.search(
                rf"(?<!\w){re.escape(needle)}(?!\w)",
                text,
                flags=re.UNICODE,
            )
        )
    return bool(
        re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text, flags=re.UNICODE)
    )


def _message_relevant(message: str, cues: tuple[str, ...]) -> bool:
    text = _norm_message(message)
    if not text:
        return False
    ordered = sorted((c for c in cues if c), key=len, reverse=True)
    return any(_cue_present(text, c) for c in ordered)


def _confirmation_eligible(
    *,
    target_key: str,
    intent: IntentResult,
    message: str,
) -> bool:
    """Reuse existing intent/context rules for conflict/stale confirmation."""
    if target_key in TIER_C_NEVER_MISSING_DRIVEN:
        return False
    if target_key in TIER_A_TARGETS:
        return intent.intent_id is IntentId.GENERAL

    for cand in _CONTEXTUAL_CANDIDATES:
        if cand.target_key != target_key:
            continue
        if intent.intent_id not in cand.compatible_intents:
            return False
        return _message_relevant(message, cand.relevance_cues)

    allowed = _INTENT_CONFIRM_KEYS.get(intent.intent_id)
    if allowed is not None and target_key in allowed:
        return True
    return False


def _select_confirmation_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    message: str,
    state: CoverageState,
    kind: str,
) -> Optional[DiscoveryDirective]:
    """At most one eligible confirmation for CONFLICTED or STALE."""
    hits: list[str] = []
    for target_key in _CONFIRMATION_PRIORITY:
        if coverage_state_for_key(snapshot, target_key) is not state:
            continue
        if not _confirmation_eligible(
            target_key=target_key, intent=intent, message=message
        ):
            continue
        hits.append(target_key)
    if not hits:
        for target_key in sorted(REGISTERED_TARGETS):
            if target_key in _CONFIRMATION_PRIORITY_INDEX:
                continue
            if coverage_state_for_key(snapshot, target_key) is not state:
                continue
            if not _confirmation_eligible(
                target_key=target_key, intent=intent, message=message
            ):
                continue
            hits.append(target_key)
    if not hits:
        return None
    winner = hits[0]
    sensitivity = "high" if winner == "barriers.time_constraints" else "medium"
    priority = _CONFIRMATION_PRIORITY_INDEX.get(winner, 100)
    question_id = f"nbq.q.confirm.{kind}.{winner}.v1"
    return DiscoveryDirective(
        question_id=question_id,
        target_key=winner,
        localized_question=_localized_confirmation(kind, winner, language),
        sensitivity=sensitivity,  # type: ignore[arg-type]
        priority=priority,
    )


def _select_contextual_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    message: str,
    exclude_keys: frozenset[str] = frozenset(),
) -> Optional[DiscoveryDirective]:
    """Return at most one contextual directive when message relevance is true."""
    hits: list[_ContextualCandidate] = []
    for cand in _CONTEXTUAL_CANDIDATES:
        if cand.target_key in exclude_keys:
            continue
        if intent.intent_id not in cand.compatible_intents:
            continue
        if not _message_relevant(message, cand.relevance_cues):
            continue
        if _coverage_blocks_discovery(snapshot, cand.target_key):
            continue
        hits.append(cand)
    if not hits:
        return None
    hits.sort(key=lambda c: (c.priority, c.target_key))
    winner = hits[0]
    question_id = f"nbq.q.{intent.intent_id.value}.{winner.target_key}.v1"
    return DiscoveryDirective(
        question_id=question_id,
        target_key=winner.target_key,
        localized_question=_localized(winner.template_id, language),
        sensitivity=winner.sensitivity,  # type: ignore[arg-type]
        priority=winner.priority,
    )


def _plan_intake_steps(plan_domain: str, snapshot: ContextSnapshot) -> list[str]:
    """Ordered plan-intake target keys: goal, body-function domains of the user's conditions, then the
    domain-specific friendly questions (any condition is covered by the generic fallback domain)."""
    from backend.app.services.intelligence.condition_function_domains import (
        domains_for_conditions,
        target_key,
    )

    conditions = [
        str(i.structured_value or i.display_text or "")
        for i in snapshot.items
        if i.canonical_key.startswith("health.condition.") and i.active
    ]
    function_keys = [target_key(d) for d in domains_for_conditions(conditions)]
    if plan_domain == "activity":
        rest = ["intake.exercise_preferences", "intake.exercise_time", "intake.equipment"]
    else:
        rest = [
            "intake.allergies",
            "intake.food_preferences",
            "intake.budget",
            "intake.cooking_time",
            "intake.meal_times",
        ]
    return ["intake.goal", *function_keys, *rest]


def _select_function_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    plan_domain: Optional[str] = None,
    conditions_only: bool = False,
    exclude_keys: frozenset[str] = frozenset(),
) -> Optional[DiscoveryDirective]:
    """Stage 06 / B1 + B1.5-a: friendly plan intake before/while building a personalized plan.

    Asks the first unanswered step. `plan_domain` ("nutrition" | "activity") is set by the orchestrator for
    plan intents and while a plan-intake reply is being continued."""
    if plan_domain is None:
        if intent.intent_id is IntentId.NUTRITION:
            plan_domain = "nutrition"
        elif intent.intent_id is IntentId.ACTIVITY:
            plan_domain = "activity"
        else:
            return None
    for key in _plan_intake_steps(plan_domain, snapshot):
        if key in exclude_keys:
            continue  # answered this turn; the snapshot predates the answer (R-008: never ask twice)
        if conditions_only and not key.startswith("function."):
            continue  # the established soft question (food habits / activity level) keeps its place
        if _coverage_blocks_discovery(snapshot, key):
            continue
        if key.startswith("function."):
            template_id = f"nbq.function.{key.split('.', 1)[1]}.v1"
        elif key == "intake.goal":
            template_id = f"nbq.intake.goal_{'exercise' if plan_domain == 'activity' else 'nutrition'}.v1"
        else:
            template_id = f"nbq.intake.{key.split('.', 1)[1]}.v1"
        return DiscoveryDirective(
            question_id=f"nbq.q.plan_intake.{key}.v1",
            target_key=key,
            localized_question=_localized(template_id, language),
            sensitivity="high",  # type: ignore[arg-type]
            priority=5,
        )
    return None


def _select_tier_a_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    exclude_keys: frozenset[str] = frozenset(),
) -> Optional[DiscoveryDirective]:
    """CR-04F.1 — at most one safe missing Tier-A question (GENERAL only)."""
    if intent.intent_id is not IntentId.GENERAL:
        return None
    for target_key in TIER_A_GENERAL_PRIORITY:
        if target_key in exclude_keys:
            continue
        if not is_safe_missing_for_discovery(snapshot, target_key):
            continue
        meta = _TIER_A_TEMPLATE_BY_KEY.get(target_key)
        if meta is None:
            continue
        sensitivity, template_id, priority = meta
        question_id = f"nbq.q.{intent.intent_id.value}.{target_key}.v1"
        return DiscoveryDirective(
            question_id=question_id,
            target_key=target_key,
            localized_question=_localized(template_id, language),
            sensitivity=sensitivity,  # type: ignore[arg-type]
            priority=priority,
        )
    return None


def _select_invitation_directive(
    *,
    snapshot: ContextSnapshot,
    language: LanguageCode,
    exclude_keys: frozenset[str] | None = None,
) -> Optional[DiscoveryDirective]:
    """Q2/Q4 — invited discovery: primary missing + optional safe companion (max 2)."""
    excluded = exclude_keys or frozenset()
    for target_key in _INVITATION_SOFT_PRIORITY:
        if target_key in excluded:
            continue
        if not is_safe_missing_for_discovery(snapshot, target_key):
            continue
        meta = _INVITATION_TEMPLATE_BY_KEY.get(target_key)
        if meta is None:
            continue
        sensitivity, template_id, priority = meta
        question_id = f"nbq.q.invitation.{target_key}.v1"
        companion_key: Optional[str] = None
        companion_q: Optional[str] = None
        cand = _invited_companion_key(target_key)
        if (
            cand is not None
            and cand not in excluded
            and is_safe_missing_for_discovery(snapshot, cand)
        ):
            cmeta = _INVITATION_TEMPLATE_BY_KEY.get(cand)
            if cmeta is not None:
                companion_key = cand
                companion_q = _localized(cmeta[1], language)
                question_id = f"nbq.q.invitation.{target_key}+{cand}.v1"
        return DiscoveryDirective(
            question_id=question_id,
            target_key=target_key,
            localized_question=_localized(template_id, language),
            sensitivity=sensitivity,  # type: ignore[arg-type]
            priority=priority,
            companion_target_key=companion_key,
            companion_localized_question=companion_q,
        )
    return None


def _select_intent_soft_directive(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    language: LanguageCode,
    exclude_keys: frozenset[str] = frozenset(),
) -> Optional[DiscoveryDirective]:
    """Intent-specific soft candidates (sleep/nutrition/activity). GENERAL uses Tier-A."""
    if intent.intent_id is IntentId.GENERAL:
        # GENERAL soft list is Tier-A; already handled by _select_tier_a_directive.
        return None
    candidates = _SOFT_DISCOVERY_CANDIDATES.get(intent.intent_id)
    if not candidates:
        return None
    for target_key, sensitivity, template_id, priority in candidates:
        if target_key in exclude_keys:
            continue
        if _coverage_blocks_discovery(snapshot, target_key):
            continue
        question_id = f"nbq.q.{intent.intent_id.value}.{target_key}.v1"
        return DiscoveryDirective(
            question_id=question_id,
            target_key=target_key,
            localized_question=_localized(template_id, language),
            sensitivity=sensitivity,  # type: ignore[arg-type]
            priority=priority,
        )
    return None


def select_next_best_question(
    *,
    snapshot: ContextSnapshot,
    intent: IntentResult,
    readiness: ReadinessResult,
    language: LanguageCode,
    message: str = "",
    force_invitation: bool = False,
    exclude_keys: frozenset[str] | None = None,
    plan_domain: Optional[str] = None,
) -> Optional[DiscoveryDirective]:
    """
    Select soft-discovery / confirmation directive(s).

    Normal / confirmation / contextual / Tier-A: at most one target.
    Invited (phrase or force_invitation): primary + optional safe companion (max 2).

    Pure: reads only snapshot / intent / readiness / language / optional message.
    Hard I3 clarification always wins — caller must not invoke when
    readiness is not READY (also enforced here).
    """
    if readiness.status is not ReadinessStatus.READY:
        return None
    if intent.intent_id in _NBQ_SUPPRESSED_INTENTS:
        return None
    excluded = exclude_keys or frozenset()

    # A) CONFLICTED confirmation outranks missing discovery.
    conflict = _select_confirmation_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        message=message,
        state=CoverageState.CONFLICTED,
        kind="conflict",
    )
    if conflict is not None:
        return conflict

    # B) STALE confirmation outranks missing discovery.
    stale = _select_confirmation_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        message=message,
        state=CoverageState.STALE,
        kind="stale",
    )
    if stale is not None:
        return stale

    # B2) Stage 06 / B1.5-a: keep a plan intake going after an intake reply (explicit plan_domain).
    if plan_domain is not None:
        plan_q = _select_function_directive(
            snapshot=snapshot,
            intent=intent,
            language=language,
            plan_domain=plan_domain,
            exclude_keys=excluded,
        )
        if plan_q is not None:
            return plan_q

    # C) Q4 progressive continuation after invited ANSWER (before contextual).
    if force_invitation:
        continued = _select_invitation_directive(
            snapshot=snapshot, language=language, exclude_keys=excluded
        )
        if continued is not None:
            return continued

    # D) contextual relevance unchanged (time_constraints contextual-only).
    contextual = _select_contextual_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        message=message,
        exclude_keys=excluded,
    )
    if contextual is not None:
        return contextual

    # D2) Stage 06 / B1 + B1.5-a: friendly plan intake for plan intents (after contextual relevance).
    plan_q2 = _select_function_directive(
        snapshot=snapshot,
        intent=intent,
        language=language,
        conditions_only=True,
        exclude_keys=excluded,
    )
    if plan_q2 is not None:
        return plan_q2

    # E) Q2/Q4 explicit invitation phrase — primary (+ optional safe pair).
    if detect_discovery_invitation(message, language):
        invited = _select_invitation_directive(
            snapshot=snapshot, language=language, exclude_keys=excluded
        )
        if invited is not None:
            return invited

    # F) Tier-A progressive (GENERAL only) — always single.
    tier_a = _select_tier_a_directive(
        snapshot=snapshot, intent=intent, language=language, exclude_keys=excluded
    )
    if tier_a is not None:
        return tier_a

    soft = _select_intent_soft_directive(
        snapshot=snapshot, intent=intent, language=language, exclude_keys=excluded
    )
    if soft is not None:
        return soft
    # Stage 06 / B1.5-a: once the established soft question is answered, continue the friendly intake.
    return _select_function_directive(
        snapshot=snapshot, intent=intent, language=language, exclude_keys=excluded
    )
