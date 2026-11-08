"""R-074 step 8a: a deterministic Persian/Arabic -> English bridge for EVERY health topic family of the governed library.

The matrix is topics x fa/ar (R-065). Combined psychology questions, unknown topics and English questions keep their old path."""
from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
import yaml

from backend.app.services.i5 import health_query_bridge as hb
from backend.app.services.i5.query_translation import translate_query_alternatives

# (language, question, expected topic key that must be among the matched families, an English term that must be offered)
CASES = [
    ("fa", "کمردرد دارم چه کنم", "back_pain", "back pain"),
    ("ar", "أعاني من ألم الظهر", "back_pain", "back pain"),
    ("fa", "درد زانو موقع پله بالا رفتن", "knee", "knee injuries and disorders"),
    ("ar", "ألم الركبة عند صعود الدرج", "knee", "knee injuries and disorders"),
    ("fa", "پوکی استخوان و کلسیم", "osteoporosis", "osteoporosis"),
    ("ar", "ما علاج هشاشة العظام", "osteoporosis", "osteoporosis"),
    ("fa", "نقرس چه غذاهایی ممنوع است", "gout", "gout"),
    ("ar", "ما هو النقرس", "gout", "gout"),
    ("fa", "آرتروز دست و مفاصل", "arthritis", "arthritis"),
    ("fa", "رژیم غذایی برای دیابت", "diabetes", "type 2 diabetes"),
    ("ar", "نظام غذائي لمرضى السكري", "diabetic_diet", "diabetic diet"),
    ("fa", "فشار خون بالا دارم", "hypertension", "high blood pressure"),
    ("ar", "كيف أخفض ضغط الدم", "hypertension", "high blood pressure"),
    ("fa", "کلسترول بالا چه بخورم", "cholesterol", "high cholesterol"),
    ("ar", "علاج الكوليسترول", "cholesterol", "high cholesterol"),
    ("fa", "نارسایی قلبی علائم", "heart_failure", "heart failure"),
    ("fa", "سکته مغزی را چطور پیشگیری کنم", "stroke", "stroke"),
    ("ar", "علامات السكتة الدماغية", "stroke", "stroke"),
    ("fa", "برای کاهش وزن چه کنم", "obesity", "overweight and obesity"),
    ("ar", "كيف أخسر الوزن الزائد", "obesity", "overweight and obesity"),
    ("fa", "تغذیه سالم برای خانواده", "healthy_eating", "eating a balanced diet"),
    ("ar", "نصائح للأكل الصحي", "healthy_eating", "eating a balanced diet"),
    ("fa", "کم خونی و فقر آهن", "iron_anaemia", "iron deficiency anaemia"),
    ("fa", "ویتامین د کمبود", "vitamin_d", "vitamin D"),
    ("ar", "نقص فيتامين د", "vitamin_d", "vitamin D"),
    ("fa", "ورزش مناسب برای سالمندان", "exercise_older", "exercise for older adults"),
    ("ar", "تمارين المسنين", "exercise_older", "exercise for older adults"),
    ("fa", "نتایج آزمایش خون را چطور بفهمم", "blood_tests", "blood tests"),
    ("ar", "كيف أفهم نتائج التحاليل", "blood_tests", "blood tests"),
    ("fa", "مراقبت از مادر سالمندم در خانه", "caregivers", "caregivers"),
    ("ar", "كيف أعتني بأمي المسنة في المنزل", "older_adults", "healthy aging"),
    ("fa", "پدرم زوال عقل دارد", "dementia", "dementia"),
    ("ar", "والدي مصاب بالزهايمر", "dementia", "dementia"),
    ("fa", "پارکینسون چیست", "parkinson", "parkinson's disease"),
    ("fa", "میگرن و سردرد", "migraine", "migraine"),
    ("ar", "علاج الصداع النصفي", "migraine", "migraine"),
    ("fa", "آسم و تنگی نفس", "asthma", "asthma"),
    ("ar", "نوبة الربو", "asthma", "asthma"),
    ("fa", "ریفلاکس و سوزش سر دل", "gerd", "GERD"),
    ("fa", "یبوست مزمن", "constipation", "constipation"),
    ("ar", "علاج الإسهال", "diarrhea", "diarrhea"),
    ("fa", "سنگ کلیه چه علائمی دارد", "kidney_stones", "kidney stones"),
    ("fa", "عفونت ادراری", "uti", "urinary tract infections"),
    ("fa", "سرطان پستان غربالگری", "breast_cancer", "breast cancer"),
    ("ar", "أعراض سرطان القولون", "bowel_cancer", "bowel cancer"),
    ("fa", "آکنه و جوش صورت", "acne", "acne"),
    ("fa", "اگزما کودک", "eczema", "eczema"),
    ("ar", "علاج الأكزيما", "eczema", "eczema"),
    ("fa", "یائسگی علائم", "menopause", "menopause and perimenopause"),
    ("fa", "بارداری و تغذیه", "pregnancy", "pregnancy"),
    ("ar", "الدورة الشهرية غير منتظمة", "periods", "periods"),
    ("fa", "رشد کودک دو ساله", "child_development", "child development"),
    ("fa", "ترک سیگار", "smoking", "quit smoking"),
    ("ar", "كيف أقلع عن التدخين", "smoking", "quit smoking"),
    ("fa", "کم شنوایی پدرم", "hearing", "hearing disorders and deafness"),
    ("fa", "پوسیدگی دندان", "oral", "tooth decay"),
    ("fa", "سرگیجه ناگهانی", "dizziness", "balance disorders"),
    ("fa", "پدرم زیاد زمین می‌خورد", "falls", "falls"),
    ("ar", "أمي تسقط كثيرا", "falls", "falls"),
    ("fa", "زخم بستر در سالمند", "pressure_sores", "pressure sores"),
    ("fa", "مراقبت تسکینی در پایان عمر", "palliative", "palliative care"),
    ("fa", "خستگی مزمن و بی حالی", "tiredness", "sleep and tiredness"),
    ("fa", "آپنه خواب و خروپف", "sleep_apnoea", "obstructive sleep apnoea"),
]


