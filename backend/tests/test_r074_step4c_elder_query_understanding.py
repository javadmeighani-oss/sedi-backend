"""R-074 step 4c: questions about looking after an elderly relative reach the library (fa / ar / en).

Found by a read-only production diagnostic: «how can I look after my elderly mother» returned INSUFFICIENT_CONTEXT because
(1) the word «mother» (also inside «grandmother») demanded a referent although no personal record is asked for, and
(2) «look AFTER my father» / «after meals» / «following a diet» were read as date expressions.
Follow-ups about a person's own record («How was my mother?») and explicit dates keep their old, cautious behaviour."""
from __future__ import annotations

import pytest

from backend.app.services.scis.coreference import coreference_blocks_retrieval, resolve_coreference
from backend.app.services.scis.temporal_query import parse_temporal_query_intent

GENERAL_CARE = [
    ("en", "how can I look after my elderly mother at home"),
    ("en", "caring for my mother after a fall, any tips"),
    ("en", "my grandmother is old and falls a lot"),
    ("en", "how do I keep my mother safe at home and prevent falls"),
    ("en", "exercises for my mother who is elderly"),
    ("fa", "چطور از مادرم که سالمند است مراقبت کنم"),
    ("fa", "مادرم زیاد زمین می‌خورد"),
    ("fa", "برای مادرم چه ورزشی مناسب است"),
    ("ar", "كيف أعتني بأمي المسنة في المنزل"),
    ("ar", "أمي تسقط كثيرا كيف أساعدها"),
]
RECORD_FOLLOW_UPS = [
    ("en", "How was my mother?"),
    ("en", "how is my mother's last result"),
    ("en", "about her"),
    ("fa", "مادرم چطور بود؟"),
    ("fa", "نتیجه آزمایش مادرم"),
    ("ar", "كيف كانت أمي؟"),
    ("ar", "نتيجة تحليل والدتي"),
    # Codex P2 (PR 166): history / counting questions contain «falls» but ask for the person's own record
    ("en", "How many falls has my mother had?"),
    ("en", "when did my mother last fall"),
    ("en", "how often does my mother fall"),
    ("fa", "مادرم چند بار زمین خورده است"),
    ("ar", "كم مرة سقطت أمي"),
]


@pytest.mark.parametrize("lang,query", GENERAL_CARE)
def test_a_general_care_question_about_a_relative_does_not_need_a_referent(lang, query):
    c = resolve_coreference(query, language=lang, referents=[])
    assert not coreference_blocks_retrieval(c, query, language=lang)


@pytest.mark.parametrize("lang,query", RECORD_FOLLOW_UPS)
def test_a_follow_up_about_the_persons_own_record_still_needs_a_referent(lang, query):
    c = resolve_coreference(query, language=lang, referents=[])
    if c.state in {"NOT_APPLICABLE"}:
        pytest.skip("no kinship cue in this phrasing")
    assert coreference_blocks_retrieval(c, query, language=lang)


@pytest.mark.parametrize(
    "query",
    [
        "looking after my elderly father",
        "how to look after a person with dementia",
        "what to eat after meals",
        "following a diet for diabetes",
        "exercise after eating, is it safe",
        "take it after food",
    ],
)
def test_after_and_following_without_a_time_reference_are_not_dates(query):
    t = parse_temporal_query_intent(query, language="en")
    assert t.deterministic_state == "NONE" and t.clarification_required is False


@pytest.mark.parametrize(
    "query,state",
    [
        ("changes since 2026-01-15", "RESOLVED"),
        ("events after 2025/06/01", "RESOLVED"),
        ("events before 2025-12-01", "RESOLVED"),
        ("what to do after 2 weeks of surgery", "AMBIGUOUS"),
        ("symptoms since last week", "AMBIGUOUS"),
        ("results before March", "AMBIGUOUS"),
    ],
)
def test_real_time_references_keep_their_behaviour(query, state):
    assert parse_temporal_query_intent(query, language="en").deterministic_state == state


@pytest.mark.parametrize("query", ["بعد از غذا چه ورزشی بکنم", "پس از ناهار چه بخورم"])
def test_persian_after_without_a_time_reference_is_not_a_date(query):
    t = parse_temporal_query_intent(query, language="fa")
    assert t.deterministic_state != "AMBIGUOUS"


def test_persian_after_with_a_time_reference_stays_ambiguous():
    assert parse_temporal_query_intent("بعد از ۲ هفته چه کنم", language="fa").deterministic_state == "AMBIGUOUS"


@pytest.mark.parametrize(
    "query",
    [
        "how can I look after my mother who takes 2 medications",
        "looking after my father, he eats 3 meals a day",
    ],
)
def test_a_bare_number_is_not_a_time_reference(query):
    t = parse_temporal_query_intent(query, language="en")
    assert t.deterministic_state != "AMBIGUOUS"


@pytest.mark.parametrize(
    "query,state",
    [
        ("what to do after 3 days", "AMBIGUOUS"),
        ("symptoms since 2020", "AMBIGUOUS"),
        ("results after 10/2025", "AMBIGUOUS"),
        ("after 2 hours", "AMBIGUOUS"),
    ],
)
def test_numbers_with_a_unit_a_year_or_a_date_shape_still_count(query, state):
    assert parse_temporal_query_intent(query, language="en").deterministic_state == state


@pytest.mark.parametrize(
    "lang,query",
    [
        ("en", "how to look after this patient at home"),
        ("en", "what to do after meals, it may help"),
        ("en", "take it after food twice a day"),
        ("fa", "بعد از غذا هر روز چه ورزشی بکنم"),
        ("ar", "بعد الأكل كل يوم ماذا أفعل"),
    ],
)
def test_ordinary_words_like_this_may_and_a_day_are_not_dates(lang, query):
    assert parse_temporal_query_intent(query, language=lang).deterministic_state != "AMBIGUOUS"


@pytest.mark.parametrize(
    "lang,query",
    [
        ("en", "what to do after last week"),
        ("en", "results before March"),
        ("fa", "بعد از ۲ هفته چه کنم"),
        ("fa", "بعد از دو ماه چه کنم"),
        ("ar", "منذ ٣ أسابيع ماذا أفعل"),
    ],
)
def test_real_time_phrases_in_three_languages_stay_ambiguous_without_a_date(lang, query):
    assert parse_temporal_query_intent(query, language=lang).deterministic_state == "AMBIGUOUS"
