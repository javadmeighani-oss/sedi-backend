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


class _Model:
    def __init__(self, out):
        self.calls = []
        self.out = out
        outer = self

        class _C:
            @staticmethod
            def create(**kw):
                outer.calls.append(kw)
                if isinstance(outer.out, Exception):
                    raise outer.out
                from types import SimpleNamespace as N

                return N(choices=[N(message=N(content=outer.out))])

        class _Chat:
            completions = _C

        self.chat = _Chat


def setup_function(_):
    from backend.app.services.i5 import query_translation as qt

    qt._CACHE.clear()


def test_v2_the_model_still_runs_and_its_first_two_queries_come_first():
    m = _Model("asthma symptoms\nasthma treatment\nasthma\nbreathing problems")
    out = translate_query_alternatives("علائم آسم", "fa", client=m)
    assert m.calls and out[:2] == ["asthma symptoms", "asthma treatment"]


def test_v2_official_names_are_added_after_the_models_two_and_unique():
    m = _Model("wheeze attacks\nbreathing trouble\nlung disease\nairway problems")
    out = translate_query_alternatives("کمردرد دارم", "fa", client=m)
    assert out[:2] == ["wheeze attacks", "breathing trouble"]
    assert "back pain" in out and len(out) == len({o.lower() for o in out}) <= 4


def test_v2_model_outputs_are_not_repeated_by_the_lexicon():
    m = _Model("back pain\nlow back pain\nspine health\nsciatica")
    out = translate_query_alternatives("کمردرد دارم", "fa", client=m)
    assert len({o.lower() for o in out}) == len(out) <= 4 and out[:2] == ["back pain", "low back pain"]


def test_v2_a_failed_model_falls_back_to_the_lexicon_alone_and_is_not_cached():
    from backend.app.services.i5 import query_translation as qt

    m = _Model(RuntimeError("down"))
    out = translate_query_alternatives("کمردرد دارم چه کنم", "fa", client=m)
    assert "back pain" in out and len(out) == 4
    assert not qt._CACHE


def test_v2_a_non_english_model_answer_falls_back_to_the_lexicon():
    out = translate_query_alternatives("کمردرد دارم چه کنم", "fa", client=_Model("کمر درد"))
    assert "back pain" in out


def test_v2_an_unknown_topic_is_model_only_and_failure_gives_nothing():
    assert translate_query_alternatives("درباره بیماری ویلسون بگو", "fa", client=_Model(RuntimeError("down"))) == []
    out = translate_query_alternatives("درباره بیماری ویلسون بگو", "fa", client=_Model("Wilson disease\ncopper"))
    assert out == ["Wilson disease", "copper"]


def test_v2_a_combined_psychology_question_stays_model_only():
    m = _Model("depression diabetes\ndiabetes distress")
    out = translate_query_alternatives("به خاطر دیابت افسرده شده‌ام", "fa", client=m)
    assert m.calls and out == ["depression diabetes", "diabetes distress"]


def test_v2_the_merged_result_is_cached_and_the_model_runs_once():
    m = _Model("a back topic\nanother back topic")
    first = translate_query_alternatives("کمردرد دارم", "fa", client=m)
    assert translate_query_alternatives("کمردرد دارم", "fa", client=m) == first and len(m.calls) == 1


def test_v2_unpadded_names_are_a_prefix_of_the_padded_list():
    short = hb.health_bridge_alternatives("علائم آسم", pad=False)
    full = hb.health_bridge_alternatives("علائم آسم")
    assert short and len(short) <= len(full) and full[: len(short)] == short


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


@pytest.mark.parametrize(
    "query",
    ["آسم دارم", "درد پاشنه پا", "درد شانه", "کشیدگی عضله", "نقرس", "ام اس", "أعاني من الربو", "ألم الكتف"],
)
def test_a_bridged_question_always_offers_four_alternatives_for_breadth(query):
    """Measured after PR 167: the adapter takes <=2 units per alternative, so 1-2 short names retrieved far too little."""
    out = hb.health_bridge_alternatives(query)
    assert len(out) == 4 and len({o.lower() for o in out}) == 4
    assert out[0] in hb.health_bridge_alternatives(query)


def test_padding_never_repeats_an_aspect_already_asked_or_named():
    out = hb.health_bridge_alternatives("علائم آسم")
    assert out[0] == "asthma symptoms" and "asthma symptoms symptoms" not in out
    assert sum(1 for o in out if o.endswith("symptoms")) == 1
    diet = hb.health_bridge_alternatives("رژیم دیابت")
    assert all("diet diet" not in o for o in diet)

