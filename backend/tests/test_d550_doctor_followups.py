"""D-550 (Javad's phone test 2026-11-27): after a doctor introduction the follow-ups must stay on the doctor path, never reach the free model.

- DEBT-108 «introduce them AGAIN» («تماس نگرفتم میخوام دوباره معرفی کنی») = the SAME five, same lines, same links (R-120 am.3 bubbles).
- DEBT-109 «۵ تا جدید معرفی کن» and every other wording of «new / fresh / other than these» = the NEXT five (R-116 am.1).
- DEBT-110 a short go-ahead («خوب انجام بده») continues the ask before it; a generated «I have no live access / send me the results» inside a
  doctor talk is replaced by the concrete way forward (R-089 / R-114: never «I cannot»).

Real session harness of test_r116_next_five (in-memory SQLite + synthetic Paziresh24 pages, eight dermatologists in Shiraz)."""
import pytest

from backend.app import sedi_copy
from backend.app.core.conversation.memory import ConversationMemory
from backend.app.services.i5 import provider_next as pn
from backend.tests.test_r108_care_loop_e2e import _fixed_timezone, db, user  # noqa: F401  (real-session fixtures)
from backend.tests.test_r116_next_five import _names, _readers, _turn, orch  # noqa: F401  (same pages + orchestrator)

_FIRST = "یک متخصص پوست در شیراز معرفی کن"


# --- the wording matrix (intent x language; and what must NOT trigger) -----------------------------------------------------------------------
@pytest.mark.parametrize("message", [
    "۵ تا جدید معرفی کن", "پنج تا جدید", "پنج تا دکتر جدید بفرست", "دکترای جدید معرفی کن", "چند تا پزشک تازه بفرست", "غیر از اینا کسی هست؟",
    "عوضشون کن", "لیست جدید بده", "دوباره ۵ تا جدید معرفی کن",
    "أطباء جدد من فضلك", "قائمة جديدة",
    "five new doctors please", "show me new ones", "different doctors please",
])
def test_new_ones_are_the_next_five_in_three_languages(message):
    assert pn.wants_next(message), message
    assert not pn.wants_again(message), message


@pytest.mark.parametrize("message", [
    "تماس نگرفتم میخوام دوباره معرفی کنی", "دوباره معرفی کن", "همونا رو دوباره بفرست", "لیست قبلی رو بفرست", "یه بار دیگه اسماشونو بگو",
    "مجددا معرفی کن", "أعد القائمة", "نفس القائمة من فضلك", "send the list again", "show them again please", "same doctors please",
])
def test_again_is_the_same_list_in_three_languages(message):
    assert pn.wants_again(message), message
    assert not pn.wants_next(message), message


@pytest.mark.parametrize("message", ["خوب انجام بده", "باشه بگرد", "آره پیدا کن", "انجامش بده لطفا", "جست‌وجو کن", "نعم ابحث", "go ahead", "ok do it"])
def test_a_short_go_ahead_is_recognised(message):
    assert pn.confirms_search(message), message


@pytest.mark.parametrize("message", [
    "دوباره سرم درد گرفت", "انجام دادم", "نمیخوام دوباره معرفی کنی", "باشه", "قرصمو خوردم", "I did it again", "",
    "سرم درد میکنه از دیروز و میخوام بدونم چیکار کنم که بهتر بشه و دوباره اینطوری نشه",
])
def test_ordinary_messages_are_neither_again_nor_new_nor_a_go_ahead(message):
    assert not pn.wants_again(message) and not pn.wants_next(message) and not pn.confirms_search(message), message


@pytest.mark.parametrize("reply, claims", [
    ("برای تهران‌پارس جست‌وجو می‌کنم. اما در این گفت‌وگو دسترسی زنده به فهرست پزشکان ندارم.", True),
    ("نتایج جست‌وجویی را که پیدا کرده‌ای بفرست تا مرتب کنیم.", True),
    ("نمی‌خواهم پنج نام یا شمارهٔ تأییدنشده بدهم.", True),
    ("I don't have live access to the doctors list.", True),
    ("لا أملك الوصول إلى قائمة الأطباء.", True),
    ("دکتر حاتمی در تهران‌پارس مطب دارد.", False),
    ("برای خواب بهتر، هر شب ساعت ثابتی بخواب.", False),
])
def test_no_access_claims_are_detected(reply, claims):
    assert pn.claims_no_access(reply) is claims


# --- the real conversation (the pilot sequence) -------------------------------------------------------------------------------------------------
def test_again_replays_the_same_five_with_the_same_links(db, user, orch):
    first = _turn(orch, user, _FIRST)
    again = _turn(orch, user, "تماس نگرفتم میخوام دوباره معرفی کنی")
    assert _names(again) == _names(first) and len(again.links) == 5                                            # the same five, same order
    assert [link["url"] for link in again.links] == [link["url"] for link in first.links]                     # the same openable pages
    assert again.message.startswith(sedi_copy.t("care_nav.again.intro", "fa"))
    assert again.message.count("•") == 5 and again.message.endswith(sedi_copy.t("care_nav.again.close", "fa"))
    assert "GEN" not in again.message                                                                          # never the free model


