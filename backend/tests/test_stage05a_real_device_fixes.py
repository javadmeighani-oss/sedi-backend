"""Stage 05-A: fixes from the real-device test (opener tone, topic carry-over, plain text, brand spelling)."""
import re
from pathlib import Path

from backend.app.services.intelligence import topic_carryover as tc
from backend.app.services.intelligence.next_best_question import _TEMPLATES
from backend.app.services.intelligence.plain_text import to_plain_chat_text

APP = Path(__file__).resolve().parents[1] / "app"


def test_followup_with_anaphor_needs_topic():
    assert tc.needs_topic("برنامه های غذایی مناسب با این بیماری چیه؟", "fa", has_own_health_term=True)
    assert tc.needs_topic("what diet suits this condition?", "en", has_own_health_term=True)


def test_topicless_short_request_needs_topic_but_named_subject_does_not():
    assert tc.needs_topic("تو باید بتوانی برنامه بدهی", "fa", has_own_health_term=False)
    assert not tc.needs_topic("برای ALS چه برنامه غذایی خوبه؟", "fa", has_own_health_term=True)
    assert not tc.needs_topic("سلام", "fa", has_own_health_term=False)
    long_msg = "یک پیام خیلی طولانی " * 10 + "برنامه"
    assert not tc.needs_topic(long_msg, "fa", has_own_health_term=False)


def test_find_topic_takes_newest_resolvable_message_and_skips_current():
    labels = {"در مورد ALS بیشتر توضیح بده": "ALS", "قدیمی ام اس": "multiple sclerosis"}
    prev = ["سلام", "در مورد ALS بیشتر توضیح بده", "قدیمی ام اس"]
    assert tc.find_topic_in_messages(prev, labels.get, current_message="برنامه بده") == "ALS"
    assert tc.find_topic_in_messages(["سلام"], labels.get) is None
    assert tc.find_topic_in_messages(["برنامه بده"], lambda t: "ALS", current_message="برنامه بده") is None


def test_augment_query_keeps_user_words_first():
    assert tc.augment_query("برنامه بده", "ALS") == "برنامه بده (ALS)"
    assert tc.augment_query("برنامه بده", None) == "برنامه بده"


def test_governed_gate_allows_carried_topic_only():
    from backend.app.services.intelligence.orchestrator import allow_governed_knowledge_decision as gate

    kw = dict(terminal_safety=False, message="تو باید بتوانی برنامه بدهی", language="fa", intent=None, interaction_need=None)
    assert gate(**kw) is False
    assert gate(**kw, topic_carried=True) is True
    assert gate(**{**kw, "terminal_safety": True}, topic_carried=True) is False


def test_plain_text_strips_markdown_emphasis():
    out = to_plain_chat_text("نکته مهم اینه که **فعلاً راهِ اثبات‌شده‌ای وجود نداره** و ادامه")
    assert "**" not in out and "فعلاً راهِ اثبات‌شده‌ای وجود نداره" in out


def test_main_generation_path_applies_plain_text():
    src = (APP / "services" / "intelligence" / "orchestrator.py").read_text(encoding="utf-8")
    assert "out_message = to_plain_chat_text(validated.message)" in src
    # both the terminal-safety branch and the main generation branch sanitize
    assert src.count("to_plain_chat_text(validated.message)") >= 2


def test_nbq_templates_have_no_stiff_optional_prefix():
    for tid, by_lang in _TEMPLATES.items():
        for lang, text in by_lang.items():
            assert not re.match(r"^\s*(اختیاری|اختياري|Optional)\s*:", text), (tid, lang)


def test_brand_spelling_is_sadi_never_sedi_in_persian_arabic_text():
    bad = ("سدی", "سِدی", "سدي", "سِدي")
    offenders = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(b in text for b in bad):
            offenders.append(str(path.relative_to(APP)))
    assert offenders == [], offenders


def test_a3_snippet_only_for_topic_like_text_never_a_request():
    from backend.app.services import a3_session_open as a3

    assert a3._safe_continuity_snippet("walking") == "walking"
    assert a3._safe_continuity_snippet("I want to start walking 30 minutes every evening.")
    assert a3._safe_continuity_snippet("در مورد ALS بیشتر توضیح بده") is None
    assert a3._safe_continuity_snippet("What should I eat?") is None
    assert a3._safe_continuity_snippet("") is None


def test_a3_opener_never_quotes_raw_user_sentence():
    from backend.app.services import a3_session_open as a3

    text = a3._continuity_opener("fa", "برنامه فعالیتت", " جواد")
    assert "خوش آمدید" not in text and "مایلید" not in text and "«برنامه فعالیتت»" in text
    for options in a3._OPENERS.values():
        assert all("{name_part}" in o for o in options)
    assert "مایلید" not in a3._INTRO["fa"] and "شما" not in a3._INTRO["fa"]
