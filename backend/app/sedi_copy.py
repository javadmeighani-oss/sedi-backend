# backend.app.sedi_copy
"""
Sedi copy catalog - the ONE place where Sedi's deterministic user-facing text lives (R-043).

What lives here: notification / reminder / follow-up / digest / opener / recap wording and the small labels
around them, in Persian (fa), Arabic (ar) and English (en).
What does NOT live here: LLM prompts and the persona (persona_policy_v1), the knowledge base, parsing regexes
and keyword lists, and log lines. Those are logic or model input, not text the user is shown.

Rules for adding or changing a text (enforced by backend/tests/test_sedi_copy_quality.py):
  * one stable, hierarchical key (``family.name[.part]``); keys are the interface - never rename one casually;
  * give all three languages, written for the language (not translated word by word);
  * the same ``{placeholders}`` in every language of a key;
  * Persian: half-space (ZWNJ) in می‌/نمی‌ and «‌ها», one Yeh/Kaf, brand «صدی» (never «سدی»); Arabic: Arabic letters;
  * Sedi's voice: warm, colloquial, friend-like (R-008/R-011) - no stiff «لطفاً ... کنید», no internal jargon;
  * a value may be a string, a tuple of VARIANTS (deterministically rotated by the caller), pairs or a small dict.

This module is a leaf: it imports nothing from the app (no import cycles, no I/O, no database).
"""

from __future__ import annotations

import copy as _copy
import re
from typing import Any, Dict, List, Optional

LANGS = ("fa", "ar", "en")
DEFAULT_LANG = "en"

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def norm_lang(raw: Optional[str], default: str = DEFAULT_LANG) -> str:
    """'fa-IR' / ' FA ' -> 'fa'; anything unsupported -> ``default``."""
    code = (raw or "").strip().lower().replace("_", "-").split("-")[0]
    return code if code in LANGS else default


def _entry(key: str) -> Dict[str, Any]:
    try:
        return CATALOG[key]
    except KeyError:
        raise KeyError(f"unknown copy key: {key}") from None


def by_lang(key: str) -> Dict[str, Any]:
    """The whole entry as ``{lang: value}`` (a private deep copy - callers may keep or mutate it)."""
    return _copy.deepcopy(_entry(key))


def nested_by_lang(prefix: str) -> Dict[str, Dict[str, Any]]:
    """``{sub: {lang: value}}`` for every key ``prefix.sub`` (catalog order)."""
    head = prefix + "."
    return {
        key[len(head):]: _copy.deepcopy(value)
        for key, value in CATALOG.items()
        if key.startswith(head) and "." not in key[len(head):]
    }


def raw(key: str, lang: Optional[str], default: str = DEFAULT_LANG) -> Any:
    """Value for ``lang``; falls back ``lang -> default -> en -> fa -> any`` (never raises for a missing language)."""
    entry = _entry(key)
    for code in (norm_lang(lang, default), default, "en", "fa"):
        if code in entry:
            return _copy.deepcopy(entry[code])
    return _copy.deepcopy(next(iter(entry.values())))


def variants(key: str, lang: Optional[str], default: str = DEFAULT_LANG) -> tuple:
    """The text variants of a key for ``lang`` (a single string becomes a one-item tuple)."""
    value = raw(key, lang, default)
    return (value,) if isinstance(value, str) else tuple(value)


def t(key: str, lang: Optional[str], *, pick: int = 0, default: str = DEFAULT_LANG, **fmt: Any) -> str:
    """One formatted text. ``pick`` selects a variant (modulo the count); a missing placeholder never breaks the caller."""
    options = variants(key, lang, default)
    text = options[pick % len(options)]
    if not fmt:
        return text
    try:
        return text.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return text


def placeholders(text: str) -> set:
    return set(_PLACEHOLDER.findall(text))


def has(key: str) -> bool:
    return key in CATALOG


def keys() -> List[str]:
    return list(CATALOG)