@pytest.mark.parametrize("lang,query,key,term", CASES)
def test_every_topic_family_is_bridged_to_the_official_english_name(lang, query, key, term):
    assert key in hb.matched_topics(query), (query, hb.matched_topics(query))
    assert term in hb.health_bridge_alternatives(query)


@pytest.mark.parametrize("query", ["گالری هنری را دیدم", "درد دارم", "سلام حالت چطوره", "ممنون", "کمک می‌خواهم", "ما هذا", "مرحبا"])
def test_unknown_or_vague_questions_are_left_to_the_model_path(query):
    assert hb.health_bridge_alternatives(query) == []


def test_alternatives_are_bounded_specific_first_and_unique():
    out = hb.health_bridge_alternatives("فشار خون بالا و کلسترول و دیابت")
    assert 1 <= len(out) <= 4 and len({o.lower() for o in out}) == len(out)
    assert out[0] in {"high blood pressure", "high cholesterol", "type 2 diabetes"}


def test_the_longer_marker_wins_over_the_general_one():
    assert hb.matched_topics("سرطان پستان")[0] == "breast_cancer"
    assert hb.matched_topics("دیابت نوع ۱")[0] == "type1_diabetes"
    assert hb.matched_topics("تمرین تعادل")[0] == "balance"


def test_the_lexicon_is_well_formed():
    raw = yaml.safe_load(io.open(Path(hb._LEXICON), encoding="utf-8"))
    keys = [e["k"] for e in raw["entries"]]
    assert len(keys) == len(set(keys)) >= 150
    for e in raw["entries"]:
        assert e["en"] and all(isinstance(a, str) and a.strip() for a in e["en"]), e["k"]
        assert e["fa"] or e["ar"], e["k"]
        assert all(not re.search(r"[؀-ۿ]", a) for a in e["en"]), e["k"]  # English side stays English
        for m in list(e.get("fa") or []) + list(e.get("ar") or []):
            assert len(hb._norm(m)) >= 2, (e["k"], m)


def test_translate_uses_the_bridge_without_any_model_call():
    class _Boom:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(*a, **k):
                    raise AssertionError("the model must not be called for a bridged topic")

    out = translate_query_alternatives("کمردرد دارم چه کنم", "fa", client=_Boom())
    assert "back pain" in out


def test_a_combined_psychology_question_still_goes_to_the_model_path():
    calls = []

    class _Client:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(*a, **k):
                    calls.append(1)
                    raise RuntimeError("model path reached")

    out = translate_query_alternatives("به خاطر دیابت افسرده شده‌ام", "fa", client=_Client())
    assert calls and out == []  # fail-open: model path reached, nothing invented


def test_an_english_question_is_never_bridged():
    assert translate_query_alternatives("back pain exercises", "en") == []


def test_a_broken_lexicon_fails_open(monkeypatch):
    hb._entries.cache_clear()
    monkeypatch.setattr(hb, "_LEXICON", Path("does-not-exist.yaml"))
    try:
        assert hb.health_bridge_alternatives("کمردرد") == []
    finally:
        hb._entries.cache_clear()


@pytest.mark.parametrize(
    "query,forbidden",
    [
        ("مراقبت از پوست صورت", "caregivers"),
        ("مراقبت از موهایم چطور باشد", "caregivers"),
        ("كيف أعتني ببشرتي", "caregivers"),
        ("بچه ام امروز بی حوصله است", "child_development"),
    ],
)
def test_generic_words_do_not_pull_in_an_unrelated_topic(query, forbidden):
    """Generic words («care», «child») are not topic markers; only the specific phrases are."""
    assert forbidden not in hb.matched_topics(query)


@pytest.mark.parametrize(
    "query,first",
    [
        ("علائم آسم چیست", "asthma symptoms"),
        ("درمان کمردرد", "back pain treatment"),
        ("علت میگرن چیست", "migraine causes"),
        ("پیشگیری از پوکی استخوان", "osteoporosis prevention"),
        ("رژیم مناسب برای نقرس", "gout diet"),
        ("ورزش برای آرتروز زانو", "arthritis exercise"),  # the longer marker (آرتروز) names the main topic
        ("أعراض الربو", "asthma symptoms"),
        ("علاج هشاشة العظام", "osteoporosis treatment"),
        ("أسباب الصداع النصفي", "migraine causes"),
        ("الوقاية من السكتة الدماغية", "stroke prevention"),
    ],
)
def test_the_requested_aspect_is_kept_in_the_english_search(query, first):
    """Codex P2 (PR 167): symptoms / treatment / causes / prevention / diet / exercise are not dropped."""
    out = hb.health_bridge_alternatives(query)
    assert out[0] == first and len(out) <= 4 and len({o.lower() for o in out}) == len(out)
    assert first.rsplit(" ", 1)[0] in out or any(first.split()[0] in o for o in out[1:])  # the plain topic name stays too


def test_an_aspect_already_in_the_topic_name_is_not_repeated():
    out = hb.health_bridge_alternatives("رژیم غذایی سالم")  # healthy_eating: «eating a balanced diet» already says diet
    assert "eating a balanced diet diet" not in out and out[0] == "eating a balanced diet"
