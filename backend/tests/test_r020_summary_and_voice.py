"""R-020: overall-status summary card, no echo of the user's words in the opener, plan intent variants, no stories in
list-like memory, colloquial friendly voice."""
from __future__ import annotations

from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.i6.memory_writes import write_fact
from backend.app.services.i6.relationship_discovery import DiscoveryDisposition, classify_discovery_reply
from backend.app.services.i7 import conversation_recap as cr
from backend.app.services.intelligence.intent_registry import resolve_intent
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.profile.a3_profile_summary import build_a3_profile_summary
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

STORY = "من مادرم این بیماری را داشت. میخواهم بیشتر در مورد دلایل ابتلا به این بیماری توضیح دهی"


def test_summary_is_an_overall_status_paragraph_not_raw_rows(db):
    u = _user(db, "+17770020001", tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    process_message(db, u.id, "من دیابت دارم", "fa")
    process_message(db, u.id, "من معلمم", "fa")
    write_fact(db, u.id, "intake", "goal", "میخوام بیشتر به سلامتی برسم")
    write_fact(db, u.id, "preferences", "interests", STORY)  # legacy pollution already stored
    write_fact(db, u.id, "intake", "food_preferences", "خوب میخواهم در مورد بیماری als بیشتر صحبت کنیم")
    out = build_a3_profile_summary(db, u.id)
    s = out["summary"]
    assert s.startswith("جواد، تا اینجا این‌طور می‌شناسمت") and s.endswith(".")
    assert "دیابت" in s and "هدفت: میخوام بیشتر به سلامتی برسم" in s and "معلم" in s
    assert "مادرم این بیماری" not in s and "als" not in s  # pasted stories never reach the card
    assert "•" not in s and "حساسیت‌ها:" not in s  # not a list of collected rows


def test_summary_is_empty_when_nothing_clean_is_known(db):
    u = _user(db, "+17770020002", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    assert build_a3_profile_summary(db, u.id)["summary"] == ""


def test_opener_never_echoes_users_words_and_knows_hair_topic():
    assert cr.topic_phrase_from_text("دیابت پیشگیری", "fa") == "پیشگیری از دیابت"
    assert cr.topic_phrase_from_text("خیلی سال هست که ریزش مو دارم", "fa") == "مراقبت از موهات"
    assert cr.topic_phrase_from_text("موضوع جالبی بود", "fa") is None
    assert "دیابت" not in cr.topic_phrase_from_text("دیابت پیشگیری", "fa", privacy="lock_screen")


def test_plan_phrase_variants_are_one_intent():
    for msg in ("برنامه های غذایی میخوام", "برنامه‌های غذایی می‌خوام", "برنامه ی غذایی برام بساز"):
        r = resolve_intent(message=msg, language="fa")
        assert r.intent_id.name == "NUTRITION" and r.request_kind.name == "PERSONALIZED_PLAN", msg
    assert resolve_intent(message="برنامه‌ی کاری فردا", language="fa").intent_id.name == "GENERAL"


def test_story_or_request_is_never_stored_as_a_list_like_preference():
    for target in ("preferences.interests", "intake.food_preferences"):
        assert classify_discovery_reply(target, STORY, "fa").disposition is not DiscoveryDisposition.ANSWER
    assert classify_discovery_reply("preferences.interests", "پیاده روی و کتاب", "fa").disposition is DiscoveryDisposition.ANSWER


def test_persona_speaks_colloquially_and_asks_the_missing_question_instead_of_refusing():
    fa = PersonaPolicyV1.system_prompt("fa")
    assert "محاوره‌ای و صمیمی" in fa and "می‌تونی" in fa and "نمی‌توانم کمک کنم" in fa
    assert "ONE most important missing question" in PersonaPolicyV1.system_prompt("en")
