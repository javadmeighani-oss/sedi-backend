"""R-014: grounding guard + recent-turn history in the model messages + persona no-referral rules."""
from types import SimpleNamespace

from backend.app.core.conversation.brain import _append_recent_history
from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
from backend.app.services.intelligence.grounding_guard import strip_unsupported_personal_claims


def test_unrecorded_family_condition_sentence_is_removed():
    reply = "با توجه به اینکه مادرت دیابت داشته، بهتره شیرینی کم بخوری. یه پیاده‌روی کوتاه بعد از شام خوبه."
    out = strip_unsupported_personal_claims(reply, "من دیابت دارم و می‌خوام رژیم بگیرم", "fa")
    assert "مادرت" not in out
    assert "پیاده‌روی" in out


def test_recorded_family_condition_is_kept():
    reply = "چون مادرت دیابت داشته، مراقب قندت باش."
    out = strip_unsupported_personal_claims(reply, "مادرم دیابت داشت و من نگرانم", "fa")
    assert out == reply


def test_sedi_never_claims_her_own_relatives_condition():
    reply = "مادر من هم دیابت داره، پس درکت می‌کنم. بگو چه غذاهایی دوست داری."
    out = strip_unsupported_personal_claims(reply, "مادرم دیابت داره", "fa")
    assert "مادر من" not in out and "غذاهایی" in out


def test_benign_mentions_are_untouched():
    reply = "با خانواده‌ات قدم بزن تا از دیابت پیشگیری کنی."
    assert strip_unsupported_personal_claims(reply, "سلام", "fa") == reply


def test_all_sentences_unsupported_gives_neutral_ask():
    reply = "مادرت دیابت داشته."
    out = strip_unsupported_personal_claims(reply, "سلام", "fa")
    assert "مادرت" not in out and out


def _mem(u, s):
    return SimpleNamespace(user_message=u, sedi_response=s)


def test_history_is_oldest_first_and_skips_error_replies():
    class _Mem:
        def get_recent_messages(self, user_id, limit=10):
            # newest first, like query_eligible_raw
            return [
                _mem("دومی", "پاسخ دوم"),
                _mem("خطا", "الان به‌خاطر یه مشکل فنی از سمت خودم نمی‌تونم درست جواب بدم"),
                _mem("اولی", "پاسخ اول"),
            ]

    msgs: list = []
    assert _append_recent_history(msgs, _Mem(), 1, limit=8) == 2
    assert [m["content"] for m in msgs] == ["اولی", "پاسخ اول", "دومی", "پاسخ دوم"]


def test_history_failure_is_non_blocking():
    class _Boom:
        def get_recent_messages(self, user_id, limit=10):
            raise RuntimeError("db down")

    msgs: list = []
    assert _append_recent_history(msgs, _Boom(), 1, limit=8) == 0 and msgs == []


def test_persona_has_no_referral_reflex_and_has_grounding_in_all_languages():
    for lang in ("fa", "en", "ar"):
        prompt = PersonaPolicyV1.system_prompt(lang)
        rules = " ".join(PersonaPolicyV1.safety_rules(lang))
        assert "کاربر را به مراجعه به پزشک تشویق کن" not in prompt
        assert "encourage the user to see a clinician" not in prompt
        assert "شجّعي المستخدم على مراجعة الطبيب" not in prompt
        assert "به پزشک ارجاع بده" not in rules
    assert "second memory" in PersonaPolicyV1.system_prompt("en")
    assert "حافظه‌ی دوم" in PersonaPolicyV1.system_prompt("fa")
    assert "Grounding" in PersonaPolicyV1.system_prompt("en")


def test_recap_names_the_aspect_of_a_disease_topic():
    from backend.app.services.i7 import conversation_recap as cr

    assert cr._disease_phrase("راه پیشگیری از دیابت چیه", "دیابت", "fa") == "پیشگیری از دیابت"
    assert cr._disease_phrase("چی بخورم برای دیابت", "دیابت", "fa") == "بیماری دیابت"
    assert cr._disease_phrase("رژیم مناسب دیابت می‌خوام", "دیابت", "fa") == "تغذیه‌ی مناسب برای دیابت"
    assert cr._disease_phrase("symptoms of diabetes", "diabetes", "en") == "the symptoms of diabetes"
    assert cr._disease_phrase("hello", "ALS", "en") == "ALS"


def test_persona_has_professional_care_protocol_in_all_languages():
    for lang, needles in (
        ("en", ("Professional care protocol", "5-4-3-2-1", "Follow through", "never claim a licence")),
        ("fa", ("پروتکل مراقبت حرفه‌ای", "۵-۴-۳-۲-۱", "پیگیری:", "ادعای مجوز")),
        ("ar", ("بروتوكول الرعاية المهنية", "٥-٤-٣-٢-١", "المتابعة:", "ترخيصاً")),
    ):
        prompt = PersonaPolicyV1.system_prompt(lang)
        for n in needles:
            assert n in prompt, (lang, n)


def test_time_context_is_fail_open_and_localised():
    from datetime import datetime

    from backend.app.services.intelligence.time_context import build_time_context, format_time_hint

    sat_night = datetime(2026, 10, 24, 22, 30)  # a Saturday
    assert "شنبه" in format_time_hint(sat_night, "fa") and "شب" in format_time_hint(sat_night, "fa")
    assert "Saturday" in format_time_hint(sat_night, "en")
    assert build_time_context(object(), 1, "fa") == ""


def test_limit_questions_keeps_statements_and_only_the_first_question():
    from backend.app.services.intelligence.grounding_guard import limit_questions

    reply = "ریزش مو خیلی اذیت می‌کنه. پروتئین و آهنت مهمه. از کی شروع شده؟ دارو مصرف می‌کنی؟ سابقه‌ی خانوادگی داره؟"
    out = limit_questions(reply, 1)
    assert "از کی شروع شده؟" in out and "دارو" not in out and "پروتئین" in out
    assert limit_questions("فقط یک جمله.", 1) == "فقط یک جمله."