def iter_strings():
    """Yield ``(key, lang, text)`` for every string in the catalog (variants, pairs and small dicts flattened)."""

    def walk(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                yield from walk(item)

    for key, entry in CATALOG.items():
        for lang, value in entry.items():
            for text in walk(value):
                yield key, lang, text


# ----------------------------------------------------------------------------------------------------------------
# CATALOG
# ----------------------------------------------------------------------------------------------------------------
CATALOG: Dict[str, Dict[str, Any]] = {

    # ---- reminder --------------------------------------------------------------
    'reminder.event.title': {
        'fa': 'یادآوری از صدی',
        'ar': 'تذكير من صدی',
        'en': 'Reminder from Sedi',
    },
    'reminder.plan.nutrition': {
        'fa': (
            'وقت {slot}',
            '{name}{title}{when}. وقتی خوردی بگو «انجام شد» تا ثبت کنم.',
        ),
        'ar': (
            'وقت {slot}',
            '{name}{title}{when}. قل لي «تم» عندما تنتهي.',
        ),
        'en': (
            'Time for {slot}',
            '{name}{title}{when}. Tell me "done" when you\'ve had it.',
        ),
    },
    'reminder.plan.exercise': {
        'fa': (
            'وقت حرکت',
            '{name}{title}{when}. بعد از انجام بگو «انجام شد» یا اگه نشد بگو چرا.',
        ),
        'ar': (
            'وقت الحركة',
            '{name}{title}{when}. قل لي «تم» بعد الانتهاء أو السبب إن لم تستطع.',
        ),
        'en': (
            'Time to move',
            '{name}{title}{when}. Tell me "done" afterwards, or why if you couldn\'t.',
        ),
    },
    'reminder.plan_slot_word': {
        'fa': {
            'breakfast': 'صبحانه',
            'lunch': 'ناهار',
            'dinner': 'شام',
            'snack': 'میان\u200cوعده',
        },
        'ar': {
            'breakfast': 'الفطور',
            'lunch': 'الغداء',
            'dinner': 'العشاء',
            'snack': 'وجبة خفيفة',
        },
        'en': {
            'breakfast': 'breakfast',
            'lunch': 'lunch',
            'dinner': 'dinner',
            'snack': 'a snack',
        },
    },

    # ---- followup --------------------------------------------------------------
    'followup.initiative.mood': {
        'fa': '{who}امروز حالت چطوره؟ هر چی تو دلته بگو، من گوش می\u200cدم.',
        'ar': '{who}كيف حالك اليوم؟ قل ما في قلبك، أنا أُصغي.',
        'en': '{who}how are you today? Tell me whatever is on your heart, I am listening.',
    },
    'followup.initiative.suggestion': {
        'fa': '{who}راستی، اون پیشنهادی که دادم چطور پیش رفت؟ دلم می\u200cخواد بدونم.',
        'ar': '{who}كيف سار اقتراحي الذي قدّمته؟ أحب أن أعرف.',
        'en': '{who}how did that suggestion of mine go? I would love to know.',
    },
    'followup.initiative.health': {
        'fa': '{who}یه سر زدم ببینم امروز بدن و حالت چطوره؛ اگه خواستی با هم یه کار کوچیک برای مراقبت از خودت انجام بدیم.',
        'ar': '{who}مررت لأطمئن على جسدك ومزاجك اليوم؛ إن أردت نقوم بشيء صغير للعناية بك.',
        'en': '{who}I stopped by to see how your body and mood are today; if you like, let us do one small thing to look after you.',
    },
    # followup.general: item 0 = continue with the topic; item 1 = fa/ar: gentle wording without the topic (P7),
    # en: wording for a manually created general follow-up.
    'followup.general': {
        'fa': (
            '{who}گفته بودی بعداً درباره\u200cی «{topic}» ادامه بدیم. الان وقت داری؟',
            '{who}دلم خواست ادامه\u200cی حرف\u200cهامون رو بگیریم. هر وقت وقت داشتی، من اینجام.',
        ),
        'ar': (
            '{who}طلبتَ أن نكمل لاحقاً حديثنا عن «{topic}». هل لديك وقت الآن؟',
            '{who}أحببت أن نكمل حديثنا. في أي وقت يناسبك، أنا هنا.',
        ),
        'en': (
            "{who}you asked to continue later about '{topic}'. Do you have time to talk now?",
            "{who}you asked to follow up later about '{topic}'. Do you have time now?",
        ),
    },

    'followup.post_event': {
        'fa': '{who}موعدت چطور پیش رفت؟ اگه خواستی درباره\u200cاش حرف بزنیم.',
        'ar': '{who}كيف سار موعدك؟ إن أردت نتحدث عنه.',
        'en': "{who}how did your appointment go? If you'd like, we can talk about it.",
    },

    # ---- weekly_review ---------------------------------------------------------
    'weekly_review.title.nutrition': {
        'fa': 'مرور هفته\u200cی برنامه\u200cی غذایی',
        'ar': 'مراجعة أسبوع الخطة الغذائية',
        'en': 'Your meal-plan week',
    },
    'weekly_review.title.exercise': {
        'fa': 'مرور هفته\u200cی ورزشت',
        'ar': 'مراجعة أسبوع التمرين',
        'en': 'Your exercise week',
    },

    # ---- motivation ------------------------------------------------------------
    'motivation.title': {
        'fa': {
            'workout_day': 'امروز روز حرکته',
            'comeback': 'من اینجام',
            'milestone': 'آفرین!',
        },
        'ar': {
            'workout_day': 'اليوم يوم حركة',
            'comeback': 'أنا هنا',
            'milestone': 'أحسنت!',
        },
        'en': {
            'workout_day': 'Today is a move day',
            'comeback': 'I am here',
            'milestone': 'Well done!',
        },
    },

    # ---- digest ----------------------------------------------------------------
    'digest.titles': {
        'fa': (
            'چک\u200cاین روزانه سلامتی',
            'پیگیری روزانه صدی',
            'امروز با صدی',
        ),
        'ar': (
            'متابعة الصحة اليومية',
            'تفقدك اليومي مع صدی',
            'اليوم مع صدی',
        ),
        'en': (
            'Daily wellness check-in',
            'Your daily Sedi check-in',
            'Today with Sedi',
        ),
    },
    'digest.general_checkin.pairs': {
        'fa': (
            (
                'صبح بخیر از صدی',
                'امروز چطوری عزیزم؟ دلم می\u200cخواست یه احوالی ازت بپرسم. هر وقت حال داشتی، با هم حرف بزنیم.',
            ),
            (
                'یه سر زدم',
                'فقط اومدم بگم کنارتم. امروز چه خبر؟ اگه دلت خواست، برام تعریف کن.',
            ),
            (
                'حال و روزت چطوره؟',
                'یادم افتاد ازت بپرسم امروز حالت چطوره. هر چی تو دلته بگو، من گوش می\u200cدم.',
            ),
            (
                'یه قدم کوچیک برای امروز',
                'امروز یه کار کوچیک برای خودت بکن؛ یه لیوان آب، چند نفس عمیق یا یه کم قدم\u200cزدن. اگه خواستی با هم برنامه\u200cاش رو بچینیم.',
            ),
            (
                'صدی اینجاست',
                'هر وقت دلت خواست حرف بزنی یا فقط یکی گوش بده، من اینجام. امروز چطور گذشت؟',
            ),
            (
                'مراقب خودت باش',
                'امیدوارم امروز بهت خوش بگذره. اگه چیزی ناراحتت کرده یا خسته\u200cای، بگو تا با هم ببینیم چی کمکت می\u200cکنه.',
            ),
        ),
        'ar': (
            (
                'صباح الخير من صدی',
                'كيف حالك اليوم؟ أحببت أن أطمئن عليك. متى ما رغبت، لنتحدث معاً.',
            ),
            (
                'مررتُ لأطمئن',
                'أردت فقط أن أقول إني بجانبك. احكِ لي كيف كان يومك إن شئت.',
            ),
            (
                'كيف حالك فعلاً؟',
                'تساءلتُ كيف تشعر اليوم. قل لي ما في قلبك، أنا أُصغي.',
            ),
            (
                'خطوة صغيرة اليوم',
                'افعل شيئاً صغيراً لنفسك اليوم: كوب ماء أو بعض الأنفاس العميقة أو مشياً قصيراً. هل نخطط لذلك معاً؟',
            ),
            (
                'صدی هنا',
                'متى أردت أن تتحدث أو تجد من يُصغي، أنا هنا. كيف مرّ يومك؟',
            ),
            (
                'اعتنِ بنفسك',
                'أتمنى أن يكون يومك لطيفاً. إن كان شيء يضايقك أو كنت متعباً، أخبرني لنرى ما يساعدك.',
            ),
        ),
        'en': (
            (
                'Good morning from Sedi',
                "How is your day going? I wanted to check in on you. Whenever you feel like it, let's talk.",
            ),
            (
                'Just dropping by',
                "I only wanted to say I'm right here with you. Tell me about your day if you like.",
            ),
            (
                'How are you really?',
                "I wondered how you're feeling today. Tell me whatever is on your heart, I'm listening.",
            ),
            (
                'One small step today',
                'Do one small thing for yourself today: a glass of water, a few deep breaths or a short walk. Want to plan it together?',
            ),
            (
                'Sedi is here',
                "Whenever you want to talk, or just have someone listen, I'm here. How did today go?",
            ),
            (
                'Take care of you',
                "I hope today is kind to you. If something is bothering you or you're tired, tell me and let's see what helps.",
            ),
        ),
    },
    'digest.no_data.bodies': {
        'fa': (
            'امروز هنوز خبر تازه\u200cای از دستگاهت نرسیده. اشکالی نداره؛ هر وقت دوست داشتی بیا با هم حرف بزنیم.',
            'هنوز داده\u200cی کافی برای یه جمع\u200cبندی کامل از امروزت ندارم. ولی من اینجام، اگه خواستی حرف بزنیم.',
            'تصویر امروز هنوز کامل نیست. هر وقت دلت خواست، یه چک\u200cاین آرام کنارتم.',
        ),
        'ar': (
            'لم تصلني قراءات جديدة من جهازك اليوم. لا بأس، متى أحببت لنتحدث.',
            'لا أملك بيانات كافية لصورة كاملة عن يومك بعد، لكني هنا متى أردت أن نتحدث.',
            'صورة اليوم لم تكتمل بعد. متى شئت أنا بجانبك لتفقد لطيف.',
        ),
        'en': (
            "No fresh readings from your device yet today. That's okay. Whenever you like, let's just talk.",
            "I don't have enough data for a full picture of today yet, but I'm here whenever you want to talk.",
            "Today's picture isn't complete yet. Whenever you feel like it, I'm here for a gentle check-in.",
        ),
    },
    'digest.safety.bodies': {
        'fa': (
            'یه موضوع مربوط به سلامتت هست که می\u200cخوام آروم باهات مرورش کنم. بیا با هم ببینیم.',
            'امروز یه چک\u200cاین ایمنی برات دارم؛ نگران نباش، فقط می\u200cخوام مطمئن بشم حالت خوبه. بیا حرف بزنیم.',
        ),
        'ar': (
            'هناك تحديث متعلق بالسلامة بانتظارك. افتح صدی لمراجعته بهدوء.',
            'لدى صدی تفقد سلامة لك اليوم. اضغط للمتابعة في المحادثة.',
        ),
        'en': (
            'There is a safety-related update waiting for you. Open Sedi to review it calmly.',
            'Sedi has a safety check-in for you today. Tap to continue in chat.',
        ),
    },
    'digest.i9_sufficient.bodies': {
        'fa': (
            'دادهٔ مشاهده\u200cشدهٔ دستگاه برای بازهٔ امروز دریافت شد. برای چک\u200cاین کوتاه صدی را باز کن.',
            'مشاهدات اخیر دستگاه در دسترس است. برای مرور محدود روزانه در صدی ادامه بده.',
        ),
        'ar': (
            'تم استلام بيانات الجهاز المرصودة لنافذة اليوم. افتح صدی لتفقد واقعي قصير.',
            'ملاحظات جهازك الأخيرة متاحة. تابع في صدی لمراجعة يومية محدودة.',
        ),
        'en': (
            "Observed device data was received for today's window. Open Sedi for a short factual check-in.",
            'Your recent device observations are available. Continue in Sedi for a bounded daily review.',
        ),
    },
    'digest.i9_partial.bodies': {
        'fa': (
            'دادهٔ امروز ناقص است؛ مقایسهٔ کامل ممکن نیست. برای ادامه صدی را باز کن.',
            'پوشش مشاهده\u200cشده برای امروز جزئی است. صدی می\u200cتواند یک چک\u200cاین آرام کمک کند.',
        ),
        'ar': (
            'بيانات اليوم غير مكتملة، لذا المقارنة الكاملة غير متاحة. افتح صدی للمتابعة.',
            'التغطية المرصودة جزئية لليوم. يمكن لصدی المساعدة بتفقد لطيف.',
        ),
        'en': (
            "Today's available data is incomplete, so a full comparison is not available. Open Sedi to continue.",
            'Observed coverage is partial for today. Sedi can help with a gentle check-in.',
        ),
    },
    'digest.i9_stale.bodies': {
        'fa': (
            'دادهٔ مشاهده\u200cشده هست اما از حد انتظار امروز قدیمی\u200cتر است. برای چک\u200cاین کوتاه صدی را باز کن.',
            'آخرین خلاصه\u200cی دستگاه قدیمی\u200cتر از معمول است. هر وقت آماده بودی در صدی ادامه بده.',
        ),
        'ar': (
            'توجد بيانات مرصودة لكنها أقدم مما هو متوقع لليوم. افتح صدی لتفقد قصير.',
            'أحدث ملخص أقدم من المعتاد. تابع في صدی عندما تكون مستعدًا.',
        ),
        'en': (
            'Observed data exists but is older than expected for today. Open Sedi for a short check-in.',
            'The latest device summary is older than usual. Continue in Sedi when ready.',
        ),
    },
    'digest.i8.bodies': {
        'fa': (
            'یه کار از برنامه\u200cات برای امروز مونده. هر وقت آماده بودی، بیا با هم ادامه\u200cاش بدیم.',
            'یکی از قدم\u200cهای برنامه\u200cات منتظرته. من کنارتم؛ هر وقت خواستی شروع کنیم.',
        ),
        'ar': (
            'لديك عنصر خطة نشط لليوم. افتح صدی للمتابعة.',
            'إجراء حالي من خطتك بانتظارك. تابع في صدی عندما تكون مستعدًا.',
        ),
        'en': (
            'You have an active plan item for today. Open Sedi to continue with it.',
            'A current action from your plan is waiting. Continue in Sedi when ready.',
        ),
    },
    'digest.i6_i7.bodies': {
        'fa': (
            'یادم نرفته دنبال چی هستی. بیا امروز یه قدم کوچیک بهش نزدیک\u200cتر بشیم.',
            'یه فکر کوچیک برای امروزت دارم. هر وقت خواستی، بیا با هم ببینیمش.',
        ),
        'ar': (
            'ملاحظة قصيرة عن نمط الحياة أو الهدف جاهزة لتفقد يومي لطيف. افتح صدی للمتابعة.',
            'سياقك اليومي المسموح يقترح متابعة خفيفة. تابع في صدی.',
        ),
        'en': (
            'A short lifestyle or goal note is ready for a gentle daily check-in. Open Sedi to continue.',
            'Your permitted daily context suggests a light follow-up. Continue in Sedi.',
        ),
    },
    'digest.general.bodies': {
        'fa': (
            'صبح بخیر — یک چک\u200cاین روزانهٔ آرام از صدی هر وقت بخواهی آماده است.',
            'صدی برای یک سلام کوتاه روزانه اینجاست. هر وقت خواستی گفتگو را باز کن.',
            'یک لمس آرام برای امروز. هر وقت آماده بودی با صدی ادامه بده.',
        ),
        'ar': (
            'صباح الخير — تفقد يومي لطيف من صدی جاهز متى شئت.',
            'صدی هنا لسلام يومي قصير. افتح المحادثة متى أحببت.',
            'لمسة هادئة واحدة لليوم. تابع مع صدی عندما تكون مستعدًا.',
        ),
        'en': (
            'Good morning — a gentle daily check-in from Sedi is ready when you are.',
            'Sedi is here for a short daily hello. Open chat whenever you like.',
            'One calm touchpoint for today. Continue with Sedi when ready.',
        ),
    },
    'digest.plan_title.morning': {
        'fa': 'برنامه\u200cی امروزت',
        'ar': 'خطتك لليوم',
        'en': 'Your plan for today',
    },
    'digest.plan_title.evening': {
        'fa': 'مرور برنامه\u200cی امروز',
        'ar': 'مراجعة خطة اليوم',
        'en': "Today's plan review",
    },

    # ---- companion -------------------------------------------------------------
    'companion.engagement.pairs': {
        'fa': (
            (
                'سلام از صدی',
                '{p}امروز چطوری؟ دلم می\u200cخواست یه احوالی ازت بپرسم. هر وقت حال داشتی، با هم حرف بزنیم.',
            ),
            (
                'یه سر زدم',
                '{p}فقط اومدم بگم کنارتم. اگه دلت می\u200cخواد، برام تعریف کن امروز چه خبر.',
            ),
            (
                'حالت چطوره؟',
                '{p}حس کردم یه مدتیه ازت خبر ندارم. همه\u200cچیز خوبه؟ من همین\u200cجام.',
            ),
            (
                'صدی کنارته',
                '{p}هر وقت دلت خواست درد و دل کنی یا فقط یکی گوش بده، من اینجام.',
            ),
        ),
        'ar': (
            (
                'تحية من صدی',
                '{p}كيف حالك اليوم؟ أحببت أن أطمئن عليك. متى ما رغبت، لنتحدث معاً.',
            ),
            (
                'مررتُ لأطمئن',
                '{p}أردت فقط أن أقول إني بجانبك. إن شئت، احكِ لي كيف كان يومك.',
            ),
            (
                'كيف حالك؟',
                '{p}شعرتُ أنني لم أسمع منك منذ فترة. هل كل شيء بخير؟ أنا هنا.',
            ),
            (
                'صدی بجانبك',
                '{p}متى أردت أن تفضفض أو تجد من يُصغي، أنا هنا.',
            ),
        ),
        'en': (
            (
                'Hello from Sedi',
                "{p}how is your day going? I wanted to check in on you. Whenever you feel like it, let's talk.",
            ),
            (
                'Just dropping by',
                "{p}I only wanted to say I'm right here with you. Tell me about your day if you like.",
            ),
            (
                'How are you?',
                "{p}it's been a little while since I heard from you. Is everything okay? I'm here.",
            ),
            (
                'Sedi is with you',
                "{p}whenever you want to talk it out, or just have someone listen, I'm here.",
            ),
        ),
    },
    'companion.engagement_low.pairs': {
        'fa': (
            (
                'فکرم پیشته',
                '{p}این روزها شاید کمی سخت می\u200cگذره. اگه دوست داری درباره\u200cاش حرف بزنیم، من گوش می\u200cدم و کنارتم.',
            ),
        ),
        'ar': (
            (
                'أفكر بك',
                '{p}ربما تمرّ عليك أيام ثقيلة. إن أحببت أن نتحدث عنها، أنا أُصغي وبجانبك.',
            ),
        ),
        'en': (
            (
                'Thinking of you',
                "{p}these days may be a bit heavy. If you'd like to talk about it, I'm listening and I'm with you.",
            ),
        ),
    },
    'companion.engagement_topic.body': {
        'fa': '{p}آخرین بار درباره\u200cی {t} حرف می\u200cزدیم و فکرم پیشت بود. می\u200cخوای همون رو ادامه بدیم، یا یه موضوع دیگه تو ذهنته؟',
        'ar': '{p}آخر مرة تحدثنا عن {t} وكنتُ أفكر بك. هل تحب أن نكمل، أم عندك موضوع آخر؟',
        'en': '{p}last time we talked about {t} and you stayed on my mind. Want to pick it up again, or is something else on your mind?',
    },

    # ---- action ----------------------------------------------------------------
    'action.label.ACK_THANKS': {
        'fa': 'متوجه شدم، ممنون',
        'ar': 'فهمت، شكرًا',
        'en': 'Got it, thanks',
    },
    'action.label.NOT_NOW': {
        'fa': 'الان نیازی نیست',
        'ar': 'ليس الآن',
        'en': 'Not now',
    },
    'action.label.TALK_LATER': {
        'fa': 'بعداً صحبت می\u200cکنیم',
        'ar': 'نتحدث لاحقًا',
        'en': "Let's talk later",
    },
    'action.label.OPEN_CHAT': {
        'fa': 'صحبت کنیم',
        'ar': 'لنتحدث',
        'en': "Let's talk",
    },
    'action.label.like': {
        'fa': 'پسندیدم',
        'ar': 'أعجبني',
        'en': 'Like',
    },
    'action.label.dislike': {
        'fa': 'نپسندیدم',
        'ar': 'لم يعجبني',
        'en': 'Dislike',
    },
    'action.label.open_chat': {
        'fa': 'صحبت کنیم',
        'ar': 'لنتحدث مع صدی',
        'en': 'Talk to Sedi',
    },
    'action.label.done': {
        'fa': 'آره، انجام شد',
        'ar': 'تم',
        'en': 'Done',
    },
    'action.label.plan_not_done': {
        'fa': 'نشد',
        'ar': 'لم يتم',
        'en': 'Not done',
    },
    'action.label.later': {
        'fa': 'بعداً',
        'ar': 'لاحقًا',
        'en': 'Later',
    },

    # ---- reminder --------------------------------------------------------------
    'reminder.talk_title': {
        'fa': 'صحبت درباره\u200cی {t}',
        'ar': 'الحديث عن {t}',
        'en': 'talk about {t}',
    },
    'reminder.title_default.lab_test': {
        'fa': 'آزمایش خون',
        'ar': 'تحليل الدم',
        'en': 'Lab test',
    },
    'reminder.title_default.doctor_visit': {
        'fa': 'نوبت دکتر',
        'ar': 'موعد الطبيب',
        'en': 'Doctor visit',
    },
    'reminder.title_default.exam': {
        'fa': 'امتحان',
        'ar': 'اختبار',
        'en': 'Exam',
    },
    'reminder.title_default.work_meeting': {
        'fa': 'جلسه',
        'ar': 'اجتماع',
        'en': 'Meeting',
    },
    'reminder.title_default.deadline': {
        'fa': 'مهلت کار',
        'ar': 'موعد التسليم',
        'en': 'Deadline',
    },
    'reminder.title_default.other': {
        'fa': 'یادآوری',
        'ar': 'تذكير',
        'en': 'Reminder',
    },
    'reminder.answer_prefix': {
        'fa': 'یادم بنداز ',
        'ar': 'ذكرني ',
        'en': 'remind me ',
    },

    # ---- recap -----------------------------------------------------------------
    'recap.phrase_in_app.nutrition': {
        'fa': 'برنامه\u200cی غذایی و تغذیه\u200cات',
        'ar': 'تغذيتك وخطتك الغذائية',
        'en': 'your eating and meal plan',
    },
    'recap.phrase_in_app.exercise': {
        'fa': 'ورزش و تحرکت',
        'ar': 'الرياضة والحركة',
        'en': 'exercise and staying active',
    },
    'recap.phrase_in_app.sleep': {
        'fa': 'خوابت',
        'ar': 'نومك',
        'en': 'your sleep',
    },
    'recap.phrase_in_app.work': {
        'fa': 'کار و دغدغه\u200cهات',
        'ar': 'العمل وما يشغلك',
        'en': "work and what's on your plate",
    },
    'recap.phrase_in_app.family': {
        'fa': 'خانواده\u200cات',
        'ar': 'عائلتك',
        'en': 'your family',
    },
    'recap.phrase_in_app.hair': {
        'fa': 'مراقبت از موهات',
        'ar': 'العناية بشعرك',
        'en': 'taking care of your hair',
    },
    'recap.phrase_in_app.skin': {
        'fa': 'مراقبت از پوستت',
        'ar': 'العناية ببشرتك',
        'en': 'taking care of your skin',
    },
    'recap.phrase_in_app.weight': {
        'fa': 'وزن و تناسب اندامت',
        'ar': 'وزنك ولياقتك',
        'en': 'your weight and fitness',
    },
    'recap.phrase_in_app.feelings': {
        'fa': 'حال و روحیه\u200cات',
        'ar': 'مزاجك وحالك',
        'en': "how you've been feeling",
    },
    'recap.phrase_in_app.reminders': {
        'fa': 'یادآورها و اعلان\u200cهات',
        'ar': 'تذكيراتك وإشعاراتك',
        'en': 'your reminders and notifications',
    },
    'recap.phrase_in_app.tone': {
        'fa': 'لحن و سبک حرف زدنمون',
        'ar': 'أسلوب حديثنا',
        'en': 'how we talk to each other',
    },
    'recap.phrase_in_app.disease_generic': {
        'fa': 'موضوع سلامتت',
        'ar': 'موضوع صحي يهمك',
        'en': 'a health topic of yours',
    },
    'recap.phrase_lock.nutrition': {
        'fa': 'برنامه\u200cی غذایی و تغذیه\u200cات',
        'ar': 'تغذيتك وخطتك الغذائية',
        'en': 'your eating and meal plan',
    },
    'recap.phrase_lock.exercise': {
        'fa': 'ورزش و تحرکت',
        'ar': 'الرياضة والحركة',
        'en': 'exercise and staying active',
    },
    'recap.phrase_lock.sleep': {
        'fa': 'خوابت',
        'ar': 'نومك',
        'en': 'your sleep',
    },
    'recap.phrase_lock.work': {
        'fa': 'کار و دغدغه\u200cهات',
        'ar': 'العمل وما يشغلك',
        'en': "work and what's on your plate",
    },
    'recap.phrase_lock.hair': {
        'fa': 'مراقبت از موهات',
        'ar': 'العناية بشعرك',
        'en': 'taking care of your hair',
    },
    'recap.phrase_lock.skin': {
        'fa': 'مراقبت از پوستت',
        'ar': 'العناية ببشرتك',
        'en': 'taking care of your skin',
    },
    'recap.phrase_lock.reminders': {
        'fa': 'یادآورها و اعلان\u200cهات',
        'ar': 'تذكيراتك وإشعاراتك',
        'en': 'your reminders and notifications',
    },
    'recap.phrase_lock.disease': {
        'fa': 'موضوع سلامتت',
        'ar': 'موضوع صحي يهمك',
        'en': 'a health topic of yours',
    },

    # ---- session ---------------------------------------------------------------
    'session.intro': {
        'fa': 'سلام{name_part}، من صدی\u200cام؛ همراه سلامتت. با رعایت حریم خصوصی\u200cات گوش می\u200cدم، چیزهای مهم رو یادم می\u200cمونه و کنارتم تا کمکت کنم. الان چی برات مهم\u200cتره که روش تمرکز کنیم؟',
        'ar': 'مرحبًا{name_part}. أنا صدی، مرافقتك الصحية. أستمع وأحتفظ بما يهمك وفق إعدادات خصوصيتك، وأنا هنا لأساعدك على المتابعة. ما الأمر الأهم أو الأكثر فائدة للتركيز عليه الآن؟',
        'en': "Hello{name_part}. I'm Sedi, your personal health companion. I listen and remember what matters under your privacy settings, and I'm here to help you stay on track. What feels most important or helpful to focus on right now?",
    },
    'session.openers': {
        'fa': [
            '{hello} امروز حالت چطوره؟ هر چی تو ذهنته بگو، من گوش می\u200cدم.',
            '{hello} دلم می\u200cخواست احوالت رو بپرسم؛ امروز چه خبر؟',
        ],
        'ar': [
            '{hello} كيف حالك اليوم؟ مهما كان في بالك، أنا أُصغي إليك.',
            '{hello} أحببت أن أطمئن عليك. ما الجديد اليوم؟',
        ],
        'en': [
            "{hello} How is your day going? Whatever is on your mind, I'm listening.",
            "{hello} I wanted to check in on you. What's new today?",
        ],
    },

    # ---- inline sites (moved out of function bodies) --------------------
    'reminder.lead.now': {
        'fa': 'الان',
        'ar': 'الآن',
        'en': 'Now',
    },
    'notification.morning.title': {
        'fa': 'صبح بخیر',
        'ar': 'صباح الخير',
        'en': 'Good Morning',
    },
    'notification.morning.cta': {
        'fa': ' روز خوبی داشته باشی.',
        'ar': ' أتمنى لك يوماً جميلاً.',
        'en': ' Have a good day.',
    },
    'notification.health_alert.title': {
        'fa': 'هشدار سلامت',
        'ar': 'تنبيه صحي',
        'en': 'Health Alert',
    },
    'notification.health_alert.unusual': {
        'fa': 'یک قرائت غیرمعمول ثبت شد.',
        'ar': 'تم تسجيل قراءة غير عادية.',
        'en': 'An unusual reading was detected.',
    },
    'notification.health_alert.cta': {
        'fa': 'برای بررسی، صدی رو باز کن.',
        'ar': 'افتح التطبيق للمراجعة.',
        'en': 'Open Sedi to review.',
    },
    'notification.health_alert.emergency': {
        'fa': 'اگر وضعیت جدی است، به پزشک مراجعه کنید.',
        'ar': 'إذا كان الأمر عاجلاً، استشر طبيباً.',
        'en': 'If urgent, seek professional care.',
    },
    'engine.hint.sleep_low': {
        'fa': 'امشب بیشتر استراحت کن',
        'ar': 'احصل على مزيد من الراحة الليلة',
        'en': 'Try to get more rest tonight',
    },
    'engine.hint.sleep_ok': {
        'fa': 'خواب خوبی داشتی',
        'ar': 'كان نومك جيداً',
        'en': 'You had good sleep',
    },
    'engine.hint.water': {
        'fa': 'یادت نره آب بخوری',
        'ar': 'لا تنس شرب الماء',
        'en': 'Remember to drink water',
    },
    'engine.hint.activity': {
        'fa': 'فعالیت خوبی داشتی',
        'ar': 'كان نشاطك جيداً',
        'en': 'You had good activity',
    },
    'engine.title.morning_brief': {
        'fa': 'صبح بخیر',
        'ar': 'صباح الخير',
        'en': 'Good Morning',
    },
    'engine.title.connection_ping': {
        'fa': 'سلام',
        'ar': 'مرحباً',
        'en': 'Hello',
    },
    'engine.title.health_alert': {
        'fa': 'هشدار سلامت',
        'ar': 'تنبيه صحي',
        'en': 'Health Alert',
    },
    'engine.title.device_disconnected': {
        'fa': 'قطع اتصال دستگاه',
        'ar': 'انقطع الاتصال بالجهاز',
        'en': 'Device Disconnected',
    },
    'engine.default_body.health_alert': {
        'fa': 'هشدار سلامت ثبت شد. بهتره وضعیتت رو بررسی کنی.',
        'ar': 'تم اكتشاف تنبيه صحي. يرجى التحقق من قراءاتك.',
        'en': 'Health alert detected. Please review your readings.',
    },
    'engine.default_body.device_disconnected': {
        'fa': 'اتصال دستگاه قطع شده. دوباره وصلش کن.',
        'ar': 'فُقد اتصال الجهاز. يرجى إعادة توصيل جهازك.',
        'en': 'Device connection lost. Please reconnect your device.',
    },
    'engine.default_body.morning_brief': {
        'fa': 'صبح بخیر. روز خوبی داشته باشی.',
        'ar': 'صباح الخير. أتمنى لك يوماً سعيداً.',
        'en': 'Good morning. Have a wonderful day.',
    },
    'engine.default_body.connection_ping': {
        'fa': 'سلام. امیدوارم حالت خوب باشه.',
        'ar': 'مرحباً. أتمنى أن تكون بخير.',
        'en': "Hello. Hope you're doing well.",
    },
    'engine.default_body.companion_ping': {
        'fa': 'سلام، دلم برات تنگ شده. اگه دوست داری، بگو امروز چطوری 🌿',
        'ar': 'مرحباً، كنت أفكر بك. إذا أحببت، أخبرني كيف يومك 🌿',
        'en': "Hi, I was thinking of you. If you'd like, tell me how today is going 🌿",
    },
    'recap.aspect.prevention': {
        'fa': 'پیشگیری از {l}',
        'ar': 'الوقاية من {l}',
        'en': 'preventing {l}',
    },
    'recap.aspect.diet': {
        'fa': 'تغذیه\u200cی مناسب برای {l}',
        'ar': 'التغذية المناسبة مع {l}',
        'en': 'eating well with {l}',
    },
    'recap.aspect.exercise': {
        'fa': 'ورزش برای {l}',
        'ar': 'الرياضة مع {l}',
        'en': 'exercise with {l}',
    },
    'recap.aspect.medication': {
        'fa': 'داروهای {l}',
        'ar': 'أدوية {l}',
        'en': 'medication for {l}',
    },
    'recap.aspect.symptoms': {
        'fa': 'علائم {l}',
        'ar': 'أعراض {l}',
        'en': 'the symptoms of {l}',
    },
    'session.continuity': {
        'fa': '{hello} آخرین بار درباره\u200cی {topic} حرف می\u200cزدیم. می\u200cخوای همون رو ادامه بدیم، یا امروز یه موضوع دیگه تو ذهنته؟',
        'ar': '{hello} آخر مرة تحدثنا عن {topic}. هل تحب أن نكمل، أم عندك موضوع آخر اليوم؟',
        'en': '{hello} Last time we talked about {topic}. Want to pick that up again, or is something else on your mind today?',
    },
    'session.presence_continuation': {
        'fa': '{prefix}آخرین بار درباره\u200cی {topic} حرف می\u200cزدیم. می\u200cخوای همون رو ادامه بدیم، یا یه موضوع دیگه تو ذهنته؟',
        'ar': '{prefix}آخر مرة تحدثنا عن {topic}. هل تحب أن نكمل، أم عندك موضوع آخر؟',
        'en': '{prefix}last time we talked about {topic}. Want to pick that up again, or is something else on your mind?',
    },

    # ---- event reminder wording --------------------------------------------
    'reminder.lead.tomorrow': {
        'fa': 'فردا',
        'ar': 'غداً',
        'en': 'Tomorrow',
    },
    'reminder.lead.days': {
        'fa': '{n} روز دیگه',
        'ar': 'بعد {n} أيام',
        'en': 'In {n} days',
    },
    'reminder.lead.one_hour': {
        'fa': 'یه ساعت دیگه',
        'ar': 'بعد ساعة',
        'en': 'In 1 hour',
    },
    'reminder.lead.hours': {
        'fa': '{n} ساعت دیگه',
        'ar': 'بعد {n} ساعات',
        'en': 'In {n} hours',
    },
    'reminder.lead.minutes': {
        'fa': '{n} دقیقه دیگه',
        'ar': 'بعد {n} دقيقة',
        'en': 'In {n} minutes',
    },
    'reminder.event.generic': {
        'fa': '{lead} وقتِ «{label}»ه 🌿',
        'ar': '{lead} موعد «{label}» 🌿',
        'en': '{lead}: {label} 🌿',
    },
    'reminder.event.generic_nolabel': {
        'fa': '{lead} وقت یادآوری\u200cته 🌿',
        'ar': '{lead} موعد تذكيرك 🌿',
        'en': "{lead} it's time for your reminder 🌿",
    },
    'reminder.event.doctor': {
        'fa': '{lead} وقت نوبت دکترته 🌿',
        'ar': '{lead} موعد زيارة طبيبك 🌿',
        'en': '{lead}: your doctor visit 🌿',
    },
    'reminder.event.lab': {
        'fa': '{lead} وقت آزمایشته 🌿',
        'ar': '{lead} موعد تحليلك 🌿',
        'en': '{lead}: your lab test 🌿',
    },
    'reminder.event.medical': {
        'fa': '{lead} یه برنامه\u200cی پزشکی داری 🌿',
        'ar': '{lead} لديك موعد طبي 🌿',
        'en': '{lead}: you have a medical event 🌿',
    },

    # ---- addressing the user by name ---------------------------------------
    'address.plain': {
        'fa': '{name}، ',
        'ar': '{name}، ',
        'en': '{name}, ',
    },
    'address.followup': {
        'fa': '{name} جان، ',
        'ar': '{name}، ',
        'en': '{name}, ',
    },
    'address.initiative': {
        'fa': '{name} جان، ',
        'ar': '{name}، ',
        'en': '{name}, ',
    },

    # ---- follow-up wording -------------------------------------------------
    'followup.title.brand': {
        'fa': 'صدی',
        'ar': 'صدی',
        'en': 'Sedi',
    },
    'followup.title.post_event': {
        'fa': 'صدی',
        'ar': 'صدی',
        'en': 'Follow-up on your appointment',
    },
    'followup.title.general': {
        'fa': 'صدی',
        'ar': 'صدی',
        'en': 'Continuing our conversation',
    },
    'followup.care_checkin.body': {
        'fa': '{who}دلم خواست حالت رو بپرسم. هر وقت وقت داشتی بیا کمی با هم حرف بزنیم؛ من اینجام.',
        'ar': '{who}أحببت أن أطمئن عليك. تعال نتحدث قليلاً عندما يناسبك؛ أنا هنا.',
        'en': "{who}I wanted to check in on you. Come talk for a bit whenever you have time; I'm here.",
    },

    # ---- companion wording (renderer) --------------------------------------
    'address.title_only': {
        'fa': '{name} جان',
        'ar': 'يا {name}',
        'en': '{name}',
    },
    'address.companion_text': {
        'fa': '{name} جان، ',
        'ar': 'يا {name}، ',
        'en': 'Hey {name}, ',
    },
    'address.companion': {
        'fa': '{name} جان، ',
        'ar': 'يا {name}، ',
        'en': '{name}, ',
    },
    'companion.goals_hint': {
        'fa': 'یادم نرفته دنبال «{goal}» هستی؛ قدم\u200cهای کوچیک هم حساب می\u200cشه.',
        'ar': 'لم أنسَ أنك تسعى إلى «{goal}»؛ الخطوات الصغيرة تُحسب أيضاً.',
        'en': "I haven't forgotten you're working on {goal}; small steps count too.",
    },
    'notification.morning.greeting': {
        'fa': 'صبح بخیر {name}',
        'ar': 'صباح الخير {name}',
        'en': 'Good morning {name}',
    },

    # ---- fallback text (used when no template renders) ---------------------
    'fallback.morning.base': {
        'fa': 'صبح بخیر {name}',
        'ar': 'صباح الخير {name}',
        'en': 'Good morning {name}',
    },
    'fallback.morning.cta': {
        'fa': 'روز خوبی داشته باشی.',
        'ar': 'أتمنى لك يوماً جميلاً.',
        'en': 'Have a wonderful day.',
    },
    'fallback.joiner': {
        'fa': '، ',
        'ar': '، ',
        'en': ', ',
    },
    'fallback.hint.sleep_low': {
        'fa': 'امشب بیشتر استراحت کن',
        'ar': 'احصل على مزيد من الراحة الليلة',
        'en': 'try to get more rest tonight',
    },
    'fallback.hint.sleep_ok': {
        'fa': 'خواب خوبی داشتی',
        'ar': 'كان نومك جيداً',
        'en': 'you had good sleep',
    },
    'fallback.hint.water': {
        'fa': 'یادت نره آب بخوری',
        'ar': 'لا تنس شرب الماء',
        'en': 'remember to drink water',
    },
    'fallback.hint.activity': {
        'fa': 'فعالیت خوبی داشتی',
        'ar': 'كان نشاطك جيداً',
        'en': 'you had good activity',
    },
    'fallback.ping.activity': {
        'fa': 'حالت چطوره؟ یه کم حرکت هم حالت رو بهتر می\u200cکنه؛ اگه خواستی با هم برنامه\u200cاش رو بچینیم',
        'ar': 'كيف حالك؟ القليل من الحركة يحسّن مزاجك؛ إن شئت نخطط لذلك معاً',
        'en': 'how are you? A little movement can lift your mood; want to plan it together',
    },
    'fallback.ping.plain': {
        'fa': 'امروز چطوری؟ دلم می\u200cخواست یه احوالی ازت بپرسم. هر وقت حال داشتی، با هم حرف بزنیم',
        'ar': 'كيف حالك اليوم؟ أحببت أن أطمئن عليك. متى ما رغبت، لنتحدث معاً',
        'en': "how is your day? I wanted to check in on you. Whenever you feel like it, let's talk",
    },
    'fallback.health.base': {
        'fa': 'سلام {name}، یه نکته\u200cی مهم',
        'ar': 'مرحباً {name}، ملاحظة مهمة',
        'en': 'Hello {name}, an important note',
    },
    'fallback.health.reason.heart_rate_high': {
        'fa': 'ضربان قلبت بالاست',
        'ar': 'نبضك مرتفع',
        'en': 'your heart rate is elevated',
    },
    'fallback.health.reason.heart_rate_low': {
        'fa': 'ضربان قلبت پایینه',
        'ar': 'نبضك منخفض',
        'en': 'your heart rate is low',
    },
    'fallback.health.reason.low_spo2': {
        'fa': 'اکسیژن خونت پایینه',
        'ar': 'الأكسجين في دمك منخفض',
        'en': 'your blood oxygen is low',
    },
    'fallback.health.reason.temperature_high': {
        'fa': 'دمای بدنت بالاست',
        'ar': 'درجة حرارتك مرتفعة',
        'en': 'your temperature is elevated',
    },
    'fallback.health.reason.irregular': {
        'fa': 'یه تغییر در وضعیت سلامتت دیده شده',
        'ar': 'تم ملاحظة تغيير في حالتك الصحية',
        'en': 'a change in your health status was detected',
    },
    'fallback.health.check': {
        'fa': 'بهتره بررسی کنی',
        'ar': 'من الأفضل أن تتحقق',
        'en': 'You should check',
    },
    'fallback.health.check_status': {
        'fa': 'بهتره وضعیت سلامتت رو بررسی کنی',
        'ar': 'من الأفضل أن تتحقق من حالتك الصحية',
        'en': 'you should check your health status',
    },
    'fallback.device.disconnected': {
        'fa': 'سلام {name}، اتصال دستگاه ({device}) قطع شده. وقتی می\u200cتونی دوباره وصلش کن',
        'ar': 'مرحباً {name}، انقطع اتصال الجهاز ({device}). أعد الاتصال عندما تستطيع',
        'en': 'Hello {name}, your device ({device}) has been disconnected. Reconnect when you can',
    },
    'fallback.greeting': {
        'fa': 'سلام {name}، امیدوارم حالت خوب باشه',
        'ar': 'مرحباً {name}، أتمنى أن تكون بخير',
        'en': "Hello {name}, I hope you're doing well",
    },

    # ---- push templates (templates_v1) -------------------------------------
    'template.companion_daily_checkin_v1': {
        'fa': {
            'title': 'سلام از صدی',
            'message': 'امروز چطوری؟ دلم می\u200cخواست یه احوالی ازت بپرسم. هر وقت حال داشتی، با هم حرف بزنیم.',
        },
        'ar': {
            'title': 'تحية من صدی',
            'message': 'كيف حالك اليوم؟ أحببت أن أطمئن عليك. متى ما رغبت، لنتحدث معاً.',
        },
        'en': {
            'title': 'Hello from Sedi',
            'message': "How is your day going? I wanted to check in on you. Whenever you feel like it, let's talk.",
        },
    },
    'template.companion_encourage_move_v1': {
        'fa': {
            'title': 'تحرک',
            'message': 'یه قدم کوچیک بردار؛ بدنت ازت ممنون می\u200cشه. اگه خواستی من کنارتم.',
        },
        'ar': {
            'title': 'تحرك قليلاً',
            'message': 'خذ خطوة صغيرة عندما تستطيع.',
        },
        'en': {
            'title': 'Move a little',
            'message': 'Take a small step when you can.',
        },
    },
    'template.companion_breathing_break_v1': {
        'fa': {
            'title': 'وقت نفس',
            'message': 'یه دقیقه نفس عمیق بکش؛ آروم می\u200cشی. 🌬',
        },
        'ar': {
            'title': 'استراحة تنفس',
            'message': 'خذ دقيقة للتنفس بعمق؛ ستشعر بالهدوء. 🌬',
        },
        'en': {
            'title': 'Breathing break',
            'message': "Take a minute to breathe deeply; you'll feel calmer. 🌬",
        },
    },
    'template.health_alert_generic_v1': {
        'fa': {
            'title': 'هشدار سلامت',
            'message': 'یک قرائت غیرمعمول ثبت شد. برای بررسی، صدی رو باز کن.',
        },
        'ar': {
            'title': 'تنبيه صحي',
            'message': 'تم تسجيل قراءة غير معتادة. افتح صدی للمراجعة.',
        },
        'en': {
            'title': 'Health Alert',
            'message': 'An unusual reading was detected. Open Sedi to review.',
        },
    },

    # ---- session openers (a3_session_open) ---------------------------------
    'session.hello': {
        'fa': 'سلام{name_part} جان!',
        'ar': 'أهلاً{name_part}!',
        'en': 'Hi{name_part}!',
    },
    'session.hello_noname': {
        'fa': 'سلام!',
        'ar': 'أهلاً!',
        'en': 'Hi!',
    },
    'session.name_part': {
        'fa': ' {name}',
        'ar': ' {name}',
        'en': ', {name}',
    },
    'session.presence_generic': {
        'fa': '{prefix}حالت چطوره؟ می\u200cتونیم از همون\u200cجا که موندیم ادامه بدیم یا درباره\u200cی یه چیز تازه حرف بزنیم.',
        'ar': '{prefix}كيف حالك؟ يمكننا أن نتابع من حيث توقفنا أو نتحدث عن شيء جديد.',
        'en': '{prefix}how are you? We can pick up where we left off, or talk about something new.',
    },
    'session.daily_digest': {
        'fa': '{prefix}برای پیگیری روزانه صدی آماده\u200cای؟',
        'ar': '{prefix}هل أنت مستعد للمتابعة اليومية مع صدی؟',
        'en': '{prefix}Ready for your daily Sedi check-in?',
    },
    'session.origin_generic': {
        'fa': '{prefix}از اعلان صدی اومدی. می\u200cخوای از همین\u200cجا ادامه بدیم؟',
        'ar': '{prefix}فتحت هذا من إشعار صدی. كيف تريد المتابعة؟',
        'en': '{prefix}You opened this from a Sedi notification. How would you like to continue?',
    },
    'session.care_checkin': {
        'fa': '{who}خوشحالم که اومدی. دلم می\u200cخواست بدونم این روزها چطوری؛ هرچی تو دلته بگو، من گوش می\u200cدم.',
        'ar': '{who}سعيدة أنك جئت. أردت أن أعرف كيف حالك هذه الأيام؛ قل ما في قلبك، أنا أُصغي.',
        'en': "{who}I'm glad you came. I wanted to know how you've been these days; tell me whatever is on your heart, I'm listening.",
    },

    # ---- reminder confirmation and clarification ---------------------------
    'reminder.lead_text.day_one': {
        'fa': 'یه روز',
        'ar': 'يوم',
        'en': 'a day',
    },
    'reminder.lead_text.days': {
        'fa': '{n} روز',
        'ar': '{n} أيام',
        'en': '{n} days',
    },
    'reminder.lead_text.hour_one': {
        'fa': 'یه ساعت',
        'ar': 'ساعة',
        'en': 'an hour',
    },
    'reminder.lead_text.hours': {
        'fa': '{n} ساعت',
        'ar': '{n} ساعات',
        'en': '{n} hours',
    },
    'reminder.lead_text.minutes': {
        'fa': '{n} دقیقه',
        'ar': '{n} دقيقة',
        'en': '{n} minutes',
    },
    'reminder.confirm.with_lead': {
        'fa': 'حله، «{title}» برای {when} ثبت شد و {lead} قبلش یادت می\u200cندازم 🌿 توی «برنامه\u200cی من» هم می\u200cبینیش.',
        'ar': 'تم، سجّلتُ «{title}» لـ{when} وسأذكّرك قبله بـ{lead} 🌿 وستجده في «جدولي».',
        'en': "Done - “{title}” is set for {when} and I'll remind you {lead} before 🌿 You'll see it in My Schedule.",
    },
    'reminder.confirm.at_time': {
        'fa': 'حله، {when} یادت می\u200cندازم: «{title}» 🌿 توی «برنامه\u200cی من» هم می\u200cبینیش.',
        'ar': 'تم، سأذكّرك {when}: «{title}» 🌿 وستجده في «جدولي».',
        'en': "Done - I'll remind you {when}: “{title}” 🌿 You'll see it in My Schedule.",
    },
    'reminder.clarify.datetime': {
        'fa': 'کِی یادت بندازم؟ روز و ساعتش رو بگو، مثلاً «فردا ساعت ۱۰ صبح».',
        'ar': 'متى أذكّرك؟ أخبرني باليوم والساعة، مثل «غداً الساعة 10 صباحاً».',
        'en': 'When should I remind you? Please tell me the date and time, like “tomorrow at 10 am”.',
    },
    'reminder.clarify.past': {
        'fa': 'این ساعت امروز گذشته. چه ساعت یا روز دیگه\u200cای بذارم؟',
        'ar': 'هذا الوقت مضى اليوم. أي وقت أو يوم آخر أضع؟',
        'en': 'That time has already passed today. Which other time or day should I use?',
    },
    'reminder.clarify.timezone': {
        'fa': 'برای زمان\u200cبندی باید منطقه\u200cی زمانی\u200cات رو بدونم. می\u200cتونی توی پروفایل تنظیمش کنی.',
        'ar': 'أحتاج إلى منطقتك الزمنية قبل الجدولة. يرجى ضبطها في الملف الشخصي.',
        'en': 'I need your timezone before I can schedule this. Please set your timezone in Profile.',
    },
    'reminder.clarify.recurrence': {
        'fa': 'می\u200cتونم یادآوری رو هر روز یا هر هفته تکرار کنم، مثلاً «هر روز ساعت ۸ یادم بنداز آب بخورم». کدومشو بذارم؟',
        'ar': 'يمكنني تكرار التذكير كل يوم أو كل أسبوع، مثل «كل يوم الساعة 8 ذكّرني بشرب الماء». أيهما تريد؟',
        'en': 'I can repeat a reminder every day or every week, like “every day at 8 remind me to drink water”. Which one would you like?',
    },
    'reminder.clarify.title': {
        'fa': 'چه چیزی را در برنامهٔ شما ثبت کنم؟',
        'ar': 'ماذا أضع في جدولك؟',
        'en': 'What should I put on your schedule?',
    },
    'reminder.clarify_opening.datetime': {
        'fa': 'کِی یادت بندازم؟',
        'ar': 'متى أذكّرك؟',
        'en': 'When should I remind you?',
    },
    'reminder.clarify_opening.past': {
        'fa': 'این ساعت امروز گذشته.',
        'ar': 'هذا الوقت مضى اليوم.',
        'en': 'That time has already passed today.',
    },
    'reminder.clarify_opening.title': {
        'fa': 'چه چیزی را در برنامهٔ شما ثبت کنم؟',
        'ar': 'ماذا أضع في جدولك؟',
        'en': 'What should I put on your schedule?',
    },

    # ---- daily digest plan lines and engine fallback -----------------------
    'digest.plan.joiner': {
        'fa': '؛ ',
        'ar': '؛ ',
        'en': '; ',
    },
    'digest.plan.evening': {
        'fa': 'امروز {done} از {total} مورد برنامه\u200cات انجام شد. بقیه چطور پیش رفت؟ اگه انجام ندادی بگو چرا تا برنامه\u200cی فردا رو متناسب\u200cتر کنم.',
        'ar': 'اليوم أُنجز {done} من {total} من خطتك. كيف سار الباقي؟ إن تركت شيئاً فأخبرني لماذا لأناسب الغد.',
        'en': 'Today {done} of {total} plan items were done. How did the rest go? If you skipped any, tell me why so I can fit tomorrow better.',
    },
    'digest.plan.tail': {
        'fa': ' اولین\u200cها: {next}.',
        'ar': ' التالي: {next}.',
        'en': ' Up next: {next}.',
    },
    'digest.plan.morning': {
        'fa': 'امروز {total} مورد توی برنامه\u200cات داری.{tail} بعد از هر کدوم بگو «انجام شد».',
        'ar': 'لديك {total} عناصر في خطتك اليوم.{tail} قل لي «تم» بعد كل واحد.',
        'en': 'You have {total} plan items today.{tail} Tell me "done" after each one.',
    },
    'engine.health_alert.fallback_title': {
        'fa': 'هشدار سلامت',
        'ar': 'تنبيه صحي',
        'en': 'Health Alert',
    },
    'engine.health_alert.fallback_body': {
        'fa': 'هشدار سلامت ثبت شد.',
        'ar': 'تم تسجيل تنبيه صحي.',
        'en': 'A health alert was recorded.',
    },
}
