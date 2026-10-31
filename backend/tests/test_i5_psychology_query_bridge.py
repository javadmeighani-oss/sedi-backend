"""R-044: the deterministic fa/ar psychology bridge is instant, exact and leaves disease questions to the LLM path."""

from __future__ import annotations

import pytest

from backend.app.services.i5 import query_translation
from backend.app.services.i5.psychology_query_bridge import bridge_alternatives, normalize

# (topic, persian question, arabic question, expected FIRST English alternative) - the production battery questions.
CASES = [
    ("stress", "خیلی استرس دارم، چیکار کنم؟", "أشعر بتوتر شديد طوال الوقت، ماذا أفعل؟", "stress"),
    ("anxiety", "چطور می‌تونم اضطراب و نگرانی دائمی‌م رو کنترل کنم؟", "كيف أتحكم في القلق والتفكير الزائد؟", "anxiety"),
    ("panic", "وقتی حمله‌ی پانیک میاد چیکار کنم؟", "ماذا أفعل أثناء نوبة الهلع؟", "panic attack"),
    ("depression", "چند هفته‌ست احساس غم و ناامیدی دارم، این افسردگیه؟", "أشعر بالحزن واليأس منذ أسابيع، هل هذا اكتئاب؟", "depression"),
    ("grief", "از دست دادن عزیزم رو چطور تحمل کنم؟", "كيف أتعامل مع فقدان شخص عزيز؟", "grief"),
    ("loneliness", "احساس تنهایی می‌کنم، چطور با آدم‌ها ارتباط بگیرم؟", "أشعر بالوحدة، كيف أتواصل مع الآخرين؟", "loneliness"),
    ("anger", "چطور عصبانیتم رو کنترل کنم؟", "كيف أتحكم في غضبي؟", "anger"),
    ("burnout", "از کار خسته و فرسوده شدم، چه کمکی می‌کنه؟", "أنا منهك ومحترق وظيفياً، ما الذي يساعد؟", "burnout"),
    ("self_esteem", "چطور اعتماد به نفسم رو بالا ببرم؟", "كيف أعزز ثقتي بنفسي؟", "self-esteem"),
    ("mindfulness", "مدیتیشن ذهن‌آگاهی چیه و کمک می‌کنه؟", "ما هو التأمل الذهني وهل يفيد؟", "mindfulness"),
    ("breathing", "یه تمرین تنفس برای آروم شدن بهم یاد بده", "علمني تمرين تنفس لأهدأ", "breathing exercises"),
    ("cbt", "درمان شناختی رفتاری (CBT) چیه؟", "ما هو العلاج المعرفي السلوكي؟", "cognitive behavioural therapy"),
    ("ocd", "افکار تکراری مزاحم دارم و نمی‌تونم کنترل کردن رو متوقف کنم", "لدي أفكار متكررة مزعجة ولا أستطيع التوقف عن التحقق من الأشياء", "obsessive compulsive disorder"),
    ("ptsd", "نمی‌تونم از فکر یه اتفاق بد که برام افتاده بیرون بیام", "لا أستطيع التوقف عن التفكير في حدث مؤلم حدث لي", "PTSD"),
    ("postpartum", "بعد از زایمان خیلی غمگینم", "أشعر بحزن شديد بعد الولادة", "postnatal depression"),
    ("motivation", "چطور انگیزه‌م رو برای عادت‌های سالم حفظ کنم؟", "كيف أحافظ على دافعي للعادات الصحية؟", "healthy habits"),
]


@pytest.mark.parametrize("topic,fa,ar,first", CASES, ids=[c[0] for c in CASES])
def test_battery_questions_bridge_to_the_right_english_topic(topic, fa, ar, first):
    for text in (fa, ar):
        out = bridge_alternatives(text)
        assert out, f"{topic}: nothing for {text!r}"
        assert out[0] == first, f"{topic}: {out!r} for {text!r}"
        assert all(a.isascii() for a in out)
        assert len(out) <= 4


def test_two_topics_interleave_most_specific_first():
    out = bridge_alternatives("از نگرانی شب‌ها خوابم نمی‌بره، چطور بهتر بخوابم؟")
    assert out[:2] == ["anxiety", "insomnia"]
    assert "sleep" in out
    out_ar = bridge_alternatives("لا أستطيع النوم ليلاً بسبب القلق، كيف أنام أفضل؟")
    assert out_ar[:2] == ["anxiety", "insomnia"]


def test_social_anxiety_beats_plain_anxiety():
    assert bridge_alternatives("کنار آدم‌ها خیلی مضطرب می‌شم")[0] == "social anxiety"
    assert bridge_alternatives("أشعر بقلق شديد أمام الآخرين")[0] == "social anxiety"


@pytest.mark.parametrize(
    "text",
    [
        "دیابت دارم و ازش خسته و غمگین شدم",
        "لدي السكري وأشعر بالإرهاق والحزن بسببه",
        "با دیابت چی بخورم؟",
        "علائم فشار خون بالا چیه؟",
        "ما أعراض ارتفاع ضغط الدم؟",
        "من سرطان دارم و خیلی استرس دارم",
    ],
)
def test_messages_that_name_a_disease_are_left_to_the_existing_path(text):
    assert bridge_alternatives(text) == []


@pytest.mark.parametrize("text", ["", "   ", "سلام", "امروز هوا خوبه", "ورزش روی خلق و خو تاثیر داره؟", "I feel stressed"])
def test_unrelated_or_english_text_gives_nothing(text):
    assert bridge_alternatives(text) == []


def test_postpartum_needs_a_low_mood_word_not_just_a_pregnancy_word():
    assert bridge_alternatives("بعد از زایمان چه ورزشی بکنم؟") == []
    assert bridge_alternatives("بعد از زایمان خیلی گریه می‌کنم")[0] == "postnatal depression"


def test_normalization_unifies_persian_and_arabic_letters():
    assert normalize("اكتئاب") == normalize("اکتئاب")
    assert normalize("ذهن‌آگاهی") == "ذهن اگاهی"
    assert normalize("  هَلَع  ") == "هلع"


class _NoModelCall:
    """A client that fails the test if the translation model is ever called."""

    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            def create(**_kw):
                raise AssertionError("the LLM must not be called for a bridged psychology question")


def test_translate_query_alternatives_uses_the_bridge_without_calling_the_model():
    query_translation._CACHE.clear()
    out = query_translation.translate_query_alternatives("خیلی استرس دارم، چیکار کنم؟", "fa", client=_NoModelCall())
    assert out[0] == "stress"
    out_ar = query_translation.translate_query_alternatives("ماذا أفعل أثناء نوبة الهلع؟", "ar", client=_NoModelCall())
    assert out_ar[0] == "panic attack"


class _CountingClient:
    """Counts model calls and answers with one English keyword line."""

    def __init__(self):
        self.calls = 0
        outer = self

        class _Msg:
            content = "diabetes symptoms\ndiabetes"

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        class _Completions:
            @staticmethod
            def create(**_kw):
                outer.calls += 1
                return _Resp()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_disease_question_still_goes_to_the_model_path():
    query_translation._CACHE.clear()
    client = _CountingClient()
    out = query_translation.translate_query_alternatives("علائم دیابت چیست؟", "fa", client=client)
    assert client.calls == 1
    assert out == ["diabetes symptoms", "diabetes"]
