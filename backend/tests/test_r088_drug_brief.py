"""R-088 amendment 3 / R-091 (D-384) package A2: Sedi introduces the medicine the user names, from the web.

Offline: the web client is a fake. Guards under test: name-only query (privacy), strict scrubbing of the web-derived sentence,
recognised-or-ask, the two-source rule, kill switch / cap / cache / fail-open, and the integration into the care interview.
"""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.medication_care import chat_reminder as mc
from backend.app.services.medication_care import drug_brief as db

GOOD = "لووتیروکسین دارویی برای جایگزینی هورمون تیروئید است که معمولاً برای کم‌کاری تیروئید مصرف می‌شود"
SRC2 = [{"title": "MedlinePlus", "url": "https://medlineplus.gov/druginfo/meds/a682461.html"},
        {"title": "NHS", "url": "https://www.nhs.uk/medicines/levothyroxine/"}]


class _FakeClient:
    def __init__(self, payload=None, boom=False):
        self.calls = []
        self.payload = payload
        self.boom = boom
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.boom:
            raise RuntimeError("network down")
        return SimpleNamespace(output_text=json.dumps(self.payload))


def _payload(**kw):
    base = {"recognized": True, "generic_name": "levothyroxine", "summary": GOOD, "sources": SRC2}
    return {**base, **kw}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    db._cache.clear()
    db._usage.clear()
    monkeypatch.delenv(db.DISABLED_ENV, raising=False)
    monkeypatch.delenv(db.DAILY_CAP_ENV, raising=False)


# --- guard 1: only the medicine NAME may leave ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "name, ok",
    [
        ("لووتیروکسین", True),
        ("Levothyroxine", True),
        ("امگا۳", True),
        ("گلیبن کلامید", True),
        ("متفورمین 500", True),
        ("name@example.com", False),
        ("https://evil.example/x", False),
        ("09121234567", False),  # a phone number is never a medicine name
        ("یک دو سه چهار پنج شش", False),  # a sentence, not a name
        ("", False),
        (None, False),
    ],
)
def test_only_a_short_medicine_name_may_leave(name, ok):
    assert (db.clean_name(name) is not None) == ok


def test_the_query_sent_is_the_name_only():
    client = _FakeClient(_payload())
    out = db.lookup("لووتیروکسین", "fa", client=client)
    assert out is not None and client.calls[0]["input"] == "لووتیروکسین"
    assert client.calls[0]["tools"] == [{"type": "web_search"}]


# --- guard 2: the sentence shown to the user is scrubbed -----------------------------------------------------------
@pytest.mark.parametrize(
    "text, ok",
    [
        (GOOD, True),
        ("Levothyroxine replaces the thyroid hormone and is usually used for an underactive thyroid", True),
        ("برای کم‌کاری تیروئید مصرف می‌شود، 100 mg هر روز", False),  # dose with unit
        ("معمولاً روزی دو بار و دوز آن را پزشک تعیین می‌کند", False),  # dose word
        ("برای تیروئید است؛ بیشتر بخوان https://x.example", False),  # link
        ("<script>alert(1)</script> برای تیروئید مصرف می‌شود", False),  # markup
        ("کوتاه", False),
        ("ا" * 300, False),
    ],
)
def test_summary_scrubbing(text, ok):
    assert (db.clean_summary(text) is not None) == ok


# --- guards 3/4: recognised or ask; the two-source rule ------------------------------------------------------------
def test_not_recognised_means_ask_for_the_exact_name_never_a_guess():
    brief = db.validate({"recognized": False, "generic_name": "", "summary": "", "sources": []})
    assert brief is not None and brief.recognized is False


def test_two_different_sites_are_stated_plainly_authorities_first():
    sources = [{"title": "x", "url": "https://some-blog.example/post"}, *SRC2]
    brief = db.validate(_payload(sources=sources), today="2026-11-18")
    assert brief.recognized and brief.two_source and brief.on_date == "2026-11-18"
    assert brief.hosts[0] in ("medlineplus.gov", "www.nhs.uk", "nhs.uk") or "gov" in brief.hosts[0]


def test_one_site_is_labelled_according_to_that_site():
    one = db.validate(_payload(sources=SRC2[:1]), today="2026-11-18")
    assert one.recognized and not one.two_source
    text = db.compose(one, "لووتیروکسین", "fa")
    assert "طبق" in text and "medlineplus.gov" in text and "2026-11-18" in text


def test_the_same_site_twice_is_one_source():
    same = [{"title": "a", "url": "https://medlineplus.gov/a"}, {"title": "b", "url": "https://medlineplus.gov/b"}]
    assert db.validate(_payload(sources=same)).two_source is False


def test_no_real_source_or_unusable_summary_is_never_stated_as_fact():
    assert db.validate(_payload(sources=[])) is None
    assert db.validate(_payload(sources=[{"title": "g", "url": "https://www.google.com/search?q=x"}])) is None
    assert db.validate(_payload(summary="برای تیروئید است، 50 mg")) is None


