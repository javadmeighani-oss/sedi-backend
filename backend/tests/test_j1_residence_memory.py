"""J1 (R-094, D-393/D-394): the user's residence lives ONLY in Sedi's memory, learned from what the user states.
Deterministic extractor -> candidate promotion map -> I6 social/home_city + home_area (consent-gated by write_fact)."""
import pytest

from backend.app.services.candidate_promotion_service import LIFESTYLE_SCALAR_MAP
from backend.app.services.knowledge.stated_facts_extractor_v1 import extract_stated_facts
from backend.app.services.memory.memory_contract import ALLOWED_KEYS

ZW = "‌"


def _facts(text):
    return {(f.fact_key, f.fact_value) for f in extract_stated_facts(text) if f.fact_key in ("home_city", "home_area")}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("من ساکن تهرانپارس هستم", {("home_city", "تهران"), ("home_area", "تهران" + ZW + "پارس")}),
        ("در نارمک زندگی می‌کنم", {("home_city", "تهران"), ("home_area", "نارمک")}),
        ("خونه‌ام سعادت آباد است", {("home_city", "تهران"), ("home_area", "سعادت" + ZW + "آباد")}),
        ("من در شیراز زندگی می‌کنم", {("home_city", "شیراز")}),
        ("ساکن منطقه ۸ تهران هستم", {("home_city", "تهران"), ("home_area", "منطقه 8")}),
        ("خانه‌ی ما در اصفهان است", {("home_city", "اصفهان")}),
        ("من و برادرم در شیراز زندگی می‌کنیم", {("home_city", "شیراز")}),
        ("I live in Shiraz", {("home_city", "Shiraz")}),
        ("I live in Tehranpars", {("home_city", "Tehran"), ("home_area", "تهران" + ZW + "پارس")}),
    ],
)
def test_residence_is_extracted_from_a_first_person_statement(text, expected):
    assert _facts(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "سر کار در نارمک هستم",  # a workplace is not a residence
        "شرکت ما در تهرانپارس است",
        "آیا در شیراز زندگی می‌کنی؟",  # a question
        "اگر در تهران زندگی می‌کردم ورزش می‌کردم",  # conditional
        "برادرم در شیراز زندگی می‌کند",  # another person
        "برادرم ساکن شیراز است",  # another person, «ساکن» cue
        "مادرم ساکن نارمک است",
        "دکتر خوب در تهرانپارس می‌خواهم",  # a provider request, not where the user lives
        "امروز هوا خوب است",
    ],
)
def test_other_sentences_never_become_a_residence(text):
    assert _facts(text) == set()


def test_the_memory_vocabulary_and_promotion_map_know_the_new_keys():
    assert "home_city" in ALLOWED_KEYS["social"] and "home_area" in ALLOWED_KEYS["social"]
    assert LIFESTYLE_SCALAR_MAP["home_city"] == ("social", "home_city")
    assert LIFESTYLE_SCALAR_MAP["home_area"] == ("social", "home_area")


def test_no_profile_field_was_added_for_the_city():
    from backend.app import models

    cols = {c.name for c in models.UserProfileCore.__table__.columns}
    assert not (cols & {"city", "home_city", "province", "address", "residence"})  # memory only (R-093 amendment 3)
