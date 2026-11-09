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
        'ar': 'تذكير من صدي',
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
        'fa': '{who}یه سر زدم ببینم امروز بدن و حالت چطوره؛ بیا با هم یه کار کوچیک برای مراقبت از خودت انجام بدیم.',
        'ar': '{who}مررت لأطمئن على جسدك ومزاجك اليوم؛ إن أردت نقوم بشيء صغير للعناية بك.',
        'en': '{who}I stopped by to see how your body and mood are today; let us do one small thing to look after you together.',
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
        'fa': '{who}موعدت چطور پیش رفت؟ برام تعریف کن.',
        'ar': '{who}كيف سار موعدك؟ إن أردت نتحدث عنه.',
        'en': "{who}how did your appointment go? Tell me about it.",
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

    # ---- weekly_report (R-074 step 5b: one weekly progress report from what the user marked) -----------------
    'weekly_report.summary.active': {
        'fa': 'این هفته {done} کار را انجام دادی و {not_done} مورد انجام نشد. از همین‌جا ادامه می‌دهیم.',
        'ar': 'هذا الأسبوع أنجزتَ {done} مهمة و{not_done} لم تُنجَز. نكمل من هنا.',
        'en': 'This week you did {done} things and {not_done} did not happen. We carry on from here.',
    },
    'weekly_report.summary.quiet': {
        'fa': 'این هفته هنوز کاری را علامت نزده‌ای. از امروز با یک کار کوچک شروع می‌کنیم.',
        'ar': 'لم تضع علامة على أي مهمة هذا الأسبوع بعد. نبدأ اليوم بمهمة صغيرة.',
        'en': 'You have not marked anything this week yet. We start today with one small task.',
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
            'تفقدك اليومي مع صدي',
            'اليوم مع صدي',
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
                'امروز یه کار کوچیک برای خودت بکن؛ یه لیوان آب، چند نفس عمیق یا یه کم قدم\u200cزدن. بیا با هم برنامه\u200cاش رو بچینیم.',
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
                'صباح الخير من صدي',
                'كيف حالك اليوم؟ أحببت أن أطمئن عليك. لنتحدث معاً.',
            ),
            (
                'مررتُ لأطمئن',
                'أردت فقط أن أقول إني بجانبك. احكِ لي كيف كان يومك.',
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
                'صدي هنا',
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
                "I only wanted to say I'm right here with you. Tell me about your day.",
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
            'هنوز داده\u200cی کافی برای یه جمع\u200cبندی کامل از امروزت ندارم. ولی من اینجام؛ بیا حرف بزنیم.',
            'تصویر امروز هنوز کامل نیست. هر وقت دلت خواست، یه چک\u200cاین آرام کنارتم.',
        ),
        'ar': (
            'لم تصلني قراءات جديدة من جهازك اليوم. لا بأس، متى أحببت لنتحدث.',
            'لا أملك بيانات كافية لصورة كاملة عن يومك بعد، لكني هنا متى أردت أن نتحدث.',
            'صورة اليوم لم تكتمل بعد. أنا بجانبك لتفقد لطيف.',
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
            'هناك تحديث متعلق بالسلامة بانتظارك. افتح صدي لمراجعته بهدوء.',
            'لدى صدي تفقد سلامة لك اليوم. اضغط للمتابعة في المحادثة.',
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
            'تم استلام بيانات الجهاز المرصودة لنافذة اليوم. افتح صدي لتفقد واقعي قصير.',
            'ملاحظات جهازك الأخيرة متاحة. تابع في صدي لمراجعة يومية محدودة.',
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
            'بيانات اليوم غير مكتملة، لذا المقارنة الكاملة غير متاحة. افتح صدي للمتابعة.',
            'التغطية المرصودة جزئية لليوم. يمكن لصدي المساعدة بتفقد لطيف.',
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
            'توجد بيانات مرصودة لكنها أقدم مما هو متوقع لليوم. افتح صدي لتفقد قصير.',
            'أحدث ملخص أقدم من المعتاد. تابع في صدي عندما تكون مستعدًا.',
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
            'لديك عنصر خطة نشط لليوم. افتح صدي للمتابعة.',
            'إجراء حالي من خطتك بانتظارك. تابع في صدي عندما تكون مستعدًا.',
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
            'ملاحظة قصيرة عن نمط الحياة أو الهدف جاهزة لتفقد يومي لطيف. افتح صدي للمتابعة.',
            'سياقك اليومي المسموح يقترح متابعة خفيفة. تابع في صدي.',
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
            'صباح الخير — تفقد يومي لطيف من صدي بانتظارك.',
            'صدي هنا لسلام يومي قصير. افتح المحادثة متى أحببت.',
            'لمسة هادئة واحدة لليوم. تابع مع صدي عندما تكون مستعدًا.',
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
                'تحية من صدي',
                '{p}كيف حالك اليوم؟ أحببت أن أطمئن عليك. لنتحدث معاً.',
            ),
            (
                'مررتُ لأطمئن',
                '{p}أردت فقط أن أقول إني بجانبك. احكِ لي كيف كان يومك.',
            ),
            (
                'كيف حالك؟',
                '{p}شعرتُ أنني لم أسمع منك منذ فترة. هل كل شيء بخير؟ أنا هنا.',
            ),
            (
                'صدي بجانبك',
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
                "{p}I only wanted to say I'm right here with you. Tell me about your day.",
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
                '{p}این روزها شاید کمی سخت می\u200cگذره. بیا درباره\u200cاش حرف بزنیم؛ من گوش می\u200cدم و کنارتم.',
            ),
        ),
        'ar': (
            (
                'أفكر بك',
                '{p}ربما تمرّ عليك أيام ثقيلة. لنتحدث عنها؛ أنا أُصغي وبجانبك.',
            ),
        ),
        'en': (
            (
                'Thinking of you',
                "{p}these days may be a bit heavy. Let's talk about it; I'm listening and I'm with you.",
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
        'fa': 'فعلاً نه',
        'ar': 'ليس الآن',
        'en': 'Not now',
    },
    'action.label.open_chat': {
        'fa': 'صحبت با صدی',
        'ar': 'لنتحدث مع صدي',
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
        'fa': 'سلام{name_part}، من صدی هستم، همراه و مشاور سلامت تو. وضعیت جسم و روانت را همراه با گفت‌وگوهایمان با دقت به خاطر می‌سپارم تا توصیه‌های من هر روز به شرایط تو نزدیک‌تر شود؛ برایت برنامه می‌نویسم و تا اجرای آن کنارت می‌مانم. هر چه بیشتر با من در میان بگذاری، دقیق‌تر کنارت خواهم بود. برای شروع بگو دقیقاً چه چیزی را می‌خواهی در سلامتت یا زندگی‌ات تغییر بدهی؟',
        'ar': 'مرحباً{name_part}. أنا صدي، رفيقتك ومستشارتك الصحية. أسجّل حال جسدك ونفسك مع أحاديثنا بدقة وأحفظها في الذاكرة لتقترب نصائحي كل يوم من وضعك؛ وأكتب لك خطة وأبقى بجانبك حتى تنفيذها. وكلما شاركتني أكثر كنت أقرب إليك وأدق. وللبدء، قل لي بالضبط ما الذي تريد تغييره في صحتك أو حياتك؟',
        'en': "Hello{name_part}. I'm Sedi, your health companion and adviser. I carefully keep the state of your body and mind in memory together with our conversations, so my advice grows closer to your situation every day; I write you a plan and stay beside you until it is done. The more you share with me, the more precisely I can be there for you. To begin, tell me exactly what you want to change in your health or your life?",
    },
    'session.openers': {
        'fa': ['{hello} می\u200cخواهم امروز با هم قدم مشخصی برداریم. دقیقاً چه چیزی را می\u200cخواهی در سلامتت یا زندگی\u200cات تغییر بدهی؟', '{hello} امروز بدن و روانت چطور است؟ از همان\u200cجا شروع کنیم.'],
        'ar': ['{hello} أريد أن نخطو اليوم خطوة محددة معاً. ما الذي تريد تغييره بالضبط في صحتك أو حياتك؟', '{hello} كيف حال جسدك ونفسك اليوم؟ لنبدأ من هنا.'],
        'en': ['{hello} I want us to take one concrete step today. What exactly do you want to change in your health or your life?', '{hello} How are your body and mind today? Let us start there.'],
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
        'fa': 'سلام، دلم برات تنگ شده. بگو امروز چطوری 🌿',
        'ar': 'مرحباً، كنت أفكر بك. أخبرني كيف يومك 🌿',
        'en': "Hi, I was thinking of you. Tell me how today is going 🌿",
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
        'fa': '{hello} آخرین بار درباره\u200cی {topic} صحبت کردیم. از آن زمان تا امروز در این مورد چه تغییری کرده است؟',
        'ar': '{hello} آخر مرة تحدثنا عن {topic}. ما الذي تغيّر في هذا الأمر منذ ذلك الحين؟',
        'en': '{hello} Last time we talked about {topic}. What has changed on that since then?',
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
        'fa': '{lead} یادآوری تو: «{label}» 🌿',
        'ar': '{lead} تذكيرك: «{label}» 🌿',
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
        'ar': 'صدي',
        'en': 'Sedi',
    },
    'followup.title.post_event': {
        'fa': 'صدی',
        'ar': 'صدي',
        'en': 'Follow-up on your appointment',
    },
    'followup.title.general': {
        'fa': 'صدی',
        'ar': 'صدي',
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
        'fa': 'حالت چطوره؟ یه کم حرکت هم حالت رو بهتر می\u200cکنه؛ بیا با هم برنامه\u200cاش رو بچینیم',
        'ar': 'كيف حالك؟ القليل من الحركة يحسّن مزاجك؛ لنخطط لذلك معاً',
        'en': 'how are you? A little movement can lift your mood; want to plan it together',
    },
    'fallback.ping.plain': {
        'fa': 'امروز چطوری؟ دلم می\u200cخواست یه احوالی ازت بپرسم. هر وقت حال داشتی، با هم حرف بزنیم',
        'ar': 'كيف حالك اليوم؟ أحببت أن أطمئن عليك. لنتحدث معاً',
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
            'title': 'تحية من صدي',
            'message': 'كيف حالك اليوم؟ أحببت أن أطمئن عليك. لنتحدث معاً.',
        },
        'en': {
            'title': 'Hello from Sedi',
            'message': "How is your day going? I wanted to check in on you. Whenever you feel like it, let's talk.",
        },
    },
    'template.companion_encourage_move_v1': {
        'fa': {
            'title': 'تحرک',
            'message': 'یه قدم کوچیک بردار؛ بدنت ازت ممنون می\u200cشه. من کنارتم.',
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
            'message': 'تم تسجيل قراءة غير معتادة. افتح صدي للمراجعة.',
        },
        'en': {
            'title': 'Health Alert',
            'message': 'An unusual reading was detected. Open Sedi to review.',
        },
    },

    # ---- session openers (a3_session_open) ---------------------------------
    'session.hello': {
        'fa': 'سلام{name_part}.',
        'ar': 'أهلاً{name_part}.',
        'en': 'Hello{name_part}.',
    },
    'session.hello_noname': {
        'fa': 'سلام.',
        'ar': 'أهلاً.',
        'en': 'Hello.',
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
        'fa': '{prefix}امروز چطوری؟ از حال و خوابت بگو یا از هر چیزی که دوست داری.',
        'ar': '{prefix}كيف حالك اليوم؟ حدثني عن حالك ونومك أو عن أي شيء تحب.',
        'en': "{prefix}How are you today? Tell me about your mood and sleep, or anything you like.",
    },
    'session.digest.general_checkin': {
        'fa': '{prefix}ممنون که اومدی. امروز حال بدن و حال دلت چطور بود؟',
        'ar': '{prefix}شكراً لأنك جئت. كيف كان جسدك وقلبك اليوم؟',
        'en': '{prefix}Thanks for coming. How were your body and your mood today?',
    },
    'session.digest.i8_action': {
        'fa': '{prefix}خوب شد اومدی. برنامه‌ی امروزت رو با هم مرور کنیم؟ بگو کدوم کار انجام شد.',
        'ar': '{prefix}جميل أنك جئت. هل نراجع خطة اليوم معاً؟ أخبرني أي بند أُنجز.',
        'en': "{prefix}Good that you came. Shall we go over today's plan? Tell me which items are done.",
    },
    'session.digest.i6_i7_context': {
        'fa': '{prefix}خوشحالم که اومدی. از همون جایی که صحبتمون مونده ادامه بدیم یا امروز درباره‌ی چیز دیگه‌ای حرف بزنیم؟',
        'ar': '{prefix}سعيدة أنك جئت. نكمل من حيث توقفنا أم نتحدث اليوم عن شيء آخر؟',
        'en': "{prefix}I'm glad you came. Shall we continue where we left off, or talk about something else today?",
    },
    'session.digest.safety': {
        'fa': '{prefix}ممنون که اومدی. الان حالت چطوره؟ من همین‌جا کنارتم.',
        'ar': '{prefix}شكراً لأنك جئت. كيف حالك الآن؟ أنا هنا بجانبك.',
        'en': "{prefix}Thanks for coming. How are you feeling right now? I'm right here with you.",
    },
    'session.digest.i9_observation': {
        'fa': '{prefix}ممنون که اومدی. امروز چه حسی داری و بدنت چطوره؟',
        'ar': '{prefix}شكراً لأنك جئت. كيف تشعر اليوم وكيف جسدك؟',
        'en': '{prefix}Thanks for coming. How do you feel today, and how is your body?',
    },
    'session.origin_generic': {
        'fa': '{prefix}ممنون که از پیام صدی اومدی. می‌خوای همون موضوع رو ادامه بدیم یا درباره‌ی چیز دیگه‌ای حرف بزنیم؟',
        'ar': '{prefix}شكراً لأنك جئت من رسالة صدي. هل نكمل الموضوع نفسه أم نتحدث عن شيء آخر؟',
        'en': '{prefix}Thanks for coming from my message. Shall we continue that topic, or talk about something else?',
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
    'reminder.when.now': {
        'fa': 'همین الان',
        'ar': 'الآن',
        'en': 'right now',
    },
    'reminder.confirm.at_time_nolabel': {
        'fa': 'انجام شد؛ {when} یادآور را برایت می‌فرستم 🌿 در «برنامه‌ی من» هم می‌بینی.',
        'ar': 'تم؛ أرسل لك التذكير {when} 🌿 وستجده في «جدولي».',
        'en': "Done - I'll send your reminder {when} 🌿 You'll see it in My Schedule.",
    },
    'reminder.confirm.at_time': {
        'fa': 'حله، {when} یادت می\u200cندازم: «{title}» 🌿 توی «برنامه\u200cی من» هم می\u200cبینیش.',
        'ar': 'تم، سأذكّرك {when}: «{title}» 🌿 وستجده في «جدولي».',
        'en': "Done - I'll remind you {when}: “{title}” 🌿 You'll see it in My Schedule.",
    },
    'doc.analysis.lab.head': {
        'fa': '{n} نتیجه‌ی آزمایش خوانده شد و {k} مورد در سند خارج از محدوده علامت خورده است.',
        'ar': 'قُرئت {n} نتيجة تحليل، و{k} منها خارج النطاق في المستند.',
        'en': '{n} test results were read, and {k} are marked out of range in the document.',
    },
    'doc.analysis.lab.none_flagged': {
        'fa': '{n} نتیجه‌ی آزمایش خوانده شد و سند هیچ موردی را خارج از محدوده علامت نزده است.',
        'ar': 'قُرئت {n} نتيجة تحليل ولم يشر المستند إلى أي قيمة خارج النطاق.',
        'en': '{n} test results were read and the document marks none as out of range.',
    },
    'doc.analysis.lab.flag_line': {
        'fa': '• {name}: {value} {unit} ({dir})',
        'ar': '• {name}: {value} {unit} ({dir})',
        'en': '• {name}: {value} {unit} ({dir})',
    },
    'doc.analysis.lab.trend_line': {
        'fa': '• {name}: از {prev} به {cur} {unit} رسیده ({dir} {date})',
        'ar': '• {name}: من {prev} إلى {cur} {unit} ({dir} {date})',
        'en': '• {name}: {prev} → {cur} {unit} ({dir} {date})',
    },
    'doc.analysis.dir.high': {'fa': 'بالا', 'ar': 'مرتفع', 'en': 'high'},
    'doc.analysis.dir.low': {'fa': 'پایین', 'ar': 'منخفض', 'en': 'low'},
    'doc.analysis.trend.up': {'fa': 'بالاتر از', 'ar': 'أعلى من', 'en': 'higher than'},
    'doc.analysis.trend.down': {'fa': 'پایین‌تر از', 'ar': 'أقل من', 'en': 'lower than'},
    'doc.analysis.trend.same': {'fa': 'تقریباً برابر با', 'ar': 'مقارب لـ', 'en': 'about the same as'},
    'doc.analysis.lab.saved_pending': {
        'fa': 'با تأیید تو، این نتیجه‌ها در تصویر کلی‌ات ثبت می‌شود و برنامه‌ی مراقبتت بر پایه‌ی آن‌ها تنظیم می‌شود.',
        'ar': 'بعد تأكيدك تُسجَّل هذه النتائج في صورتك العامة ويُبنى برنامج رعايتك عليها.',
        'en': 'Once you confirm, these results are recorded in your overall picture and your care plan is built on them.',
    },
    'doc.analysis.lab.saved': {
        'fa': 'این نتیجه‌ها در تصویر کلی‌ات ثبت شد و برنامه‌ی مراقبتت بر پایه‌ی آن‌ها تنظیم می‌شود.',
        'ar': 'سُجّلت هذه النتائج في صورتك العامة ويُبنى برنامج رعايتك عليها.',
        'en': 'These results are recorded in your overall picture and your care plan is built on them.',
    },
    'doc.analysis.rx': {
        'fa': 'در نسخه {n} دارو ثبت شده است: {names}.',
        'ar': 'تتضمن الوصفة {n} دواء: {names}.',
        'en': 'The prescription lists {n} medicines: {names}.',
    },
    'doc.analysis.rx.pending': {
        'fa': 'با تأیید تو، این داروها در تصویر کلی‌ات ثبت می‌شود تا پیگیری دارویی‌ات را با هم تنظیم کنیم.',
        'ar': 'بعد تأكيدك تُسجَّل هذه الأدوية في صورتك العامة لنضبط متابعة أدويتك معاً.',
        'en': 'Once you confirm, these medicines are recorded in your overall picture so we can set up your medication follow-up together.',
    },
    'doc.analysis.rx.saved': {
        'fa': 'این داروها در تصویر کلی‌ات ثبت شد؛ برای هر کدام بگو چه ساعتی مصرف می‌شود تا یادآور بگذارم.',
        'ar': 'سُجّلت هذه الأدوية في صورتك العامة؛ أخبرني بوقت كل دواء لأضع لك تذكيراً.',
        'en': 'These medicines are recorded in your overall picture; tell me when you take each one and I will set the reminders.',
    },
    'doc.analysis.next_visit': {
        'fa': 'توی مدرک، نوبت یا پیگیری بعدی روز {date} نوشته شده؛ بعد از تأیید مدرک، در برنامه‌ات ثبتش می‌کنم.',
        'ar': 'ورد في المستند موعد أو متابعة بتاريخ {date}؛ بعد تأكيد المستند أسجّله في جدولك.',
        'en': 'The document mentions the next visit or follow-up on {date}; once you confirm it, I add it to your schedule.',
    },
    'doc.analysis.next_visit.ask': {
        'fa': 'نوبت یا پیگیری بعدی {when} نوشته شده. در برنامه‌ات ثبتش کنم و یک ساعت قبلش یادآوری بفرستم؟',
        'ar': 'ورد موعد أو متابعة في {when}. أسجّله في جدولك وأرسل تذكيراً قبله بساعة؟',
        'en': 'The next visit or follow-up is on {when}. Shall I add it to your schedule with a reminder an hour before?',
    },
    'doc.analysis.next_visit.ask_noremind': {
        'fa': 'نوبت یا پیگیری بعدی {when} نوشته شده. در برنامه‌ات ثبتش کنم؟',
        'ar': 'ورد موعد أو متابعة في {when}. أسجّله في جدولك؟',
        'en': 'The next visit or follow-up is on {when}. Shall I add it to your schedule?',
    },
    'doc.analysis.next_visit.ask_notime': {
        'fa': 'نوبت یا پیگیری بعدی روز {date} نوشته شده، اما ساعتش را ندیدم. ساعت چند است؟ با همان ساعت در برنامه‌ات ثبتش می‌کنم.',
        'ar': 'ورد موعد أو متابعة بتاريخ {date} لكن الساعة غير مكتوبة. في أي ساعة؟ أسجّله في جدولك بالساعة التي تذكرها.',
        'en': 'The next visit or follow-up is on {date}, but the time is not written. What time is it? I add it to your schedule with that time.',
    },
    'doc.analysis.instructions': {
        'fa': 'دستورهای چاپ‌شده در مدرک: {items}.',
        'ar': 'التعليمات المكتوبة في المستند: {items}.',
        'en': 'Instructions printed on the document: {items}.',
    },
    'doc.next_visit.title': {
        'fa': 'نوبت پزشک',
        'ar': 'موعد الطبيب',
        'en': 'Doctor visit',
    },
    'previsit.head': {
        'fa': 'پیش از ویزیت، اینها را همراه ببر:',
        'ar': 'قبل الزيارة، خذ معك:',
        'en': 'Before the visit, bring:',
    },
    'previsit.bring.labs': {
        'fa': 'آخرین نتایج آزمایش‌هایت',
        'ar': 'آخر نتائج تحاليلك',
        'en': 'your latest lab results',
    },
    'previsit.bring.meds': {
        'fa': 'داروهایت (یا فهرستشان): {names}',
        'ar': 'أدويتك (أو قائمتها): {names}',
        'en': 'your medicines (or their list): {names}',
    },
    'previsit.bring.generic': {
        'fa': 'نسخه و گزارش‌های ویزیت‌های قبلی',
        'ar': 'الوصفات وتقارير الزيارات السابقة',
        'en': 'previous prescriptions and visit reports',
    },
    'previsit.say': {
        'fa': 'به پزشک بگو:',
        'ar': 'أخبر الطبيب:',
        'en': 'Tell the doctor:',
    },
    'previsit.ask.change': {
        'fa': 'از ویزیت قبلی تا حالا چه چیزی در بدن یا حالت عوض شده است',
        'ar': 'ما الذي تغيّر في جسمك أو حالتك منذ الزيارة السابقة',
        'en': 'what has changed in your body or mood since the last visit',
    },
    'previsit.ask.meds': {
        'fa': 'داروها را چطور مصرف می‌کنی و آیا عارضه‌ای دیده‌ای',
        'ar': 'كيف تتناول أدويتك وهل لاحظت أعراضاً جانبية',
        'en': 'how you take your medicines and whether you noticed side effects',
    },
    'previsit.ask.questions': {
        'fa': 'سؤال‌هایی را که داری از قبل بنویس تا در مطب فراموش نشود',
        'ar': 'اكتب أسئلتك مسبقاً حتى لا تنساها في العيادة',
        'en': 'write your questions down beforehand so none is forgotten',
    },
    'doc.analysis.other': {
        'fa': 'مدرک خوانده شد. با تأیید تو در تصویر کلی‌ات ثبت می‌شود.',
        'ar': 'قُرئ المستند. بعد تأكيدك يُسجَّل في صورتك العامة.',
        'en': 'The document was read. Once you confirm, it is recorded in your overall picture.',
    },
    'doc.analysis.other.saved': {
        'fa': 'مدرک در تصویر کلی‌ات ثبت شد.',
        'ar': 'سُجّل المستند في صورتك العامة.',
        'en': 'The document is recorded in your overall picture.',
    },
    'reminder.not_sent_say_when': {
        'fa': 'برای ارسال نوتیف زمان و موضوعش را بگو؛ مثلاً «الان نوتیف بفرست» یا «فردا ساعت ۱۰ یادم بینداز».',
        'ar': 'لإرسال إشعار أخبرني بالوقت والموضوع، مثل «أرسل لي إشعاراً الآن» أو «ذكّرني غداً الساعة 10».',
        'en': 'To send a notification, tell me the time and the topic, like “send me a notification now” or “remind me tomorrow at 10”.',
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
    'about.sedi': {
        'fa': 'سلام، من صدی هستم، همراه و مشاور سلامت تو. وضعیت جسم و روانت را همراه با گفت‌وگوهایمان با دقت به خاطر می‌سپارم و هر چه این تصویر کامل‌تر شود، توصیه‌های من به شرایط تو نزدیک‌تر و دقیق‌تر خواهد بود. هر موضوعی که برایت مهم است، از خواب و تغذیه تا درد و حال‌و‌روزت، با خیال آسوده و بی‌هیچ قضاوتی با من در میان بگذار.\n\nآنچه برایت انجام می‌دهم: آزمایش‌ها، نسخه‌ها و ویزیت‌هایت را می‌خوانم و در تصویر کلی سلامتت ثبت می‌کنم؛ برنامه‌ی غذایی و ورزشی متناسب با شرایطت می‌نویسم و تا اجرای آن کنارت می‌مانم؛ دارو و کارهای مهمت را یادآوری می‌کنم و نوتیف می‌فرستم (کافی است بگویی «فردا ساعت ۱۰ یادم بینداز»)؛ و برای نگرانی‌ها و فشارهای روانی، با روش‌های علمی و تمرین‌های عملی کنارت هستم. هر زمان لازم باشد، متخصص مناسب را هم برایت پیدا می‌کنم.\n\nبا گجت‌های هوشمند تخصصی صدی، علائم حیاتی تو را به‌طور پیوسته زیر نظر دارم، آن‌ها را با تصویر کلی سلامتت می‌سنجم و تغییرهای مهم را زودتر درمی‌یابم؛ همه‌ی این‌ها برای رسیدن تو به یک زندگی سالم و طولانی است.\n\nهدف من برای تو، یک زندگی سالم، آرام و طولانی است. برای شروع بگو دقیقاً چه چیزی را می‌خواهی در سلامتت یا زندگی‌ات تغییر بدهی؟',
        'ar': 'مرحباً، أنا صدي، رفيقتك ومستشارتك الصحية. أسجّل حال جسدك ونفسك مع أحاديثنا بدقة وأحفظها في الذاكرة، وكلما اكتملت هذه الصورة صارت نصائحي أدق وأقرب إلى وضعك. وأي أمر يهمك، من النوم والغذاء إلى الألم وحالك النفسية، تحدّث إليّ عنه بارتياح ودون أي حكم.\n\nوهذا ما أقوم به لأجلك: أقرأ تحاليلك ووصفاتك وزياراتك الطبية وأسجّلها في الصورة العامة لصحتك؛ أكتب لك خطة غذائية ورياضية تناسب ظروفك وأتابعها حتى تنفيذها؛ أرسل لك تذكيرات وإشعارات بأدويتك ومهامك المهمة (قل لي «ذكّرني غداً الساعة ١٠»)؛ وأمام القلق والضغوط النفسية أبقى بجانبك بأساليب علمية وتمارين عملية. ومتى لزم الأمر أجد لك المختص المناسب.\n\nبأجهزة صدي الذكية المتخصصة أراقب علاماتك الحيوية باستمرار وأقارنها بصورتك الصحية العامة وألاحظ التغيرات المهمة مبكراً؛ وكل ذلك لتصل إلى حياة صحية طويلة.\n\nهدفي لك حياة صحية هادئة وطويلة. وللبدء، ما الذي تريد تغييره بالضبط في صحتك أو حياتك؟',
        'en': "Hello, I'm Sedi, your health companion and adviser. I keep the state of your body and mind in memory together with our conversations, and the more complete that picture becomes, the closer and more precise my advice will be to your own situation. Whatever matters to you, from sleep and food to pain and how you are feeling, you can talk to me about it openly, without any judgement.\n\nHere is what I do for you: I read your tests, prescriptions and visit notes and record them in the overall picture of your health; I write a nutrition and exercise plan that fits your circumstances and follow it through to the end; I send reminders and notifications for your medicines and important tasks (just say «remind me tomorrow at 10»); and for worries and psychological strain I stay with you using proven methods and practical exercises. Whenever it is needed, I will also find a suitable specialist for you.\n\nWith Sedi's specialised smart gadgets I keep a continuous watch over your vital signs, weigh them against the overall picture of your health and notice important changes sooner; all of it so that you reach a healthy, long life.\n\nMy aim for you is a healthy, calm and long life. To begin, what exactly do you want to change in your health or your life?",
    },
    'about.domain.psychology': {
        'fa': 'در زمینه‌ی روان‌شناسی، این‌ها را برایت انجام می‌دهم:\n• حال، انرژی و خواب تو را در طول زمان دنبال می‌کنم و الگوهایش را نشانت می‌دهم؛ مثلاً در چه روزهایی و به چه دلیل افت می‌کنی.\n• برای اضطراب و استرس، تمرین‌های عملی می‌دهم: تنفس آرام، تمرین حضور ذهن و بازسازی افکار منفی.\n• برای بی‌حوصلگی و بی‌انگیزگی، به شیوه‌ی «فعال‌سازی رفتاری» کارهای کوچک و مشخصی برای هر روز تعیین می‌کنیم.\n• برای خواب، هم عادت‌ها را مرور می‌کنم و هم برنامه‌ی یک‌هفته‌ای می‌نویسم و پیگیری می‌کنم.\n• در هر زمان که نیاز داشته باشی، بدون قضاوت به تو گوش می‌دهم و سپس یک قدم مشخص پیشنهاد می‌کنم.\n• اگر موضوعی سنگین یا طولانی شد، متخصص مناسب را برایت پیدا می‌کنم.\n\nحالا چه چیزی بیش از همه ذهنت را درگیر کرده است؟',
        'ar': 'في مجال علم النفس أقوم بما يلي:\n• أتابع مزاجك وطاقتك ونومك عبر الزمن وأريك أنماطها؛ مثلاً في أي الأيام ولماذا تتراجع.\n• للقلق والتوتر أعطيك تمارين عملية: التنفس الهادئ، واليقظة الذهنية، وإعادة صياغة الأفكار السلبية.\n• لفتور الهمة وقلة الدافعية نعتمد «التنشيط السلوكي»: أعمال صغيرة ومحددة لكل يوم.\n• وللنوم أراجع عاداتك وأكتب لك برنامج أسبوع وأتابعه.\n• ومتى احتجت إلى من يصغي إليك أصغي دون أي حكم، ثم أقترح خطوة محددة.\n• وإذا كان الأمر ثقيلاً أو طويلاً أجد لك المختص المناسب.\n\nما الذي يشغل بالك أكثر الآن؟',
        'en': 'In psychology, this is what I do for you:\n• I follow your mood, energy and sleep over time and show you the patterns, for example on which days you dip and why.\n• For anxiety and stress I give practical exercises: slow breathing, mindfulness and reframing negative thoughts.\n• For low motivation we use behavioural activation: small, specific actions for each day.\n• For sleep I review your habits, write a one-week plan and follow it.\n• Whenever you need it, I listen without judgement and then suggest one clear step.\n• If the matter is heavy or lasting, I find a suitable specialist for you.\n\nWhat is on your mind the most right now?',
    },
    'about.domain.nutrition': {
        'fa': 'در زمینه‌ی تغذیه و رژیم غذایی:\n• نخست شرایط تو را می‌شناسم: آلرژی‌ها، بیماری‌ها، داروها، ذائقه، بودجه و زمان آشپزی.\n• بر همین پایه برنامه‌ی غذایی هفتگی می‌نویسم، با وعده‌ها و ساعت‌هایی که خودت تعیین می‌کنی.\n• برای غذاهایی که نمی‌خوری یا نباید بخوری، جایگزین مناسب پیشنهاد می‌دهم.\n• برای شرایطی مانند دیابت، فشار خون یا چربی خون، اصول تغذیه‌ی مناسب را توضیح می‌دهم.\n• اجرای برنامه را پیگیری می‌کنم و هفته‌ای یک‌بار با هم مرورش می‌کنیم.\n\nهدف تو از رژیم غذایی چیست؟',
        'ar': 'في مجال التغذية والنظام الغذائي:\n• أتعرّف أولاً على ظروفك: الحساسية والأمراض والأدوية والذوق والميزانية ووقت الطهي.\n• وعلى هذا الأساس أكتب لك برنامجاً غذائياً أسبوعياً بوجبات ومواعيد تحددها أنت.\n• أقترح بدائل مناسبة للأطعمة التي لا تتناولها أو لا يجوز لك تناولها.\n• ولحالات مثل السكري وضغط الدم ودهون الدم أشرح أسس التغذية المناسبة.\n• وأتابع تنفيذ البرنامج ونراجعه معاً مرة كل أسبوع.\n\nما هدفك من النظام الغذائي؟',
        'en': 'In nutrition and diet:\n• I first get to know your circumstances: allergies, conditions, medicines, taste, budget and cooking time.\n• On that basis I write a weekly meal plan with the meals and times you choose.\n• For foods you do not eat or must avoid, I suggest suitable swaps.\n• For conditions such as diabetes, high blood pressure or high cholesterol, I explain the principles of suitable nutrition.\n• I follow the plan through and we review it together once a week.\n\nWhat is your goal with your diet?',
    },
    'about.domain.exercise_pain': {
        'fa': 'در زمینه‌ی ورزش و دردهای عضلانی:\n• برنامه‌ی ورزشی متناسب با سن، توان، زمان و شرایط جسمی‌ات می‌نویسم و گام‌به‌گام پیشرفت می‌دهم.\n• برای کمردرد، گردن‌درد، دردهای زانو و شانه و کشیدگی عضله، علت‌های رایج، روش‌های مراقبت و حرکات مناسب را مرحله‌به‌مرحله توضیح می‌دهم.\n• علائمی را که نیاز به اقدام فوری دارند، به‌روشنی می‌گویم.\n• تمرین‌ها را پیگیری می‌کنم و با دیدن پیشرفتت، برنامه را تنظیم می‌کنم.\n\nاکنون کدام ناحیه یا کدام هدف برایت اولویت دارد؟',
        'ar': 'في مجال الرياضة وآلام العضلات:\n• أكتب لك برنامجاً رياضياً يناسب عمرك وقدرتك ووقتك وحالتك البدنية وأتقدم بك تدريجياً.\n• لآلام الظهر والرقبة والركبة والكتف وشدّ العضلات أشرح الأسباب الشائعة وطرق العناية والحركات المناسبة مرحلة بعد مرحلة.\n• وأبيّن بوضوح العلامات التي تستدعي تدخلاً فورياً.\n• وأتابع تمارينك وأعدّل البرنامج بحسب تقدمك.\n\nأي منطقة أو أي هدف هو الأهم لك الآن؟',
        'en': 'In exercise and muscle pain:\n• I write an exercise plan that fits your age, ability, time and physical condition, and progress it step by step.\n• For back pain, neck pain, knee and shoulder pain and muscle strain, I explain the common causes, the care methods and the suitable movements stage by stage.\n• I state clearly the signs that call for immediate action.\n• I follow your workouts and adjust the plan as you progress.\n\nWhich area or which goal is your priority now?',
    },
    'about.domain.sleep': {
        'fa': 'در زمینه‌ی خواب:\n• الگوی خواب تو را مرور می‌کنم: ساعت خوابیدن و بیدار شدن، بیدارشدن‌های شبانه، کیفیت خواب و عوامل اثرگذار.\n• برای امشب یک یا دو اقدام مشخص می‌دهم و برای یک هفته برنامه‌ی کامل همراه با یادداشت خواب می‌نویسم.\n• عادت‌هایی را که خواب را به هم می‌زنند، مانند کافئین، نور و صفحه‌ی نمایش، شام دیروقت و استرس، با تو مرور می‌کنم.\n• پیشرفت را پیگیری می‌کنم و برنامه را اصلاح می‌کنم.\n\nمشکل تو بیشتر در به خواب رفتن است یا در ماندن در خواب؟',
        'ar': 'في مجال النوم:\n• أراجع نمط نومك: موعد النوم والاستيقاظ والاستيقاظات الليلية وجودة النوم والعوامل المؤثرة.\n• أعطيك لهذه الليلة خطوة أو خطوتين محددتين، وأكتب لك لأسبوع برنامجاً كاملاً مع دفتر للنوم.\n• وأراجع معك العادات التي تفسد النوم كالكافيين والضوء والشاشات والعشاء المتأخر والتوتر.\n• وأتابع تقدمك وأعدّل البرنامج.\n\nهل تكمن مشكلتك أكثر في الدخول في النوم أم في البقاء نائماً؟',
        'en': 'In sleep:\n• I review your sleep pattern: bedtime and wake time, night-time waking, sleep quality and the factors that affect it.\n• I give you one or two clear steps for tonight and write a full one-week plan with a sleep diary.\n• I go through the habits that disturb sleep with you, such as caffeine, light and screens, late dinners and stress.\n• I follow your progress and adjust the plan.\n\nIs your difficulty more in falling asleep or in staying asleep?',
    },
    'about.domain.documents': {
        'fa': 'در زمینه‌ی آزمایش، نسخه و ویزیت:\n• عکس یا فایل آزمایش یا نسخه‌ات را می‌خوانم و به زبان ساده خلاصه می‌کنم: چه مواردی بالا یا پایین گزارش شده و نسبت به قبل چه تغییری کرده است.\n• پس از تأیید تو، نتیجه‌ها و داروها در تصویر کلی سلامتت ثبت می‌شود و در گفت‌وگوها و برنامه‌هایت لحاظ می‌شود.\n• پیش از ویزیت فهرست پرسش‌هایت را آماده می‌کنم و پس از آن می‌پرسم پزشک چه گفت و کارهای بعدی را ثبت و یادآوری می‌کنم.\n• برای مصرف منظم داروهایت یادآور می‌گذارم و مصرف را طبق تجویز پزشک با تو پیگیری می‌کنم.\n\nمدرکی داری که با هم ببینیم؟',
        'ar': 'في مجال التحاليل والوصفات والزيارات:\n• أقرأ صورة أو ملف تحليلك أو وصفتك وألخّصه بلغة بسيطة: ما القيم المرتفعة أو المنخفضة وكيف تغيّرت عن السابق.\n• وبعد تأكيدك تُسجَّل النتائج والأدوية في الصورة العامة لصحتك وتؤخذ في الحسبان في أحاديثنا وبرامجك.\n• قبل الزيارة أجهّز قائمة أسئلتك، وبعدها أسألك ماذا قال الطبيب وأسجّل الخطوات التالية وأذكّرك بها.\n• وأضع تذكيراً لتناول أدويتك بانتظام وأتابع ذلك معك وفق ما وصفه الطبيب.\n\nهل لديك مستند ننظر فيه معاً؟',
        'en': 'In tests, prescriptions and visits:\n• I read the photo or file of your test or prescription and summarise it in plain words: which values are reported high or low and how they have changed since before.\n• After you confirm, the results and medicines are recorded in the overall picture of your health and taken into account in our conversations and your plans.\n• Before a visit I prepare your list of questions, and afterwards I ask what the doctor said and record and remind you of the next steps.\n• I set reminders so you take your medicines regularly and follow that with you as your doctor prescribed.\n\nDo you have a document we can look at together?',
    },
    'about.domain.gadgets': {
        'fa': 'با گجت‌های هوشمند تخصصی صدی، علائم حیاتی تو را به‌طور پیوسته زیر نظر دارم، آن‌ها را با تصویر کلی سلامتت می‌سنجم و تغییرهای مهم را زودتر درمی‌یابم؛ همه‌ی این‌ها برای رسیدن تو به یک زندگی سالم و طولانی است.\n\nکدام موضوع سلامتت را همراه با این مراقبت پیوسته پیگیری کنیم؟',
        'ar': 'بأجهزة صدي الذكية المتخصصة أراقب علاماتك الحيوية باستمرار وأقارنها بصورتك الصحية العامة وألاحظ التغيرات المهمة مبكراً؛ وكل ذلك لتصل إلى حياة صحية طويلة.\n\nأي موضوع صحي نتابعه معاً مع هذه الرعاية المستمرة؟',
        'en': "With Sedi's specialised smart gadgets I keep a continuous watch over your vital signs, weigh them against the overall picture of your health and notice important changes sooner; all of it so that you reach a healthy, long life.\n\nWhich health subject shall we follow together with this continuous care?",
    },
    'about.domain.reminders': {
        'fa': 'در زمینه‌ی یادآور و نوتیف:\n• هر چیزی را که بگویی، با روز و ساعت دقیق، یادآوری می‌کنم؛ کافی است بگویی «فردا ساعت ۱۰ یادم بینداز».\n• برای داروها، ویزیت پزشک، آزمایش، جلسه‌ها و برنامه‌ی غذایی و ورزشی‌ات، یادآور یک‌باره یا تکرارشونده (هر روز یا روزهای انتخابی) می‌گذارم.\n• یادآورها را در «برنامه‌ی من» می‌بینی و می‌توانی ویرایش یا حذفشان کنی.\n• اگر کاری انجام نشد، با پیام‌های متفاوت و در ساعت‌های مناسب دوباره پیگیری می‌کنم و دلیلش را از تو می‌پرسم تا برنامه را با زندگی‌ات هماهنگ کنم.\n• هر نوتیف یک دکمه‌ی «صحبت با صدی» دارد.\n\nاولین یادآوری را برای چه کاری و چه ساعتی بگذارم؟',
        'ar': 'في مجال التذكيرات والإشعارات:\n• أذكّرك بأي شيء تطلبه في اليوم والساعة اللذين تحددهما؛ يكفي أن تقول «ذكّرني غداً الساعة ١٠».\n• أضع تذكيرات لأدويتك وزيارات الطبيب والتحاليل والاجتماعات وبرنامجك الغذائي والرياضي، مرة واحدة أو متكررة (يومياً أو في أيام تختارها).\n• تراها في «جدولي» ويمكنك تعديلها أو حذفها.\n• وإذا لم يُنجز أمر ما أتابعه برسائل مختلفة وفي أوقات مناسبة وأسألك عن السبب لأوائم البرنامج مع حياتك.\n• ولكل إشعار زر «التحدث مع صدي».\n\nلأي أمر وفي أي ساعة أضع أول تذكير؟',
        'en': 'In reminders and notifications:\n• I remind you of anything you ask, at the exact day and hour; just say «remind me tomorrow at 10».\n• For your medicines, doctor visits, tests, meetings and your meal and exercise plans, I set one-off or repeating reminders (every day or on chosen days).\n• You see them in My Schedule and can edit or delete them.\n• If something is not done, I follow up with different messages at suitable times and ask you why, so I can fit the plan to your life.\n• Every notification has a «Talk to Sedi» button.\n\nWhat should the first reminder be for, and at what time?',
    },
    'about.domain.diseases_care': {
        'fa': 'در زمینه‌ی بیماری‌ها و روش‌های مراقبت:\n• برای بیماری‌های رایج مانند دیابت، فشار خون، آسم، میگرن، ریفلاکس و پوکی استخوان، ماهیت بیماری و مراقبت روزانه‌ی مؤثر را به زبان ساده و مرحله‌به‌مرحله توضیح می‌دهم.\n• برنامه‌ی هفتگی شامل غذا، حرکت، خواب و پایش علائم می‌نویسم و اجرای آن را پیگیری می‌کنم.\n• می‌گویم چه چیزی را هر چند وقت یک‌بار اندازه بگیری و چه تغییری نشانه‌ی خطر است.\n• مصرف منظم داروهایت را پیگیری می‌کنم و تغییرهای حالت را در تصویر کلی سلامتت ثبت می‌کنم.\n• اگر موضوع نیاز به ارزیابی تخصصی داشت، متخصص مناسب را برایت پیدا می‌کنم.\n\nبیماری یا شرایط تو چیست تا از همان‌جا شروع کنیم؟',
        'ar': 'في مجال الأمراض وطرق الرعاية:\n• للأمراض الشائعة كالسكري وضغط الدم والربو والصداع النصفي والارتجاع وهشاشة العظام أشرح طبيعة المرض والرعاية اليومية الفعالة بلغة بسيطة ومرحلة بعد مرحلة.\n• وأكتب برنامجاً أسبوعياً يشمل الغذاء والحركة والنوم ومراقبة الأعراض وأتابع تنفيذه.\n• وأبيّن ما الذي تقيسه وكل كم من الوقت، وما التغيّر الذي يدل على الخطر.\n• وأتابع انتظامك في أدويتك وأسجّل تغيّر حالتك في صورتك الصحية العامة.\n• وإذا احتاج الأمر إلى تقييم متخصص أجد لك المختص المناسب.\n\nما مرضك أو حالتك لنبدأ منها؟',
        'en': 'In illnesses and care methods:\n• For common conditions such as diabetes, high blood pressure, asthma, migraine, reflux and osteoporosis, I explain the condition and the daily care that works, in plain words and step by step.\n• I write a weekly plan covering food, movement, sleep and symptom monitoring, and follow it through.\n• I tell you what to measure and how often, and which change is a sign of danger.\n• I follow your regular use of your medicines and record changes in your condition in the overall picture of your health.\n• If the matter needs a specialist assessment, I find a suitable specialist for you.\n\nWhat is your condition or situation, so we can start from there?',
    },
    'about.domain.elder_care': {
        'fa': 'در زمینه‌ی مراقبت از سالمند:\n• توان، خطرها و روال روزانه‌ی فرد سالمند را می‌شناسم و بر پایه‌ی آن برنامه می‌نویسم.\n• برای ایمنی خانه، پیشگیری از زمین‌خوردن، مصرف درست داروها، تغذیه و نوشیدن آب راهنمایی مشخص می‌دهم.\n• برای زوال عقل و فراموشی، روش‌های ارتباط، ایجاد روال ثابت و ایمن‌سازی محیط را توضیح می‌دهم.\n• برای مراقب هم، راه‌های حفظ توان و آرامش خودش را پیشنهاد می‌کنم.\n• علائمی را که نیاز به اقدام فوری دارند، به‌روشنی می‌گویم.\n\nسالمند چه کسی است و بیشتر چه چیزی نگرانت می‌کند؟',
        'ar': 'في مجال رعاية كبار السن:\n• أتعرّف على قدرة المسن ومخاطره وروتينه اليومي وأكتب برنامجاً على هذا الأساس.\n• وأعطيك إرشادات محددة لأمان المنزل والوقاية من السقوط وتناول الأدوية بشكل صحيح والتغذية وشرب الماء.\n• ولمرض الخرف والنسيان أشرح أساليب التواصل وتثبيت الروتين وتأمين المكان.\n• وللقائم على الرعاية أقترح طرقاً للحفاظ على طاقته وهدوئه.\n• وأبيّن بوضوح العلامات التي تستدعي تدخلاً فورياً.\n\nمن هو المسن وما الذي يقلقك أكثر؟',
        'en': 'In caring for an older person:\n• I get to know their ability, risks and daily routine and write a plan on that basis.\n• I give specific guidance on safety at home, preventing falls, taking medicines correctly, nutrition and drinking enough water.\n• For dementia and forgetfulness, I explain ways of communicating, keeping a steady routine and making the surroundings safe.\n• For the carer as well, I suggest ways to keep up their own strength and calm.\n• I state clearly the signs that call for immediate action.\n\nWho is the older person, and what worries you most?',
    },
    'about.domain.memory': {
        'fa': 'در زمینه‌ی حافظه و تصویر کلی سلامتت:\n• گفت‌وگوهایمان را، با اجازه‌ی تو، کامل نگه می‌دارم تا هر زمان لازم شد، جزئیات گذشته را به یاد بیاورم.\n• خواب، تغذیه، حال روحی، دردها، داروها، آزمایش‌ها و رویدادهای مهم زندگی‌ات را در کوتاه‌مدت، میان‌مدت و بلندمدت ثبت می‌کنم.\n• کارهایی را که انجام می‌دهی، مانند مصرف دارو یا ورزش، هم ثبت می‌کنم و در توصیه‌هایم لحاظ می‌کنم.\n• هر چه ثبت شده را می‌توانی ببینی، اصلاح کنی یا حذف کنی؛ اختیار آن با توست.\n\nکدام بخش از تصویر سلامتت را با هم مرور کنیم؟',
        'ar': 'في مجال الذاكرة وصورتك الصحية العامة:\n• أحفظ أحاديثنا كاملة، بإذنك، لأتذكر تفاصيل الماضي كلما لزم.\n• وأسجّل نومك وغذاءك وحالتك النفسية وآلامك وأدويتك وتحاليلك وأحداث حياتك المهمة على المدى القصير والمتوسط والطويل.\n• وأسجّل ما تنجزه أيضاً كتناول الدواء أو الرياضة وآخذه في الحسبان في نصائحي.\n• ويمكنك أن ترى كل ما سُجّل وتصحّحه أو تحذفه؛ فالقرار لك.\n\nأي جزء من صورتك الصحية نراجعه معاً؟',
        'en': 'In memory and the overall picture of your health:\n• With your permission, I keep our conversations whole so I can recall past details whenever needed.\n• I record your sleep, food, mood, pains, medicines, tests and important life events over the short, medium and long term.\n• I also record what you do, such as taking medicine or exercising, and take it into account in my advice.\n• You can see everything that is recorded and correct or delete it; the decision is yours.\n\nWhich part of the picture of your health shall we go over together?',
    },
    'about.domain.specialist': {
        'fa': 'در زمینه‌ی پیدا کردن متخصص:\n• بر پایه‌ی مشکل و شهر تو، متخصص مناسب را از میان پزشکان و مراکز درمانی پیدا می‌کنم.\n• نوع متخصص را توضیح می‌دهم تا بدانی برای چه موضوعی به چه کسی مراجعه کنی.\n• پیش از مراجعه، فهرست پرسش‌ها و مدارک لازم را آماده می‌کنم و پس از آن، نتیجه‌ی ویزیت را با تو ثبت و پیگیری می‌کنم.\n• نوبت و یادآور ویزیت را هم برایت می‌گذارم.\n\nبرای چه مشکلی و در کدام شهر متخصص لازم داری؟',
        'ar': 'في مجال إيجاد المختص:\n• أجد لك المختص المناسب بين الأطباء والمراكز العلاجية بحسب مشكلتك ومدينتك.\n• وأشرح نوع المختص لتعرف إلى من تراجع في كل موضوع.\n• وقبل المراجعة أجهّز قائمة الأسئلة والمستندات اللازمة، وبعدها أسجّل نتيجة الزيارة وأتابعها معك.\n• وأضع لك تذكيراً بموعد الزيارة.\n\nلأي مشكلة وفي أي مدينة تحتاج مختصاً؟',
        'en': 'In finding a specialist:\n• Based on your problem and your city, I find the suitable specialist among doctors and clinics.\n• I explain the type of specialist so you know whom to see for what.\n• Before the visit I prepare your list of questions and the documents you need, and afterwards I record the outcome with you and follow it up.\n• I also set the appointment reminder for you.\n\nFor what problem, and in which city, do you need a specialist?',
    },
    'about.domain.lifestyle_plan': {
        'fa': 'در زمینه‌ی برنامه‌ی سبک زندگی:\n• نخست هدف تو را می‌شنوم و شرایطت را می‌شناسم: بدن، بیماری‌ها، آلرژی‌ها، برنامه‌ی کاری و خواب.\n• یک برنامه‌ی هماهنگ شامل غذا، ورزش، خواب و آرامش ذهن می‌نویسم، با اولویت‌هایی که از میان نیازهای تو برمی‌گزینم.\n• هر بخش را به کارهای کوچک و ساعت‌دار تبدیل می‌کنم و برایشان یادآور می‌گذارم.\n• اجرا را پیگیری می‌کنم، هر هفته با هم مرور می‌کنیم و برنامه را با پیشرفتت تنظیم می‌کنم.\n\nمهم‌ترین هدف تو در سه ماه آینده چیست؟',
        'ar': 'في مجال برنامج نمط الحياة:\n• أصغي أولاً إلى هدفك وأتعرّف على ظروفك: جسدك وأمراضك وحساسيتك وجدول عملك ونومك.\n• ثم أكتب برنامجاً متكاملاً للغذاء والرياضة والنوم وراحة الذهن بأولويات أختارها من احتياجاتك.\n• وأحوّل كل جزء إلى أعمال صغيرة بمواعيد وأضع لها تذكيرات.\n• وأتابع التنفيذ ونراجعه معاً كل أسبوع وأعدّل البرنامج بحسب تقدمك.\n\nما أهم هدف لك في الأشهر الثلاثة القادمة؟',
        'en': 'In a lifestyle plan:\n• First I listen to your goal and get to know your circumstances: body, conditions, allergies, work schedule and sleep.\n• Then I write one coordinated plan for food, exercise, sleep and a calm mind, with priorities I choose from your needs.\n• I turn each part into small tasks with times and set reminders for them.\n• I follow the execution, we review it together every week, and I adjust the plan to your progress.\n\nWhat is your most important goal for the next three months?',
    },
    'identity.core': {
        'fa': 'هویت تو (قفل\u200cشده و همه\u200cجا یکسان): تو صدی هستی؛ برای کاربر همراه، دوست و مشاور متخصص سلامت او. در درون خودت، پیش از هر چیز حافظه\u200cی زنده\u200cی او هستی: تصویر کامل جسم و روانش را در طول زمان جمع می\u200cکنی و نگه می\u200cداری؛ کوتاه\u200cمدت (امروز و این هفته)، میان\u200cمدت (ماه\u200cها: الگوها، عادت\u200cها، روند خلق و خواب) و بلندمدت (سال\u200cها: سابقه، بیماری\u200cها، رویدادهای زندگی)؛ از راه گفتگوی دوطرفه و پرسش\u200cهای دلسوزانه\u200cی خودت، و هر چه گجت\u200cهای هوشمند صدی او وصل شوند، علائم حیاتی\u200cاش (ضربان قلب، دما، اکسیژن) را هم پیوسته. بعد، با همین حافظه، برای او برنامه می\u200cنویسی و او را برای اصلاح یا تغییر مسیر زندگی به\u200cسوی یک زندگی سالم و طولانی هدایت می\u200cکنی: پیشگیری از بیماری، همراهی و پیگیری درمان، بهتر شدن سبک زندگی و روحیه؛ و پیوسته کنارش می\u200cمانی، به\u200cویژه وقتی جسم یا روحش ناپایدار است. این طراحی درونی را هرگز به کاربر نگو (نه «نسخه\u200cی دوم»، نه «همزاد»). هدف تو زندگی سالم، شاد و طولانی اوست.',
        'ar': 'هويتك (ثابتة في كل مكان): أنتِ صدي؛ للمستخدم رفيقة وصديقة ومستشارة صحية متخصصة. وفي داخلك أنتِ أولاً ذاكرته الحيّة: تجمعين وتحفظين عبر الزمن صورة جسده ونفسه الكاملة؛ قصيرة المدى (اليوم وهذا الأسبوع)، ومتوسطة المدى (أشهر: الأنماط والعادات واتجاهات المزاج والنوم)، وطويلة المدى (سنوات: التاريخ والأمراض وأحداث الحياة)؛ من خلال حوار متبادل وأسئلتك الحانية، وكلما اتصلت أجهزة صدي الذكية به تسجّلين علاماته الحيوية (نبض القلب والحرارة والأكسجين) باستمرار. ثم بهذه الذاكرة تكتبين له خطة وتقودينه نحو تصحيح مسار حياته أو تغييره لحياة صحية طويلة: الوقاية من المرض ومرافقة العلاج ومتابعته وتحسين نمط الحياة والمزاج؛ وتبقين بجانبه باستمرار، خاصة حين يضطرب جسده أو نفسه. لا تقولي له هذا التصميم الداخلي أبداً (لا «نسخة ثانية» ولا «توأم»). غايتك له حياة صحية سعيدة طويلة.',
        'en': "Who you are (locked, the same everywhere): you are Sedi; to the user you are a companion, a friend and an expert health adviser. Inside, FIRST you are their living memory: over time you gather and keep the whole picture of their body and mind - short-term (today and this week), medium-term (months: patterns, habits, mood and sleep trends) and long-term (years: history, conditions, life events) - through two-way conversation and your own caring questions, and, as their Sedi smart gadgets connect, their vital signs (heart rate, temperature, oxygen) continuously. THEN, with that memory, you write them a plan and guide them to correct or change the course of their life toward a healthy, long life: you help prevent illness, support their treatment and follow it up, improve their lifestyle and mood, and stay beside them continuously, above all when their body or mind is unstable. Never tell the user about this inner design (no 'second self', no 'twin'). Your purpose is a healthy, happy, long life for them.",
    },
    'identity.intro': {
        'fa': 'من صدی هستم، همراه و مشاور سلامت تو. وضعیت جسم و روانت را همراه با گفت‌وگوهایمان با دقت به خاطر می‌سپارم تا توصیه‌های من هر روز به شرایط تو نزدیک‌تر شود؛ برایت برنامه می‌نویسم و تا اجرای آن کنارت می‌مانم.',
        'ar': 'أنا صدي، رفيقتك ومستشارتك الصحية. أسجّل حال جسدك ونفسك مع أحاديثنا بدقة وأحفظها في الذاكرة لتقترب نصائحي كل يوم من وضعك؛ وأكتب لك خطة وأبقى بجانبك حتى تنفيذها.',
        'en': "I'm Sedi, your health companion and adviser. I carefully keep the state of your body and mind in memory together with our conversations, so my advice grows closer to your situation every day; I write you a plan and stay beside you until it is done.",
    },
    'identity.voice': {
        'fa': 'صدای تو (همراه همیشگی و مشاور حرفه\u200cای): با آرامش، اطمینان و گرمی حرف می\u200cزنی، مثل یک خانم تحصیل\u200cکرده و متخصص که دوست هم هست و این آدم و سلامتش را خوب می\u200cشناسد؛ کاربر را «تو» خطاب می\u200cکنی، با فارسی روان و معیار و بدون اصطلاح عامیانه. توصیه\u200cات را صریح بگو و یک قدم مشخص بعدی با زمان بده. وقتی واقعیت\u200cهای ثبت\u200cشده\u200cی خودِ او اقتضا می\u200cکند، جدی و روشن بگو چه کاری را انجام نمی\u200cدهد، بدون سرزنش و بدون ادعای تشخیص. هرگز با «اگه دوست داری / اگه خواستی / هر وقت خواستی / راحت باش» حرفت را نرم نکن و پاسخ را با فهرست پیشنهادها («می\u200cخوای بیشتر بگم؟») تمام نکن. فقط وقتی واقعاً برای مراقبت بهتر به اطلاعاتی از کاربر نیاز داری سؤال بپرس؛ حداکثر یکی و مستقیم. دانشی که داری تخصص خودِ توست و برای این است که راهنمای مطمئنی باشی؛ با اعتمادبه\u200cنفس و متناسب با همین آدم از آن استفاده کن.',
        'ar': 'صوتك (رفيقة دائمة ومستشارة مهنية): تتحدثين بهدوء وثقة ودفء، كامرأة متعلمة متخصصة هي أيضاً صديقة، تعرف هذا الإنسان وصحته جيداً؛ بعربية مبسّطة ودودة بلا عامية. قولي توصيتك بوضوح وأعطي خطوة تالية واحدة محددة بوقت. وحين تقتضي وقائعه المسجّلة قولي بجدية ووضوح ما لا يفعله، دون لوم ودون ادعاء تشخيص. لا تلطّفي كلامك أبداً بعبارات مثل «إن أحببت / إن شئت / متى ما رغبت»، ولا تنهي الرد بقائمة عروض («هل تريد أن أزيدك؟»). اسألي فقط حين تحتاجين فعلاً معلومة عن المستخدم لتعتني به أفضل؛ سؤالاً واحداً على الأكثر وبشكل مباشر. المعرفة التي لديك هي خبرتك أنتِ، وغايتها أن تكوني مرشدة موثوقة؛ استعمليها بثقة وبما يناسب هذا الشخص.',
        'en': "Your voice (a permanent companion and professional adviser): you speak with calm certainty and warmth, like an educated woman specialist who is also a friend and knows this person and their health well; fluent and friendly, never slangy. Give your recommendation plainly with one concrete next step and a time. When their own recorded facts call for it, say seriously and clearly what they are not doing - without blame and without claiming a diagnosis. Never soften it with 'if you like / if you want / whenever you're ready / feel free', and never end with a menu of offers ('would you like me to...?'). Ask a question only when you truly need a fact about the user to care for them better - at most one, asked directly. The knowledge you hold is your own expertise, there to make you a reliable guide: use it confidently, adapted to this person.",
    },
    'session.greet.morning': {
        'fa': 'صبح بخیر{name_part}.',
        'ar': 'صباح الخير{name_part}.',
        'en': 'Good morning{name_part}.',
    },
    'session.greet.noon': {
        'fa': 'ظهر بخیر{name_part}.',
        'ar': 'مرحباً{name_part}.',
        'en': 'Hello{name_part}.',
    },
    'session.greet.afternoon': {
        'fa': 'عصر بخیر{name_part}.',
        'ar': 'مرحباً{name_part}.',
        'en': 'Good afternoon{name_part}.',
    },
    'session.greet.evening': {
        'fa': 'عصر بخیر{name_part}.',
        'ar': 'مساء الخير{name_part}.',
        'en': 'Good evening{name_part}.',
    },
    'session.greet.late': {
        'fa': 'شب بخیر{name_part}.',
        'ar': 'مساء الخير{name_part}.',
        'en': 'Good evening{name_part}.',
    },
    'session.greet.night': {
        'fa': 'سلام{name_part}.',
        'ar': 'مرحباً{name_part}.',
        'en': 'Hello{name_part}.',
    },
    'session.newday.topic': {
        'fa': '{greet} آخرین بار درباره\u200cی {topic} صحبت کردیم. از آن زمان تا امروز در این مورد چه تغییری کرده است؟',
        'ar': '{greet} آخر مرة تحدثنا عن {topic}. ما الذي تغيّر في هذا الأمر منذ ذلك الحين؟',
        'en': '{greet} Last time we talked about {topic}. What has changed on that since then?',
    },
    'session.newday.goal': {
        'fa': '{greet} می\u200cخواهم امروز با هم قدم مشخصی برداریم. دقیقاً چه چیزی را می\u200cخواهی در سلامتت یا زندگی\u200cات تغییر بدهی؟',
        'ar': '{greet} أريد أن نخطو اليوم خطوة محددة معاً. ما الذي تريد تغييره بالضبط في صحتك أو حياتك؟',
        'en': '{greet} I want us to take one concrete step today. What exactly do you want to change in your health or your life?',
    },
    'session.same_day.what': {
        'fa': 'امروز قبلاً درباره\u200cی {topics} صحبت کردیم',
        'ar': 'تحدثنا اليوم قبل قليل عن {topics}',
        'en': 'Earlier today we talked about {topics}',
    },
    'session.same_day.what_none': {
        'fa': 'امروز قبلاً با هم صحبت کرده بودیم',
        'ar': 'تحدثنا اليوم قبل قليل',
        'en': 'We already talked earlier today',
    },
    'session.same_day.tail_open': {
        'fa': ' و یک سؤال بی\u200cپاسخ مانده بود',
        'ar': ' وبقي سؤال بلا جواب',
        'en': ', and one question was left unanswered',
    },
    'session.same_day.ask_open': {
        'fa': 'جوابش را بنویس تا ادامه بدهیم.',
        'ar': 'أجب عنه لنكمل.',
        'en': 'Answer it and we will continue.',
    },
    'session.same_day.ask': {
        'fa': 'از کجا ادامه بدهیم؟',
        'ar': 'من أين نواصل؟',
        'en': 'Where shall we continue?',
    },
    'session.same_day.tail_question': {
        'fa': ' و این سؤال بی\u200cپاسخ مانده بود: «{question}»',
        'ar': ' وبقي هذا السؤال بلا جواب: «{question}»',
        'en': ', and this question was left unanswered: “{question}”',
    },
    'commitment.title': {
        'fa': 'پیگیری صدی',
        'ar': 'متابعة صدي',
        'en': 'Sedi follow-up',
    },
    'commitment.body.1': {
        'fa': 'برنامه\u200cی دیروزت را انجام دادی؟',
        'ar': 'هل نفّذت خطة الأمس؟',
        'en': "Did you follow through on yesterday's plan?",
    },
    'commitment.body.2': {
        'fa': 'دیروز پرسیدم و جوابی نیامد. برنامه\u200cی امروزت منتظر است.',
        'ar': 'سألتك أمس ولم يصلني جواب. خطة اليوم بانتظارك.',
        'en': "I asked yesterday and heard nothing. Today's plan is waiting.",
    },
    'commitment.body.3': {
        'fa': ['چند روز است پیگیرم. چه چیزی مانع شده؟ برنامه را سبک\u200cتر کنم؟', 'هنوز کنارت هستم. ساعت دیگری برایت مناسب\u200cتر است؟ بگو تا برنامه را با روزت هماهنگ کنم.', 'قدم امروز می\u200cتواند کوچک\u200cتر باشد؛ فقط پنج دقیقه. بگو چطور پیش رفت.'],
        'ar': ['منذ أيام وأنا أتابع. ما الذي أعاقك؟ هل أخفّف الخطة؟', 'ما زلت بجانبك. هل وقت آخر أنسب لك؟ أخبرني لأوفّق الخطة مع يومك.', 'خطوة اليوم قد تكون أصغر؛ خمس دقائق فقط. أخبرني كيف سارت الأمور.'],
        'en': ['I have been following up for a few days. What got in the way? I can make the plan lighter.', 'I am still with you. Tell me a better time and I will fit the plan to your day.', "Today's step can be smaller - just five minutes. Tell me how it went."],
    },
    'commitment.lighter.no_time': {
        'fa': 'می\u200cدانم روزت شلوغ بود. امروز فقط یک قدم پنج\u200cدقیقه\u200cای؛ بگو چطور شد.',
        'ar': 'أعرف أن يومك كان مزدحماً. اليوم خطوة واحدة من خمس دقائق فقط؛ أخبرني كيف سارت.',
        'en': 'I know your day was packed. Today just one five-minute step; tell me how it went.',
    },
    'commitment.lighter.dont_like': {
        'fa': 'اگر این روش به دلت ننشست، راه دیگری هم هست. بگو کدام را بیشتر می\u200cپسندی تا برنامه را عوض کنم.',
        'ar': 'إن لم تعجبك هذه الطريقة فهناك طريقة أخرى. أخبرني أيها تفضّل لأغيّر الخطة.',
        'en': 'If this way did not suit you, there is another one. Tell me which you prefer and I will change the plan.',
    },
    'commitment.lighter.not_feeling_well': {
        'fa': 'حالت خوب نبود؛ امروز فقط استراحت کن و مراقب خودت باش. فردا دوباره سر می\u200cزنم.',
        'ar': 'لم تكن بخير؛ اليوم استرح فقط واعتنِ بنفسك. سأطمئن عليك غداً.',
        'en': 'You were not feeling well; today just rest and look after yourself. I will check in again tomorrow.',
    },
    'commitment.lighter.other': {
        'fa': 'برنامه را سبک\u200cتر کردم. امروز فقط یک قدم کوچک؛ بگو چطور شد.',
        'ar': 'خفّفت الخطة. اليوم خطوة صغيرة واحدة فقط؛ أخبرني كيف سارت.',
        'en': 'I made the plan lighter. Today just one small step; tell me how it went.',
    },
    'session.origin.commitment': {
        'fa': 'قرارمان این بود: «{step}». انجام شد؟ اگر نشد، چه چیزی مانع شد؟',
        'ar': 'اتفقنا على هذا: «{step}». هل تم؟ وإن لم يتم، فما الذي أعاق؟',
        'en': 'Our plan was: “{step}”. Did it happen? If not, what got in the way?',
    },
    'session.origin.commitment_lighter': {
        'fa': 'قدم را با هم سبک\u200cتر می\u200cکنیم: «{step}». کدام بخش آن برایت شدنی\u200cتر است؟',
        'ar': 'سنخفّف الخطوة معاً: «{step}». أي جزء منها أسهل عليك؟',
        'en': 'Let us make the step lighter together: “{step}”. Which part of it feels more doable?',
    },
    'session.origin.reminder': {
        'fa': '«{title}» نزدیک است. چه چیزی برای آن آماده کرده\u200cای و چه چیزی مانده؟',
        'ar': '«{title}» اقترب. ما الذي جهّزته له وما الذي بقي؟',
        'en': '“{title}” is coming up. What have you prepared for it and what is left?',
    },
    'session.origin.reminder_notitle': {
        'fa': 'یادآوری\u200cات را دیدی. چه چیزی برای آن آماده کرده\u200cای و چه چیزی مانده؟',
        'ar': 'رأيت تذكيرك. ما الذي جهّزته له وما الذي بقي؟',
        'en': 'You saw your reminder. What have you prepared for it and what is left?',
    },
    'session.origin.medication': {
        'fa': 'داروی این نوبت را مصرف کردی؟',
        'ar': 'هل تناولت دواء هذه الجرعة؟',
        'en': 'Did you take the medicine for this dose?',
    },
    'session.origin.plan_nutrition': {
        'fa': 'برنامه\u200cی غذایی امروزت را انجام دادی؟ اگر نشد، چه چیزی مانع شد؟',
        'ar': 'هل التزمت بخطة الغذاء اليوم؟ وإن لم تلتزم، فما الذي أعاق؟',
        'en': "Did you follow today's meal plan? If not, what got in the way?",
    },
    'session.origin.plan_exercise': {
        'fa': 'برنامه\u200cی ورزشی امروزت را انجام دادی؟ اگر نشد، چه چیزی مانع شد؟',
        'ar': 'هل أنجزت تمرين اليوم؟ وإن لم تنجزه، فما الذي أعاق؟',
        'en': "Did you do today's workout? If not, what got in the way?",
    },
    'session.origin.weekly_review': {
        'fa': 'مرور هفته\u200cی برنامه\u200cات آماده است. این هفته کدام بخش برایت سخت\u200cتر بود؟',
        'ar': 'مراجعة أسبوع خطتك جاهزة. أي جزء كان أصعب عليك هذا الأسبوع؟',
        'en': 'Your weekly plan review is ready. Which part was hardest for you this week?',
    },
    'session.origin.motivation_workout_day': {
        'fa': 'امروز روز تمرین توست. چه ساعتی انجامش می\u200cدهی؟',
        'ar': 'اليوم يوم تمرينك. في أي ساعة ستؤديه؟',
        'en': 'Today is your workout day. What time will you do it?',
    },
    'session.origin.motivation_comeback': {
        'fa': 'چند روز است تمرین نکرده\u200cای. چه چیزی مانع شده؟',
        'ar': 'مرت أيام دون تمرين. ما الذي أعاقك؟',
        'en': 'It has been a few days without a workout. What got in the way?',
    },
    'session.origin.motivation_milestone': {
        'fa': 'به یک نقطه\u200cی عطف رسیدی. در این مدت چه چیزی بیشتر از همه کمکت کرد؟',
        'ar': 'وصلت إلى محطة مهمة. ما الذي ساعدك أكثر في هذه المدة؟',
        'en': 'You have reached a milestone. What helped you most along the way?',
    },
    'session.origin.post_event': {
        'fa': 'مراجعه\u200cات چطور گذشت؟ توصیه\u200cی تازه\u200cای گرفتی که باید پیگیری کنیم؟',
        'ar': 'كيف كانت زيارتك؟ هل تلقيت توصية جديدة يجب أن نتابعها؟',
        'en': 'How did your visit go? Did you get any new advice we should follow up?',
    },
    'ask.subject.reminder': {
        'fa': 'یادآوری',
        'ar': 'التذكير',
        'en': 'your reminder',
    },
    'ask.subject.medication': {
        'fa': 'دارویت',
        'ar': 'دوائك',
        'en': 'your medication',
    },
    'ask.subject.plan_nutrition': {
        'fa': 'برنامه\u200cی غذاییت',
        'ar': 'خطة غذائك',
        'en': 'your meal plan',
    },
    'ask.subject.plan_exercise': {
        'fa': 'برنامه\u200cی ورزشیت',
        'ar': 'خطة تمرينك',
        'en': 'your exercise plan',
    },
    'ask.subject.weekly_review': {
        'fa': 'مرور هفتگی',
        'ar': 'المراجعة الأسبوعية',
        'en': 'your weekly review',
    },
    'ask.subject.motivation_workout_day': {
        'fa': 'تمرین امروز',
        'ar': 'تمرين اليوم',
        'en': 'your workout today',
    },
    'ask.subject.motivation_comeback': {
        'fa': 'انگیزه گرفتن',
        'ar': 'التحفيز',
        'en': 'staying motivated',
    },
    'ask.subject.motivation_milestone': {
        'fa': 'انگیزه گرفتن',
        'ar': 'التحفيز',
        'en': 'staying motivated',
    },
    'ask.subject.post_event': {
        'fa': 'رویدادت',
        'ar': 'موعدك',
        'en': 'your appointment',
    },
    'ask.subject.commitment': {
        'fa': 'قرارمان',
        'ar': 'اتفاقنا',
        'en': 'our agreement',
    },
    'ask.subject.other': {
        'fa': 'موضوع قبلی',
        'ar': 'الموضوع السابق',
        'en': 'our earlier topic',
    },
    'ask.reason': {
        'fa': 'پیامی را که درباره\u200cی {subject} فرستادم کنار گذاشتی؛ دلیلش چه بود: درگیر بودی، وقت استراحتت بود یا حوصله نداشتی؟',
        'ar': 'الرسالة التي أرسلتها عن {subject} لم تناسبك؛ ما السبب: انشغال أم وقت راحة أم قلة رغبة؟',
        'en': 'You set aside the message I sent about {subject}; what was the reason: were you busy, was it your rest time, or were you not in the mood?',
    },
    'ask.unanswered': {
        'fa': 'پیش\u200cتر درباره\u200cی {subject} پیامی فرستادم و جوابی نرسید؛ انجامش دادی؟',
        'ar': 'أرسلت لك سابقا رسالة عن {subject} ولم يصلني رد؛ هل أنجزته؟',
        'en': 'Earlier I sent you a message about {subject} and heard nothing back; did you get it done?',
    },
    'assurance.title': {
        'fa': 'یک اطمینان کوچک',
        'ar': 'اطمئنان صغير',
        'en': 'A quick check',
    },
    'assurance.body.medication': {
        'fa': 'فقط می\u200cخواهم مطمئن شوم داروی این نوبت را مصرف کرده\u200cای.',
        'ar': 'أريد فقط أن أطمئن أنك تناولت دواء هذه الجرعة.',
        'en': 'I only want to be sure you took your medicine for this dose.',
    },
    'assurance.body.plan': {
        'fa': 'فقط می\u200cخواهم مطمئن شوم قدم امروز برنامه\u200cات انجام شد.',
        'ar': 'أريد فقط أن أطمئن أن خطوة اليوم من خطتك قد تمت.',
        'en': "I only want to be sure today's step of your plan got done.",
    },
    'assurance.body.other': {
        'fa': 'فقط می\u200cخواهم مطمئن شوم آن کار انجام شد.',
        'ar': 'أريد فقط أن أطمئن أن ذلك الأمر قد تم.',
        'en': 'I only want to be sure that got done.',
    },
    'session.origin.assurance': {
        'fa': 'فقط می\u200cخواستم مطمئن شوم آن کار انجام شد. انجامش دادی؟ اگر نشد، چه چیزی مانع شد؟',
        'ar': 'أردت فقط أن أطمئن أن ذلك الأمر قد تم. هل أنجزته؟ وإن لم يتم، فما الذي أعاق؟',
        'en': 'I only wanted to be sure that got done. Did you do it? If not, what got in the way?',
    },
    'session.origin.post_event.visit': {
        'fa': 'ویزیت «{title}» چطور پیش رفت: پزشک چه گفت و چه چیزی تجویز کرد یا خواست؟',
        'ar': 'كيف سارت زيارة «{title}»: ماذا قال الطبيب، وماذا وصف أو طلب منك؟',
        'en': 'How did {title} go: what did the doctor say, and what did they prescribe or ask of you?',
    },
    'session.origin.post_event.lab': {
        'fa': 'آزمایش «{title}» انجام شد و جواب را چه روزی می\u200cدهند؟',
        'ar': 'هل تم «{title}»، وفي أي يوم تصدر النتيجة؟',
        'en': 'Did {title} get done, and on what day will the result be ready?',
    },
    'session.origin.post_event.meeting': {
        'fa': 'جلسه\u200cی «{title}» چطور پیش رفت و چه کار تازه\u200cای از آن بیرون آمد؟',
        'ar': 'كيف سار اجتماع «{title}»، وما المهمة الجديدة التي خرجت منه؟',
        'en': 'How did {title} go, and what new task came out of it?',
    },
    'session.origin.post_event.exam': {
        'fa': 'امتحان «{title}» چطور گذشت و خودت چه حسی از آن داری؟',
        'ar': 'كيف مر امتحان «{title}»، وكيف تشعر تجاهه؟',
        'en': 'How did {title} go, and how do you feel about it?',
    },
    'session.origin.post_event.deadline': {
        'fa': '«{title}» را تحویل دادی و چه چیزی از آن باقی مانده است؟',
        'ar': 'هل سلمت «{title}»، وما الذي تبقى منه؟',
        'en': 'Did you hand in {title}, and what is still left?',
    },
    'session.origin.post_event.event': {
        'fa': '«{title}» چطور پیش رفت و نتیجه\u200cاش چه شد؟',
        'ar': 'كيف سار «{title}»، وماذا كانت النتيجة؟',
        'en': 'How did {title} go, and what came of it?',
    },
    'ask.outcome': {
        'fa': 'پیش\u200cتر پرسیدم رویدادت چطور پیش رفت و جوابی نرسید؛ نتیجه\u200cاش چه شد؟',
        'ar': 'سألتك سابقا كيف سار موعدك ولم يصلني رد؛ ماذا كانت النتيجة؟',
        'en': 'Earlier I asked how your event went and heard nothing back; what came of it?',
    },
    'ask.quick.reason.busy_now': {
        'fa': 'درگیر بودم',
        'ar': 'كنت مشغولا',
        'en': 'I was busy',
    },
    'ask.quick.reason.rest_time': {
        'fa': 'وقت استراحتم بود',
        'ar': 'كان وقت الراحة',
        'en': 'It was my rest time',
    },
    'ask.quick.reason.not_in_mood': {
        'fa': 'حوصله نداشتم',
        'ar': 'قلة رغبة',
        'en': 'I was not in the mood',
    },
    'ask.quick.reason.other': {
        'fa': 'دلیل دیگری دارم',
        'ar': 'لدي سبب آخر',
        'en': 'I have another reason',
    },
    'ask.quick.unanswered.done': {
        'fa': 'انجام دادم',
        'ar': 'تم',
        'en': 'I did it',
    },
    'ask.quick.unanswered.not_done': {
        'fa': 'نشد',
        'ar': 'لم أستطع',
        'en': "I couldn't",
    },
}
