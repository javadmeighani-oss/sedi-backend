"""R-068 (step 2A): the commitment loop - Sedi keeps what she promises and the user is never left.

Matrix: topics x languages (extraction), attempts x languages (copy), ladder (never above 2 days), answers
(done / not done + reason / later), consent, supersede, lock-screen safety, wiring.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz

from backend.app import models, sedi_copy
from backend.app.services.gate4.notification_context import ALLOWED_CONTEXT_JSON_KEYS, sanitize_notification_context
from backend.app.services.gate4.push_payload import PLAN_FOLLOWUP_TEMPLATE_KEYS
from backend.app.services.i10 import commitment_followup as cf
from backend.app.services.i10.contextual_followup_task_meta import BoundedFollowUpMeta, pack_description, parse_bounded_meta
from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks
from backend.app.services.i7 import user_done
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

TEHRAN = pytz.timezone("Asia/Tehran")

# (language, a reply with a step + the follow-up promise, expected coarse domain, a marker that must be in the step)
_REPLIES = [
    ("fa", "وقتی بیدار شدی ساعت را چک نکن و در نور کم کار آرامی انجام بده. امشب همین روش را امتحان کن. فردا درباره‌اش می‌پرسم.", "sleep", "نور کم"),
    ("fa", "امروز بعدازظهر ده دقیقه پیاده‌روی کن و دو لیوان آب بیشتر بنوش. فردا بگو چطور پیش رفت.", "exercise", "پیاده‌روی"),
    ("fa", "هر ساعت دو دقیقه بایست و کمرت را بکش. این بار فشار ستون فقرات را کم می‌کند. دفعه‌ی بعد ازت می‌پرسم.", "pain", "کمرت"),
    ("fa", "امشب ده دقیقه تنفس آهسته انجام بده تا استرس روز پایین بیاید. فردا صبح خبر بگیرم که چطور بود؟ فردا درباره‌اش می‌پرسم.", "mood", "تنفس"),
    ("en", "Walk for ten minutes after lunch and drink two more glasses of water. I will ask you about it tomorrow.", "exercise", "Walk"),
    ("en", "Keep the same wake-up time and avoid checking the clock at night. Tell me tomorrow how many times you woke up.", "sleep", "wake-up"),
    ("ar", "اترك الهاتف قبل النوم بنصف ساعة واجعل وقت الاستيقاظ ثابتاً. سأسألك عنها غداً.", "sleep", "النوم"),
    ("ar", "امشِ عشر دقائق بعد الغداء. هذا يخفف التوتر ويحسّن الهضم. غداً أخبرني كيف سارت الأمور.", "exercise", "امشِ"),
]


@pytest.fixture(autouse=True)
def _flag_and_policy():
    with patch(
        "backend.app.services.i10.contextual_followup_worker.contextual_followup_enabled", return_value=True
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy", return_value=(True, {})
    ), patch(
        "backend.app.services.notification_runtime.quiet_hours.is_within_quiet_hours", return_value=False
    ):
        yield


# ---- extraction: general over topics and languages ------------------------------------------------------------------
@pytest.mark.parametrize("lang,reply,domain,marker", _REPLIES)
def test_the_promise_and_the_step_before_it_are_extracted(lang, reply, domain, marker):
    found = cf.extract_commitment(reply, lang)
    assert found is not None
    assert marker in found.step and len(found.step) <= cf.MAX_STEP_CHARS + 1
    assert cf.commitment_domain(found.step) == domain
    assert not found.step.rstrip().endswith(("?", "؟"))  # a step is never a question


@pytest.mark.parametrize("reply", [
    "سه شب بی‌خوابی فرساینده است. امشب خودت را مجبور نکن.",  # no promise
    "Short walks help. Drink water daily.",
    "درد قفسه سینه جدی است. همین حالا به اورژانس زنگ بزن. فردا درباره‌اش می‌پرسم.",  # severe: the safety floor owns it
    "Chest pain and shortness of breath need emergency care. I will ask you about it tomorrow.",
    "فردا می‌پرسم.",  # a promise with no step and fewer than 4 words
    "",
])
def test_no_promise_a_severe_reply_or_an_empty_step_creates_no_commitment(reply):
    assert cf.extract_commitment(reply, "fa") is None


def test_a_promise_only_reply_with_enough_words_becomes_its_own_step_and_questions_are_not_steps():
    found = cf.extract_commitment("فردا بگو چند بار از خواب بیدار شدی و چقدر طول کشید.", "fa")
    assert found and "بیدار شدی" in found.step
    found = cf.extract_commitment("آیا امروز ورزش کردی؟ امشب ده دقیقه پیاده‌روی کن. فردا درباره‌اش می‌پرسم.", "fa")
    assert found and "ورزش کردی" not in found.step and "پیاده‌روی" in found.step


def test_a_long_step_is_shortened_at_a_word_boundary():
    long_step = "این یک جمله‌ی خیلی بلند است " * 12 + "تا آخر."
    found = cf.extract_commitment(long_step + " فردا درباره‌اش می‌پرسم.", "fa")
    assert found and len(found.step) <= cf.MAX_STEP_CHARS + 1


# ---- the ladder: the interval NEVER exceeds 2 days, every attempt changes approach -------------------------------
def test_the_interval_never_exceeds_two_days():
    assert [cf.interval_days_after(n) for n in range(1, 12)] == [1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
    assert max(cf.interval_days_after(n) for n in range(1, 200)) == 2


def test_every_attempt_changes_the_approach():
    assert [cf.approach_for(n) for n in range(1, 9)] == ["first", "nudge", "why", "lighter", "time", "why", "lighter", "time"]


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_each_attempt_has_its_own_wording_and_the_third_onwards_rotates(lang):
    bodies = [cf.commitment_copy(lang, n)[1] for n in range(1, 8)]
    assert len(set(bodies[:5])) == 5  # 1, 2 and three different approaches for 3, 4, 5
    assert bodies[5] == bodies[2] and bodies[6] == bodies[3]  # then the three approaches rotate
    assert cf.commitment_copy(lang, 1)[0] == sedi_copy.t("commitment.title", lang)


_ILLNESS = ("دیابت", "سرطان", "افسردگی", "فشار خون", "diabet", "cancer", "depress", "hypertension", "سكري", "اكتئاب")


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_lock_screen_text_never_names_an_illness_or_the_step(lang):
    for attempt in range(1, 8):
        title, body = cf.commitment_copy(lang, attempt)
        low = (title + " " + body).lower()
        assert not any(word in low for word in _ILLNESS)
        assert "{" not in body


# ---- time: always 09:00 local ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("hour_utc", [0, 5, 12, 20, 23])
@pytest.mark.parametrize("days", [1, 2])
def test_the_follow_up_is_always_nine_oclock_in_the_users_timezone(db, hour_utc, days):
    u = _user(db, f"+1777007{hour_utc:02d}{days}", tz="Asia/Tehran")
    base = datetime(2026, 11, 5, hour_utc, 17, tzinfo=timezone.utc)
    due = cf.follow_up_time(db, u.id, base_utc=base, days_ahead=days)
    local = pytz.utc.localize(due).astimezone(TEHRAN)
    assert (local.hour, local.minute) == (9, 0)
    assert local.date() == base.astimezone(TEHRAN).date() + timedelta(days=days)


# ---- meta: backward compatible --------------------------------------------------------------------------------------
def test_the_meta_roundtrips_and_a_legacy_blob_is_unchanged():
    meta = BoundedFollowUpMeta(follow_up_kind="commitment", attempt=3, domain="sleep", chain_id=7, approach="why", reason="no_time")
    packed = pack_description(None, meta)
    assert parse_bounded_meta(packed)[1] == meta
    legacy = pack_description("x", BoundedFollowUpMeta(follow_up_kind="care_checkin"))
    assert '"attempt"' not in legacy and '"domain"' not in legacy  # old rows and new default rows stay byte-identical
    assert parse_bounded_meta(legacy)[1].attempt == 1


# ---- DB: capture, supersede, consent --------------------------------------------------------------------------------
def _fa_user(db, phone, consent=True):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    db.commit()
    if consent:
        _seed_consent(db, u.id)
    ensure_self_subject_for_account(db, u.id, commit=True)
    return u


_SLEEP = "وقتی بیدار شدی ساعت را چک نکن و در نور کم کار آرامی انجام بده. فردا درباره‌اش می‌پرسم."
_WALK = "امروز بعدازظهر ده دقیقه پیاده‌روی کن. فردا درباره‌اش می‌پرسم."
_FOOD = "امروز دو لیوان آب بیشتر بنوش. فردا درباره‌اش می‌پرسم."
_PAIN = "هر ساعت کمرت را بکش و دو دقیقه بایست. فردا درباره‌اش می‌پرسم."


def test_a_promise_in_the_reply_becomes_a_tracked_task_due_tomorrow_at_nine(db):
    u = _fa_user(db, "+17770071001")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    assert task is not None and cf.is_commitment(task) and task.status == "open"
    meta = cf.meta_of(task)
    assert (meta.attempt, meta.domain, meta.chain_id, meta.approach) == (1, "sleep", task.id, "first")
    local = pytz.utc.localize(task.due_at).astimezone(TEHRAN)
    assert local.hour == 9 and local.date() == datetime.now(timezone.utc).astimezone(TEHRAN).date() + timedelta(days=1)
    assert "نور کم" in task.title


def test_without_memory_consent_nothing_is_stored(db):
    u = _fa_user(db, "+17770071002", consent=False)
    assert cf.capture_from_reply(db, u.id, _SLEEP, "fa") is None
    assert db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).count() == 0


def test_a_severe_user_message_never_creates_a_commitment(db):
    u = _fa_user(db, "+17770071003")
    assert cf.capture_from_reply(db, u.id, _SLEEP, "fa", user_message="درد قفسه سینه و تنگی نفس دارم") is None


def test_a_new_commitment_replaces_the_older_one_on_the_same_subject_and_at_most_three_chains_stay_open(db):
    u = _fa_user(db, "+17770071004")
    first = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    second = cf.capture_from_reply(db, u.id, "بعد از ناهار نرم‌شی کن و بیشتر بایست. فردا درباره‌اش می‌پرسم. ", "fa")
    db.refresh(first)
    sleep_again = cf.capture_from_reply(db, u.id, "ساعت بیدارشدنت را ثابت نگه دار و شب‌ها زودتر بخواب. فردا درباره‌اش می‌پرسم.", "fa")
    db.refresh(first)
    assert first.status == "cancelled" and sleep_again.status == "open"
    for text in (_FOOD, _PAIN):
        cf.capture_from_reply(db, u.id, text, "fa")
    open_chains = {cf.meta_of(t).chain_id for t in cf._commitment_tasks(db, u.id)}
    assert len(open_chains) <= cf.MAX_OPEN_CHAINS
    assert second is not None


# ---- DB: delivery + the ladder + the answers ------------------------------------------------------------------------
def _send(db, task):
    now = task.due_at + timedelta(minutes=1)
    assert process_due_follow_up_tasks(db, now=now) == 1
    db.refresh(task)
    return db.query(models.Notification).filter(models.Notification.user_id == task.user_id).order_by(models.Notification.id.desc()).first()


def _chain(db, task):
    cid = cf.meta_of(task).chain_id or task.id
    rows = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == task.user_id).order_by(models.CareFollowUpTask.id).all()
    return [t for t in rows if cf.is_commitment(t) and (cf.meta_of(t).chain_id or t.id) == cid]


def test_the_follow_up_is_delivered_through_the_framework_and_the_next_attempt_is_scheduled_at_once(db):
    u = _fa_user(db, "+17770072001")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    assert notif.template_key == "commitment_follow_up" and notif.category == "care_follow_up" and notif.i10_policy_decision_id is not None
    assert notif.title == sedi_copy.t("commitment.title", "fa") and notif.body == sedi_copy.t("commitment.body.1", "fa")
    assert json.loads(notif.context_json)["commitment_task_id"] == str(task.id)
    assert task.status == "notified"
    chain = _chain(db, task)
    assert [cf.meta_of(t).attempt for t in chain] == [1, 2] and chain[1].status == "open"
    gap = pytz.utc.localize(chain[1].due_at).astimezone(TEHRAN).date() - pytz.utc.localize(task.due_at).astimezone(TEHRAN).date()
    assert gap == timedelta(days=1)


def test_silence_is_followed_up_every_two_days_at_most_with_a_new_approach_each_time(db):
    u = _fa_user(db, "+17770072002")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    bodies, gaps, current = [], [], task
    for _ in range(6):  # six unanswered follow-ups in a row: the loop never stops
        notif = _send(db, current)
        bodies.append(notif.body)
        nxt = max((t for t in _chain(db, current) if t.status == "open"), key=lambda t: cf.meta_of(t).attempt)
        gaps.append((pytz.utc.localize(nxt.due_at).astimezone(TEHRAN).date() - pytz.utc.localize(current.due_at).astimezone(TEHRAN).date()).days)
        current = nxt
    assert gaps == [1, 2, 2, 2, 2, 2] and max(gaps) <= 2
    assert bodies[0] == sedi_copy.t("commitment.body.1", "fa") and bodies[1] == sedi_copy.t("commitment.body.2", "fa")
    assert len(set(bodies)) >= 5  # the wording changes; only the rotation repeats after the third approach


def _answer(db, task, notif, **payload):
    return cf.handle_commitment_answer(db, notification=notif, actor_user_id=task.user_id, payload=payload)


def test_done_ends_the_chain_and_i7_learns_it(db):
    u = _fa_user(db, "+17770073001")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    _answer(db, task, notif, reaction="interact", action_id="done")
    db.expire_all()
    chain = _chain(db, task)
    assert [t.status for t in chain] == ["done", "cancelled"]
    today = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    assert user_done.done_counts_for_day(db, u.id, today).get("commitment") == 1


def test_not_done_with_a_reason_makes_the_next_follow_up_lighter_and_due_tomorrow(db):
    u = _fa_user(db, "+17770073002")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    _answer(db, task, notif, reaction="interact", action_id="plan_not_done", reason="no_time")
    db.expire_all()
    answered, pending = _chain(db, task)
    assert answered.status == "cancelled" and cf.meta_of(answered).reason == "no_time"
    assert pending.status == "open" and cf.meta_of(pending).approach == "lighter"
    local = pytz.utc.localize(pending.due_at).astimezone(TEHRAN)
    assert local.hour == 9 and local.date() == datetime.now(timezone.utc).astimezone(TEHRAN).date() + timedelta(days=1)


def test_later_never_ends_the_loop_and_never_moves_it_earlier(db):
    u = _fa_user(db, "+17770073003")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    before = max((t for t in _chain(db, task) if t.status == "open"), key=lambda t: t.id).due_at
    _answer(db, task, notif, reaction="interact", action_id="later")
    db.expire_all()
    pending = [t for t in _chain(db, task) if t.status == "open"]
    assert len(pending) == 1 and pending[0].due_at >= before


def test_a_reaction_that_is_not_an_answer_only_records_and_keeps_the_chain(db):
    u = _fa_user(db, "+17770073004")
    task = cf.capture_from_reply(db, u.id, _SLEEP, "fa")
    notif = _send(db, task)
    _answer(db, task, notif, reaction="open", action_id="open_chat")
    db.expire_all()
    assert [t.status for t in _chain(db, task)] == ["notified", "open"]  # talking to Sedi does not end the follow-up


# ---- wiring contracts ---------------------------------------------------------------------------------------------------
def test_the_tray_buttons_the_context_key_the_router_and_the_brain_are_wired():
    assert "commitment_follow_up" in PLAN_FOLLOWUP_TEMPLATE_KEYS
    assert "commitment_task_id" in ALLOWED_CONTEXT_JSON_KEYS
    assert sanitize_notification_context({"commitment_task_id": "5", "secret": "x"}) == {"commitment_task_id": "5"}
    app = Path(__file__).resolve().parents[1] / "app"
    router = (app / "routers" / "notifications.py").read_text(encoding="utf-8")
    assert router.index("handle_commitment_answer") < router.index("handle_coaching_done_for_notification")
    brain = (app / "core" / "conversation" / "brain.py").read_text(encoding="utf-8")
    assert "capture_from_reply(self.db, user_id, sedi_response, lang, user_message=user_message)" in brain


@pytest.mark.parametrize("needle,lang", [
    ("end the reply with ONE short follow-up promise", "en"),
    ("وعده‌ی پیگیری", "fa"),
    ("جملة وعد متابعة", "ar"),
])
def test_the_prompts_ask_for_the_follow_up_promise_sentence(needle, lang):
    from backend.app.core.conversation import persona_policy_v1 as pp

    prompt = {"en": pp._SYSTEM_PROMPT_EN, "fa": pp._SYSTEM_PROMPT_FA, "ar": pp._SYSTEM_PROMPT_AR}[lang]
    assert needle in prompt