# --- guard 6: kill switch, cap, cache, fail-open -----------------------------------------------------------------
def test_kill_switch_cap_cache_and_failure_are_all_fail_open(monkeypatch):
    client = _FakeClient(_payload())
    first = db.lookup("لووتیروکسین", "fa", client=client)
    again = db.lookup("لووتیروکسین", "fa", client=client)
    assert first == again and len(client.calls) == 1  # 24 h cache

    monkeypatch.setenv(db.DISABLED_ENV, "1")
    assert db.lookup("متفورمین", "fa", client=client) is None
    monkeypatch.delenv(db.DISABLED_ENV)

    monkeypatch.setenv(db.DAILY_CAP_ENV, "0")
    assert db.lookup("آتورواستاتین", "fa", client=client) is None
    monkeypatch.delenv(db.DAILY_CAP_ENV)

    assert db.lookup("آسپرین", "fa", client=_FakeClient(boom=True)) is None
    leak = _FakeClient(_payload())
    assert db.lookup("name@example.com", "fa", client=leak) is None and leak.calls == []  # nothing left the server


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_compose_texts_carry_name_summary_sites_and_date(lang):
    plain = db.DrugBrief(True, "S-TEXT", "g", ("a.example", "b.example"), True, "2026-11-18")
    single = db.DrugBrief(True, "S-TEXT", "g", ("a.example",), False, "2026-11-18")
    for brief in (plain, single):
        text = db.compose(brief, "Zed", lang)
        assert "Zed" in text and "S-TEXT" in text and "a.example" in text and "2026-11-18" in text and "{" not in text
    after = sedi_copy.t("medication.chat.q.ask_reason_after_brief", lang)
    assert after.count("?") + after.count("؟") == 1 and mc._stage_of(after, lang) == "ask_reason"
    unrec = sedi_copy.t("medication.chat.q.unrecognised", lang, name="Zed")
    assert mc._stage_of(unrec, lang) == "unrecognised" and "Zed" in unrec
    assert unrec.count("?") + unrec.count("؟") == 1


# --- integration into the care interview -------------------------------------------------------------------------
REQUEST = "هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم"


def _rows(sedi_reply):
    now = datetime.utcnow()
    return [SimpleNamespace(user_message=REQUEST, sedi_response=sedi_reply, created_at=now)]


@pytest.fixture
def interview(monkeypatch):
    monkeypatch.setattr(mc, "history_available", lambda d, u: True)
    created = []
    monkeypatch.setattr(
        mc, "_create", lambda d, **kw: created.append(kw["name"]) or {"created": True, "duplicate": False, "name": kw["name"], "time": "14:00"}
    )
    return created


def _go(monkeypatch, sedi_reply, message):
    monkeypatch.setattr(mc, "_recent_turns", lambda d, u, n: _rows(sedi_reply))
    return mc.continue_interview(None, user_id=1, message=message, language="fa", timezone_name="Asia/Tehran")


def test_name_answer_gets_the_introduction_then_one_reason_question(monkeypatch, interview):
    brief = db.validate(_payload(), today="2026-11-18")
    monkeypatch.setattr(db, "lookup", lambda name, lang, client=None: brief)
    reply = _go(monkeypatch, sedi_copy.t("medication.chat.q.ask_name", "fa"), "لووتیروکسین")
    assert "کم‌کاری تیروئید" in reply and "medlineplus.gov" in reply and "همراهت هستم" in reply
    assert reply.count("؟") == 1 and mc._stage_of(reply, "fa") == "ask_reason" and interview == []
    assert mc._QUOTED.search(reply).group(1) == "لووتیروکسین"  # the next turn recovers the name from the first guillemets


def test_unknown_name_asks_for_spelling_or_a_photo_and_yes_does_not_search_again(monkeypatch, interview):
    calls = []

    def fake(name, lang, client=None):
        calls.append(name)
        return db.DrugBrief(recognized=False)

    monkeypatch.setattr(db, "lookup", fake)
    reply = _go(monkeypatch, sedi_copy.t("medication.chat.q.ask_name", "fa"), "ایکسزد")
    assert mc._stage_of(reply, "fa") == "unrecognised" and "عکس" in reply and calls == ["ایکسزد"]
    again = _go(monkeypatch, reply, "بله همین است")
    assert mc._stage_of(again, "fa") == "ask_reason" and calls == ["ایکسزد"]  # no second search for the same name


def test_no_result_or_kill_switch_keeps_the_plain_reason_question(monkeypatch, interview):
    monkeypatch.setattr(db, "lookup", lambda name, lang, client=None: None)
    reply = _go(monkeypatch, sedi_copy.t("medication.chat.q.ask_name", "fa"), "لووتیروکسین")
    assert mc._stage_of(reply, "fa") == "ask_reason" and "medlineplus" not in reply and interview == []


