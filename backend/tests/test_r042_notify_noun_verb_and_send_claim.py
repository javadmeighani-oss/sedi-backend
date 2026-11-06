"""R-042 class fix (Javad 2026-11-06 phone test): «میخواهم یه نوتیف الان برام ارسال کنی در مورد چه خبر جواد» was not recognised as a
reminder, the model answered «نوتیف … را همین الان برات فرستادم» and NOTHING was sent.

Two guarantees, tested as a matrix (not one sentence):
1. a notification noun + a delivery verb with small words between them, plus a day/time word or «now», is a reminder in fa/ar/en;
   complaints / negations / past references are not requests;
2. a model reply never claims an immediate send that did not happen (it reaches the guard only when no reminder was created)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.intelligence.contracts import IntentId
from backend.app.services.intelligence.grounding_guard import strip_unverified_send_claims
from backend.app.services.intelligence.intent_registry import resolve_intent
from backend.app.services.intelligence.reminder_event_readiness import looks_like_notify_request, parse_reminder_event_draft

NOW = datetime(2026, 11, 6, 15, 30, tzinfo=timezone.utc)

POSITIVE = [
    ("میخواهم یه نوتیف الان برام ارسال کنی در مورد چه خبر جواد", "fa"),
    ("میخوام یه نوتیف الان برام بفرستی", "fa"),
    ("یه نوتیف الان بهم بده", "fa"),
    ("الان یه اعلان برام بفرست", "fa"),
    ("می‌خواهم فردا ساعت ۱۰ یک پیام برایم ارسال کنی", "fa"),
    ("همین الان برام یه پیام بزن", "fa"),
    ("send a notification to me now", "en"),
    ("send me a notification right now", "en"),
    ("could you please notify me now", "en"),
    ("أرسل لي إشعاراً الآن", "ar"),
    ("أريد أن ترسل إشعاراً الآن", "ar"),
]
NEGATIVE = [
    ("چرا نوتیف الان نفرستادی", "fa"),
    ("چرا برام نوتیف نمیفرستی الان", "fa"),
    ("دیروز نوتیف فرستادی", "fa"),
    ("نوتیف ها رو الان خاموش کن", "fa"),
    ("پیام بدی دارم", "fa"),
    ("why did you never send a notification now", "en"),
    ("لماذا لم ترسل لي إشعاراً الآن", "ar"),
]


@pytest.mark.parametrize("message,lang", POSITIVE)
def test_notify_noun_plus_delivery_verb_is_a_reminder(message, lang):
    assert looks_like_notify_request(message, lang) is True
    assert resolve_intent(message=message, language=lang).intent_id is IntentId.REMINDER


@pytest.mark.parametrize("message,lang", NEGATIVE)
def test_complaints_negations_and_past_references_are_not_requests(message, lang):
    assert looks_like_notify_request(message, lang) is False


def test_the_real_sentence_becomes_an_immediate_reminder_about_the_topic():
    message = "میخواهم یه نوتیف الان برام ارسال کنی در مورد چه خبر جواد"
    draft, missing = parse_reminder_event_draft(message=message, timezone_name="Asia/Tehran", now_utc=NOW, language="fa")
    assert missing is None and draft is not None
    assert draft.relative is True
    assert draft.reminder_offsets == (0,)
    # within a couple of minutes of "now" (19:00 in Tehran)
    assert (draft.starts_at_local.hour, draft.starts_at_local.minute) in {(19, 0), (19, 1), (19, 2), (19, 3)}
    assert "جواد" in draft.title


@pytest.mark.parametrize(
    "reply,lang",
    [
        ("نوتیف «چه خبر، جواد؟» را همین الان برات فرستادم.", "fa"),
        ("I just sent you a notification right now.", "en"),
        ("أرسلت لك إشعاراً الآن.", "ar"),
    ],
)
def test_a_false_immediate_send_claim_is_replaced_by_an_honest_line(reply, lang):
    out = strip_unverified_send_claims(reply, lang)
    assert out != reply
    assert "فرستادم" not in out and "sent" not in out.lower().split("send")[0] and "أرسلت" not in out


def test_other_sentences_stay_and_non_now_references_are_untouched():
    assert strip_unverified_send_claims("سلام. نوتیف را همین الان فرستادم. حالت چطور است؟", "fa") == "سلام. حالت چطور است؟"
    for keep in ("امروز صبح خلاصه‌ات را فرستادم.", "This morning I sent your daily summary.", "Your plan is ready now."):
        assert strip_unverified_send_claims(keep, "fa" if "ا" in keep else "en") == keep
    assert strip_unverified_send_claims("", "fa") == ""
