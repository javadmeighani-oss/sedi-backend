"""R-066/R-067 (step 1C): conversation, not interrogation - a GENERAL mechanism (R-065), matrix over topics x languages.

No hard cap on questions (Javad's decision): the guard only removes a restatement of the user's words, the hint only
nudges toward a conclusion, and the system question is not stacked under a model question.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.conversation import persona_policy_v1 as pp
from backend.app.services.intelligence.conversation_flow import advance_hint, asks_a_question, question_streak, strip_echo
from backend.app.services.intelligence.psychological_interaction import append_discovery_questions

# (language, what the user said, a reply that opens by restating it + adds insight, a marker of the restatement)
_ECHOES = [
    ("fa", "من هر روز بعد از ناهار سردرد می‌گیرم و شب‌ها کم می‌خوابم",
     "هر روز بعد از ناهار سردرد می‌گیری و شب‌ها کم می‌خوابی. این الگو معمولاً به کم‌آبی یا کم‌خوابی برمی‌گردد؛ امروز دو لیوان آب بیشتر بنوش.",
     "سردرد می‌گیری"),
    ("fa", "این روزها خیلی غمگینم و حوصله هیچ کاری ندارم",
     "این روزها خیلی غمگین هستی و حوصله هیچ کاری نداری. این حس در دوره‌های پرفشار شایع است و با یک کار کوچک روزانه بهتر می‌شود؛ امروز ده دقیقه پیاده‌روی کن.",
     "غمگین هستی"),
    ("fa", "من حدودا۱۱ تا ۱۲ شب میخوابم و صبح زود هم باید از خواب بیدار بشم",
     "متوجه شدم، جواد؛ معمولاً ساعت ۱۱ تا ۱۲ شب می‌خوابی و صبح زود بیدار می‌شوی. پس مهم است بدانیم چند ساعت خوابِ واقعی به دستت می‌رسد؛ امشب ساعتش را یادداشت کن.",
     "می‌خوابی و صبح زود بیدار"),
    ("fa", "از خواب هم بعصی شبها بیدار میشوم",
     "بعضی شب‌ها از خواب بیدار می‌شوی. بیدارشدن کوتاه در طول شب پیش می‌آید؛ مهم‌تر این است که چقدر طول می‌کشد دوباره بخوابی.",
     "از خواب بیدار می‌شوی"),
    ("en", "I go to bed around 11 and I wake up at 6 every day",
     "You go to bed around 11 and wake up at 6 every day. That gives you about seven hours, the lower end of what adults need; try moving bedtime to 10:30.",
     "go to bed around 11"),
    ("en", "My lower back hurts every evening after I sit at my desk all day",
     "Your lower back hurts every evening after you sit at your desk all day. Long sitting loads the spine; stand and walk for two minutes every hour.",
     "lower back hurts every evening"),
    ("ar", "أنام الساعة الحادية عشرة وأستيقظ في السادسة كل يوم",
     "تنام الساعة الحادية عشرة وتستيقظ في السادسة كل يوم. هذا يعطيك سبع ساعات تقريباً وهو الحد الأدنى للبالغين؛ جرّب تقديم موعد النوم نصف ساعة.",
     "تنام الساعة الحادية عشرة"),
]


@pytest.mark.parametrize("lang,user,reply,marker", _ECHOES)
def test_a_reply_never_opens_by_repeating_the_users_words(lang, user, reply, marker):
    out = strip_echo(reply, user, lang)
    assert marker not in out
    assert len(out.split()) >= 8  # the useful rest is kept verbatim


def test_a_reply_that_adds_something_new_is_left_untouched():
    user = "سه شب است خوابم نمی‌برد"
    reply = "سه شب بی‌خوابی واقعاً فرساینده است؛ امشب لازم نیست به‌زور خودت را بخوابانی. از امروز بعدازظهر کافئین نخور."
    assert strip_echo(reply, user, "fa") == reply
    long_user = "من چند روز است که حس می‌کنم انرژی ندارم و به‌سختی از جایم بلند می‌شوم"
    assert strip_echo("خستگی چندروزه معمولاً از کم‌خوابی، کم‌آبی یا کمبود آهن می‌آید. اول ساعت خوابت را ثابت کن.", long_user, "fa").startswith("خستگی")


@pytest.mark.parametrize("lang,reply,expected_start", [
    ("fa", "متوجه شدم، جواد؛ امشب ساعت ۱۰ بخواب و ساعت بیدارشدنت را ثابت نگه دار.", "امشب"),
    ("fa", "فهمیدم. اول ساعت خوابت را ثابت کن و بعد کافئین را کم کن.", "اول"),
    ("en", "I understand. Try going to bed thirty minutes earlier tonight.", "Try"),
    ("en", "Got it, Sara; walk for ten minutes after lunch every day.", "Walk"),
])
def test_a_bare_acknowledgement_that_only_introduces_a_restatement_is_removed(lang, reply, expected_start):
    assert strip_echo(reply, "یک پیام کاملاً نامربوط درباره‌ی چیز دیگر که هیچ هم‌پوشانی ندارد", lang).startswith(expected_start)


def test_a_confirmation_of_a_dose_is_never_removed_as_an_echo():
    user = "روزی یک قرص ۵ میلی‌گرم می‌خورم"
    reply = "پس روزی یک قرص ۵ میلی‌گرم می‌خوری. این دوز را بدون نظر پزشکت تغییر نده."
    assert strip_echo(reply, user, "fa") == reply


def test_the_guard_never_empties_a_reply_and_never_removes_a_question():
    user = "من هر روز بعد از ناهار سردرد می‌گیرم"
    only = "هر روز بعد از ناهار سردرد می‌گیری."
    assert strip_echo(only, user, "fa") == only  # nothing else to say: keep
    asked = "هر روز بعد از ناهار سردرد می‌گیری؟ این را برای تشخیص علت می‌پرسم."
    assert strip_echo(asked, user, "fa").startswith("هر روز")
    assert strip_echo("", user, "fa") == "" and strip_echo("متن", "", "fa") == "متن"


# ---- the SOFT hint: no cap, never a strip -----------------------------------------------------------------------------
@pytest.mark.parametrize("lang,marker", [("fa", "[پیشروی_به_نتیجه]"), ("ar", "[التقدم_نحو_الخلاصة]"), ("en", "[ADVANCE_TO_A_CONCLUSION]")])
def test_two_question_replies_in_a_row_get_the_soft_hint(lang, marker):
    history = ["یک توضیح. سؤال اول؟", "یک توضیح دیگر. سؤال دوم؟"]
    assert advance_hint(history, lang).startswith(marker)
    assert advance_hint(["سؤال؟", "یک پاسخ بدون سؤال."], lang) == ""
    assert advance_hint(["سؤال؟"], lang) == ""
    assert advance_hint([], lang) == ""


def test_the_streak_counts_only_the_latest_consecutive_question_replies():
    assert question_streak(["الف.", "ب؟", "ج؟", "د؟"]) == 3
    assert question_streak(["الف؟", "ب."]) == 0
    assert asks_a_question("توضیح. آیا درد داری؟") and not asks_a_question("همین است.")


def test_there_is_no_hard_cap_the_hint_is_a_nudge_not_a_strip():
    # a reply that asks a question after three question-replies is NOT touched by any guard here
    reply = "حدسم این است که دیر خوابیدن علت اصلی است، چون ساعت بیدارشدنت ثابت است. فقط یک چیز مهم است: چند ساعت طول می‌کشد تا خوابت ببرد؟"
    assert strip_echo(reply, "نمی‌دانم", "fa") == reply


# ---- one question per reply: the system question is not stacked under a model question ---------------------------
def test_the_system_question_is_not_stacked_under_a_model_question():
    assert append_discovery_questions("یک توضیح کوتاه. سؤال خود مدل؟", ["سؤال سیستمی؟"]) == "یک توضیح کوتاه. سؤال خود مدل؟"
    assert append_discovery_questions("A short explanation. A model question?", ["System question?"]) == "A short explanation. A model question?"
    assert append_discovery_questions("هل لديك ألم؟", ["سؤال النظام؟"]) == "هل لديك ألم؟"
    assert append_discovery_questions("یک توضیح بدون سؤال.", ["سؤال سیستمی؟"]).endswith("سؤال سیستمی؟")
    assert append_discovery_questions("", ["فقط سؤال؟"]) == "فقط سؤال؟"


# ---- prompts: hypothesis-led, no fixed number of questions, no restating ----------------------------------------------
@pytest.mark.parametrize("lang,needles", [
    ("en", ("Assessment by hypothesis", "FORM YOUR OWN HYPOTHESIS", "no fixed number of questions", "Never repeat or paraphrase what the user has just told you")),
    ("fa", ("ارزیابی حدس‌محور", "خودت حدس بزن", "تعداد سؤال ثابت نیست", "تکرار یا بازگو نکن")),
    ("ar", ("التقييم بالفرضية", "كوّني فرضيتك أنتِ", "ليس هناك عدد ثابت من الأسئلة", "لا تكرري ولا تعيدي صياغة ما قاله المستخدم للتو")),
])
def test_the_prompt_is_hypothesis_led_in_every_language(lang, needles):
    prompt = {"en": pp._SYSTEM_PROMPT_EN, "fa": pp._SYSTEM_PROMPT_FA, "ar": pp._SYSTEM_PROMPT_AR}[lang]
    for needle in needles:
        assert needle in prompt, (lang, needle)
    assert "ONE question at a time" not in pp._SYSTEM_PROMPT_EN and "فقط یک سؤال در هر بار" not in pp._SYSTEM_PROMPT_FA


# ---- wiring contract --------------------------------------------------------------------------------------------------
def test_the_brain_and_the_orchestrator_are_wired():
    app = Path(__file__).resolve().parents[1] / "app"
    brain = (app / "core" / "conversation" / "brain.py").read_text(encoding="utf-8")
    assert "from backend.app.services.intelligence.conversation_flow import advance_hint" in brain
    assert "from backend.app.services.intelligence.conversation_flow import strip_echo" in brain
    assert brain.index("advance_hint(") < brain.index('messages.append({"role": "user", "content": user_message})')
    orchestrator = (app / "services" / "intelligence" / "orchestrator.py").read_text(encoding="utf-8")
    assert "nbq_was_appended = gen_message != _before_nbq" in orchestrator