def test_confirmed_name_from_the_first_message_is_introduced_once(monkeypatch, interview):
    brief = db.validate(_payload(), today="2026-11-18")
    monkeypatch.setattr(db, "lookup", lambda name, lang, client=None: brief)
    reply = _go(monkeypatch, sedi_copy.t("medication.chat.q.confirm_name", "fa", name="لووتیروکسین"), "بله")
    assert "medlineplus.gov" in reply and mc._stage_of(reply, "fa") == "ask_reason"


# --- Codex review of PR 185 (P1 x2, P2 x2) ------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply, sent",
    [
        ("Metformin for my diabetes", "Metformin"),  # the reason never leaves
        ("متفورمین برای دیابت", "متفورمین"),
        ("Levothyroxine, I have thyroid problems", "Levothyroxine"),
        ("گلیبن کلامید", "گلیبن کلامید"),
        ("لووتیروکسین", "لووتیروکسین"),
        ("I have HIV", None),  # starts with a sentence: nothing is sent
        ("من دیابت دارم", None),
        ("0912 123 4567", None),  # phone with separators
        ("۰۹۱۲-۱۲۳-۴۵۶۷", None),
        ("name@example.com", None),
        ("diabetes", None),  # a health condition is not a medicine name
    ],
)
def test_only_the_leading_medicine_name_can_leave_the_server(reply, sent):
    assert db.name_from_reply(reply) == sent
    client = _FakeClient(_payload())
    db.lookup(db.name_from_reply(reply) or "I have HIV", "fa", client=client)
    for call in client.calls:  # whatever was sent is only the name
        assert call["input"] == sent


@pytest.mark.parametrize(
    "text",
    [
        "Take 2 tablets daily for pain relief",
        "Take 50 milligrams daily for thyroid replacement",
        "It is used for pain, one tablet twice a day",
        "هر روز دو قرص مصرف کنید برای درد",
        "برای کم‌کاری تیروئید روزانه مصرف می‌شود",
        "يؤخذ مرة يومياً لعلاج الغدة الدرقية",
        "برای درد ۵۰۰ میلی‌گرم مصرف می‌شود",
        "for pain 500 only",
    ],
)
def test_dosing_and_instructions_never_pass_the_summary_guard(text):
    assert db.clean_summary(text) is None
    assert db.validate(_payload(summary=text)) is None  # falls back to the plain reason question


def test_missing_or_malformed_recognition_is_a_failed_enrichment_not_a_negative_answer():
    assert db.validate({}) is None
    assert db.validate({"summary": GOOD, "sources": SRC2}) is None
    assert db.validate({"recognized": "yes", "summary": GOOD, "sources": SRC2}) is None
    assert db.validate({"recognized": False, "generic_name": "", "summary": "", "sources": []}).recognized is False
    assert db.lookup("لووتیروکسین", "fa", client=_FakeClient({})) is None  # empty API answer = fail-open


def test_correction_in_the_unrecognised_stage_advances_the_interview(monkeypatch, interview):
    seen = []

    def fake(name, lang, client=None):
        seen.append(name)
        return db.validate(_payload(), today="2026-11-18")

    monkeypatch.setattr(db, "lookup", fake)
    unrecognised = sedi_copy.t("medication.chat.q.unrecognised", "fa", name="ایکسزد")
    reply = _go(monkeypatch, unrecognised, "لووتیروکسین")
    assert seen == ["لووتیروکسین"] and mc._stage_of(reply, "fa") == "ask_reason" and "medlineplus.gov" in reply


def test_a_reply_that_is_a_sentence_is_not_stored_as_a_medicine_name(monkeypatch, interview):
    monkeypatch.setattr(db, "lookup", lambda name, lang, client=None: None)
    assert _go(monkeypatch, sedi_copy.t("medication.chat.q.ask_name", "fa"), "من دیابت دارم") is None
    assert mc._candidate_name("Metformin for my diabetes") == "Metformin"


@pytest.mark.parametrize(
    "stage_text",
    [
        sedi_copy.t("medication.chat.q.ask_name", "fa"),
        sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین"),
        sedi_copy.t("medication.chat.q.confirm_name", "fa", name="لووتیروکسین"),
    ],
)
@pytest.mark.parametrize(
    "message",
    ["فردا ساعت ۱۰ صبح جلسه‌ام را یادم بنداز", "Remind me tomorrow at 10am about my meeting", "یادم بنداز فردا ساعت ۸ شب برم باشگاه"],
)
def test_an_independent_reminder_request_is_never_swallowed_by_the_interview(monkeypatch, interview, stage_text, message):
    """Codex P2 (PR 185): it must keep its normal routing (None), and nothing is created or stored."""
    monkeypatch.setattr(db, "lookup", lambda name, lang, client=None: None)
    assert _go(monkeypatch, stage_text, message) is None
    assert interview == []


def test_a_reason_that_mentions_a_time_without_reminder_words_still_completes_the_interview(monkeypatch, interview):
    ask_reason = sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")
    reply = _go(monkeypatch, ask_reason, "برای کم‌کاری تیروئید؛ صبح‌ها ساعت ۸ ناشتا می‌خورمش")
    assert interview == ["لووتیروکسین"] and reply and "14:00" in reply