def test_after_again_the_new_ones_are_still_the_next_five(db, user, orch):
    first = _turn(orch, user, _FIRST)
    _turn(orch, user, "دوباره معرفی کن")
    new = _turn(orch, user, "۵ تا جدید معرفی کن")
    assert len(_names(new)) == 3 and not set(_names(new)) & set(_names(first))                                 # the remaining three, no repeat
    assert new.message.startswith(sedi_copy.t("care_nav.next.intro", "fa"))


def test_a_go_ahead_continues_the_next_five_ask_before_it(db, user, orch):
    first = _turn(orch, user, _FIRST)
    # the pilot: the «new ones» turn had been answered by the model with an offer to search; the go-ahead must run THAT search
    ConversationMemory(db).save_conversation(user.id, "۵ تا جدید معرفی کن", "برای معرفی پنج متخصص جدید باید جست‌وجو و بررسی کنم.", "fa")
    go = _turn(orch, user, "خوب انجام بده")
    assert len(_names(go)) == 3 and not set(_names(go)) & set(_names(first))
    assert "GEN" not in go.message


def test_a_go_ahead_after_an_again_ask_replays_the_list(db, user, orch):
    first = _turn(orch, user, _FIRST)
    ConversationMemory(db).save_conversation(user.id, "دوباره معرفی کن", "باشه.", "fa")
    go = _turn(orch, user, "باشه بگرد")
    assert _names(go) == _names(first)


def test_without_an_introduction_again_and_go_ahead_are_not_special(db, user, orch):
    assert pn.again_reply(db, user.id, "دوباره معرفی کن", "fa") is None
    assert pn.next_request(db, user.id, "خوب انجام بده", "fa") is None


def test_again_is_not_replayed_after_a_newer_other_subject(db, user, orch):
    _turn(orch, user, _FIRST)
    ConversationMemory(db).save_conversation(user.id, "برای شام یک غذای سبک و سالم پیشنهاد بده", "سوپ سبزیجات…", "fa")
    assert pn.again_reply(db, user.id, "دوباره معرفی کن", "fa") is None


def test_the_no_access_guard_only_acts_inside_an_open_doctor_talk(db, user, orch):
    bad = "در این گفت‌وگو دسترسی زنده به فهرست پزشکان ندارم؛ نتایج جست‌وجو را بفرست."
    assert pn.guard_no_access(db, user.id, bad, "fa") == bad                                                    # no doctor talk: untouched
    _turn(orch, user, _FIRST)
    fixed = pn.guard_no_access(db, user.id, bad, "fa")
    assert fixed == sedi_copy.t("care_nav.no_access.redirect", "fa") and not pn.claims_no_access(fixed)
    fine = "دکتر ۰۱ نزدیک‌ترین مطب به توست."
    assert pn.guard_no_access(db, user.id, fine, "fa") == fine


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_redirect_names_phrases_that_really_work(lang):
    """The redirect tells the user what to write: both phrases it quotes must be recognised by the deterministic path (no dead end)."""
    import re

    quoted = re.findall(r"«([^»]+)»", sedi_copy.t("care_nav.no_access.redirect", lang))
    assert len(quoted) == 2
    assert pn.wants_next(quoted[0]) and pn.wants_again(quoted[1])


# --- Codex round 1 (PR 232) ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("message", ["یک لیست جدید غذا بده", "لیست جدید غذاهای سالم", "give me a new list of meals", "a new list of exercises please"])
def test_p2_a_new_list_of_something_else_is_not_the_next_doctors(db, user, orch, message):
    _turn(orch, user, _FIRST)
    assert pn.next_request(db, user.id, message, "fa") is None


def test_p2_a_generic_new_list_continues_the_doctors_only_while_the_doctor_talk_is_open(db, user, orch):
    _turn(orch, user, _FIRST)
    assert pn.next_request(db, user.id, "لیست جدید بده", "fa") is not None
    ConversationMemory(db).save_conversation(user.id, "برای شام یک غذای سبک و سالم پیشنهاد بده", "سوپ سبزیجات…", "fa")
    assert pn.next_request(db, user.id, "لیست جدید بده", "fa") is None
    assert pn.next_request(db, user.id, "۵ تا دکتر جدید معرفی کن", "fa") is not None  # an explicit doctor ask still continues


def test_p2_the_guard_leaves_the_first_unrelated_question_alone(db, user, orch):
    _turn(orch, user, _FIRST)
    reply = "به اطلاعات زنده دسترسی ندارم؛ نتایج جست‌وجو را بفرست."
    assert pn.guard_no_access(db, user.id, reply, "fa", user_message="هوای امروز تهران چطوره؟") == reply
    assert pn.guard_no_access(db, user.id, reply, "fa", user_message="خوب انجام بده") == sedi_copy.t("care_nav.no_access.redirect", "fa")
