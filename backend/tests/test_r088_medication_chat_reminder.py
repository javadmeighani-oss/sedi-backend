"""R-088 / R-091 (D-382..D-387) package A1 v2: pill reminder in chat = care interview BEFORE any time is set.

Offline and DB-free: the owner write (_create) and the conversation (_recent_turns) are stubbed; detection, name parsing, the
stage markers and the interview state machine run for real. Matrix: phrasing x language x stage.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.medication_care import chat_reminder as mc

TZ = "Asia/Tehran"
REQUEST = "هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم"


@pytest.fixture(autouse=True)
def _no_real_web_search(monkeypatch):
    """The interview tests never reach the real web: the drug introduction (package A2) is stubbed to «no result»."""
    from backend.app.services.medication_care import drug_brief

    monkeypatch.setattr(drug_brief, "lookup", lambda name, lang, client=None: None)


@pytest.mark.parametrize(
    "text",
    [
        REQUEST,
        "هر شب ساعت ۹ یادم بنداز ویتامین D بخورم",
        "یه یادآور بذار برای داروی فشارم هر روز ساعت ۸",
        "قرصم رو هر روز ساعت ۲ بخورم",
        "remind me every day at 8 to take my pill",
        "remind me daily to take my medication at 9pm",
        "كل يوم الساعة 8 ذكّرني بدوائي",
    ],
)
def test_pill_reminders_are_detected(text):
    assert mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text",
    ["یادم بنداز فردا برم داروخانه", "یادم بنداز فردا ساعت ۱۰ جلسه دارم", "remind me to go to the pharmacy tomorrow", "هر روز ساعت ۶ ورزش یادم بنداز"],
)
def test_other_reminders_are_not_medication(text):
    assert not mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "Remind me every day at 9pm to buy pills",
        "remind me daily at 8 to refill my medication",
        "هر روز ساعت ۹ شب یادم بنداز قرص بخرم",
        "هر ماه یادم بنداز داروهام رو بشمارم",
        "كل يوم الساعة 9 ذكّرني بشراء الحبوب",
    ],
)
def test_pill_errands_stay_on_the_generic_event_route(text):
    """Codex P2 (PR 185): buying / counting / refilling pills is not an intake schedule."""
    assert not mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text",
    ["remind me every day at 9pm to take the pills I bought", "remind me every day at 9pm to take my pills after the refill", "هر شب ساعت ۹ یادم بنداز قرصی که خریدم بخورم"],
)
def test_an_intake_word_keeps_the_medication_route(text):
    assert mc.is_medication_text(text)


@pytest.mark.parametrize("perms,expected", [(("memory.read", "memory.write"), True), (("memory.read",), False), (("memory.write",), False), ((), False)])
def test_interview_needs_read_and_write_consent(monkeypatch, perms, expected):
    """Codex P2 (PR 185): a read-only consent cannot save the interview question, so the interview must not start."""
    from backend.app.services.i6 import consent_service

    monkeypatch.setattr(consent_service, "has_permission", lambda db, uid, perm: perm in perms)
    assert mc.history_available(None, 1) is expected


@pytest.mark.parametrize(
    "text, name",
    [
        ("هر روز ساعت ۸ قرص متفورمین بخورم", "متفورمین"),
        (REQUEST, None),
        ("هر روز ساعت ۸ داروی فشارم بخورم", None),
        ("remind me daily to take Levothyroxine pill", "Levothyroxine"),
        ("remind me daily to take my vitamin", None),
        ("remind me daily to take my pill", None),
        ("هر روز ساعت ۸ کپسول امگا۳ بخورم", "امگا۳"),
    ],
)
def test_pill_name_extraction(text, name):
    assert mc.extract_pill_name(text) == name


def test_weekly_days_map_to_monday_zero():
    assert mc._days_of_week("FREQ=WEEKLY;BYDAY=MO,TH") == "0,3"
    assert mc._days_of_week("FREQ=DAILY") is None
    assert mc._is_recurring("FREQ=DAILY") and mc._is_recurring("FREQ=WEEKLY;BYDAY=FR")
    assert not mc._is_recurring(None)


@pytest.mark.parametrize("text", ["همین ساعت فقط", "فقط یادم بنداز", "بدون سوال", "just remind me", "no questions please", "same time"])
def test_insistence_phrases(text):
    assert mc.insists(text)
    assert not mc.insists("برای فشار خون مصرف می‌کنم")


# --- the interview texts: ONE question, stage markers, exact name / photo ----------------------------------------
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_every_stage_text_asks_one_question_and_is_recognised_next_turn(lang):
    ask_name = sedi_copy.t("medication.chat.q.ask_name", lang)
    confirm = sedi_copy.t("medication.chat.q.confirm_name", lang, name="Zed")
    reason = sedi_copy.t("medication.chat.q.ask_reason", lang, name="Zed")
    for text, stage in ((ask_name, "ask_name"), (confirm, "confirm_name"), (reason, "ask_reason")):
        assert text.count("?") + text.count("؟") == 1  # one question per reply (R-020/R-067)
        assert mc._stage_of(text, lang) == stage
        assert "{" not in text
    assert "photo" in ask_name.lower() or "عکس" in ask_name or "صورة" in ask_name  # exact name / photo of the box (R-088 am.3)
    assert "Zed" in confirm and "Zed" in reason
    # a created-reminder text is never mistaken for a question stage, nor is small talk
    assert mc._stage_of(sedi_copy.t("medication.chat.created.after_reason", lang, name="Zed", time="14:00"), lang) is None
    assert mc._stage_of("سلام، امروز چطوری؟", lang) is None


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_created_texts_carry_time_name_and_the_open_door(lang):
    for key in ("medication.chat.created.after_reason", "medication.chat.created.insist_named"):
        text = sedi_copy.t(key, lang, name="Zed", time="14:00")
        assert "14:00" in text and "Zed" in text and "{" not in text
    insist = sedi_copy.t("medication.chat.created.insist_named", lang, name="Zed", time="14:00")
    assert insist.count("?") + insist.count("؟") == 0  # not a question, not a menu of offers (R-049)
    unnamed = sedi_copy.t("medication.chat.created.insist_unnamed", lang, name="", time="14:00")
    assert "14:00" in unnamed and "{" not in unnamed


# --- turn 1 -----------------------------------------------------------------------------------------------------
class _Draft(SimpleNamespace):
    pass


def _draft(rule="FREQ=DAILY"):
    return _Draft(starts_at_local=datetime(2026, 11, 18, 14, 0), recurrence_rule=rule)


@pytest.fixture
def owner(monkeypatch):
    writes = []

    def fake_create(db, *, user_id, draft, language, timezone_name, name):
        writes.append(name)
        return {"kind": "medication", "created": True, "duplicate": False, "name": name or mc.provisional_name(language),
                "named": bool(name), "time": "14:00", "days": None}

    monkeypatch.setattr(mc, "_create", fake_create)
    return writes


def test_first_turn_asks_before_setting_any_time(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    out = mc.start_interview(None, user_id=1, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    assert out["created"] is False and out["interview"] == "ask_name" and owner == []
    named = mc.start_interview(None, user_id=1, message="هر روز ساعت ۸ قرص متفورمین بخورم", draft=_draft(), language="fa", timezone_name=TZ)
    assert named["interview"] == "confirm_name" and named["name"] == "متفورمین" and owner == []
    text = mc.confirmation(out, "fa", "WHEN")
    assert "کدام دارو را مصرف می‌کنی" in text and "یادت می‌اندازم" not in text  # no «I will remind you» before knowing


def test_insistence_creates_at_once_with_the_open_door(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    out = mc.start_interview(None, user_id=1, message="هر روز ساعت ۲ قرص بخورم همین ساعت", draft=_draft(), language="fa", timezone_name=TZ)
    assert out["created"] and out["flow"] == "insist" and owner == [None]
    assert "مراقب سلامتی" in mc.confirmation(out, "fa", "WHEN")


def test_without_consent_the_request_is_created_at_once_and_the_pill_is_asked(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: False)
    out = mc.start_interview(None, user_id=1, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    assert out["created"] and out["flow"] == "no_history" and owner == [None]
    assert "کدام قرص" in mc.confirmation(out, "fa", "هر روز ساعت ۱۴:۰۰")


def test_one_off_non_medication_and_kill_switch_keep_the_generic_path(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    assert mc.start_interview(None, user_id=1, message="فردا ساعت ۲ قرص بخورم", draft=_draft(None), language="fa", timezone_name=TZ) is None
    assert mc.start_interview(None, user_id=1, message="هر روز ساعت ۶ ورزش یادم بنداز", draft=_draft(), language="fa", timezone_name=TZ) is None
    monkeypatch.setenv(mc.DISABLED_ENV, "1")
    assert mc.start_interview(None, user_id=1, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ) is None
    assert owner == []


# --- the next turns ---------------------------------------------------------------------------------------------
def _turns(*pairs, request=REQUEST):
    """Newest first: [(user, sedi), ...] after the original request turn."""
    now = datetime.utcnow()
    rows = [SimpleNamespace(user_message=u, sedi_response=s, created_at=now) for u, s in pairs]
    rows.append(SimpleNamespace(user_message=request, sedi_response=sedi_copy.t("medication.chat.q.ask_name", "fa"), created_at=now))
    return rows


def _go(monkeypatch, rows, message, lang="fa", consent=True):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: consent)
    monkeypatch.setattr(mc, "_recent_turns", lambda db, uid, now: rows)
    return mc.continue_interview(None, user_id=1, message=message, language=lang, timezone_name=TZ)


def test_name_answer_leads_to_the_reason_question_and_still_no_reminder(monkeypatch, owner):
    reply = _go(monkeypatch, _turns(), "لووتیروکسین")
    assert reply and "لووتیروکسین" in reply and mc._stage_of(reply, "fa") == "ask_reason" and owner == []


def test_reason_answer_creates_the_reminder_with_the_learned_name(monkeypatch, owner):
    ask_reason = sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")
    rows = [SimpleNamespace(user_message="لووتیروکسین", sedi_response=ask_reason, created_at=datetime.utcnow())] + _turns()
    reply = _go(monkeypatch, rows, "برای کم‌کاری تیروئید مصرفش می‌کنم")
    assert owner == ["لووتیروکسین"] and "14:00" in reply and "لووتیروکسین" in reply and "همراهتم" in reply


def test_confirm_stage_yes_no_and_new_name(monkeypatch, owner):
    confirm = sedi_copy.t("medication.chat.q.confirm_name", "fa", name="متفورمین")

    def rows():
        return [SimpleNamespace(user_message=REQUEST, sedi_response=confirm, created_at=datetime.utcnow())]

    assert mc._stage_of(_go(monkeypatch, rows(), "بله"), "fa") == "ask_reason"
    assert mc._stage_of(_go(monkeypatch, rows(), "نه"), "fa") == "ask_name"
    renamed = _go(monkeypatch, rows(), "گلیبن کلامید")
    assert "گلیبن" in renamed and mc._stage_of(renamed, "fa") == "ask_reason" and owner == []


@pytest.mark.parametrize("message", ["همین ساعت فقط یادم بنداز", "نمی‌دونم", "فرقی نمی‌کنه", "just remind me"])
def test_insistence_or_non_answer_ends_the_interview_and_creates(monkeypatch, owner, message):
    reply = _go(monkeypatch, _turns(), message)
    assert owner == [None] and reply and "14:00" in reply
    assert "مراقب سلامتی" in reply


def test_other_topics_and_unrelated_turns_are_left_to_the_normal_flow(monkeypatch, owner):
    long_other = "راستی دیروز با دوستم رفتیم بیرون و کلی خوش گذشت و بعد هم رفتیم رستوران و غذا خوردیم و کلی حرف زدیم"
    assert _go(monkeypatch, _turns(), long_other) is None
    plain = [SimpleNamespace(user_message="سلام", sedi_response="سلام، امروز چطوری؟", created_at=datetime.utcnow())]
    assert _go(monkeypatch, plain, "خوبم") is None
    assert owner == []


def test_no_original_request_in_the_window_means_nothing_happens(monkeypatch, owner):
    rows = [SimpleNamespace(user_message="سلام", sedi_response=sedi_copy.t("medication.chat.q.ask_name", "fa"), created_at=datetime.utcnow())]
    assert _go(monkeypatch, rows, "لووتیروکسین") is None and owner == []


@pytest.mark.parametrize(
    "reply, expected",
    [("لووتیروکسین", "لووتیروکسین"), ("اسمش متفورمین هست", "متفورمین"), ("قرص آتورواستاتین", "آتورواستاتین"),
     ("Levothyroxine", "levothyroxine"), ("بله", None), ("نه", None),
     ("یک جمله‌ی خیلی بلند که اصلاً اسم قرص نیست و درباره‌ی چیز دیگری است", None)],
)
def test_candidate_name_from_a_short_reply(reply, expected):
    got = mc._candidate_name(reply)
    assert (got.lower() if got else None) == expected


def test_revoked_memory_consent_stops_the_interview_at_once(monkeypatch, owner):
    """Codex P1 (PR 185): continuation must re-check the CURRENT memory-read permission, not only the first turn."""
    ask_reason = sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")
    rows = [SimpleNamespace(user_message="لووتیروکسین", sedi_response=ask_reason, created_at=datetime.utcnow())] + _turns()
    assert _go(monkeypatch, rows, "برای کم‌کاری تیروئید", consent=False) is None
    assert owner == []


def test_request_completed_by_a_period_answer_is_reconstructed(monkeypatch, owner):
    """Codex P2 (PR 185): «ساعت ۲» -> Sedi asks «صبح یا عصر؟» -> «عصر» -> medicine question: the stored messages are
    separate, the interview must still find the complete request."""
    period_question = sedi_copy.by_lang("reminder.clarify_opening.period")["fa"] + " ساعت ۲ صبح است یا عصر؟"
    ask_name = sedi_copy.t("medication.chat.q.ask_name", "fa")
    now = datetime.utcnow()
    rows = [
        SimpleNamespace(user_message="لووتیروکسین", sedi_response=sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین"), created_at=now),
        SimpleNamespace(user_message="عصر", sedi_response=ask_name, created_at=now),
        SimpleNamespace(user_message="هر روز ساعت ۲ یادم بنداز قرص بخورم", sedi_response=period_question, created_at=now),
    ]
    reply = _go(monkeypatch, rows, "برای کم‌کاری تیروئید مصرفش می‌کنم")
    assert owner == ["لووتیروکسین"] and reply and "14:00" in reply


# --- Codex P2 (PR 185): the medication schedule has no start date -------------------------------------------------
def _tehran_draft(start_local, rule="FREQ=DAILY"):
    return _Draft(starts_at_local=start_local, recurrence_rule=rule, timezone_name="Asia/Tehran")


@pytest.mark.parametrize(
    "now_utc, start, future",
    [
        (datetime(2026, 11, 18, 10, 0), datetime(2026, 11, 19, 21, 0), True),   # 13:30 Tehran, «from tomorrow 21:00»: tonight would be a day early
        (datetime(2026, 11, 18, 10, 0), datetime(2026, 11, 18, 21, 0), False),  # today 21:00 is simply the next occurrence
        (datetime(2026, 11, 18, 19, 0), datetime(2026, 11, 19, 14, 0), False),  # 22:30 Tehran, «every day 14:00»: tomorrow IS the next occurrence
        (datetime(2026, 11, 18, 10, 0), datetime(2026, 11, 21, 8, 0), True),    # a start three days away
    ],
)
def test_future_start_dates_keep_the_generic_route(now_utc, start, future):
    assert mc.has_future_start(_tehran_draft(start), now_utc) is future


def test_a_future_start_pill_request_is_left_to_the_generic_event_route(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    far = _tehran_draft(datetime(2030, 1, 5, 21, 0))
    assert mc.start_interview(None, user_id=1, message="از ۱۵ دی هر شب ساعت ۹ قرصم را یادم بنداز", draft=far, language="fa", timezone_name=TZ) is None
    assert owner == []


# --- Codex P2 x2 (PR 185): the schedule time IS the dose time; an explicit offset keeps the generic route ---------
def _offset_draft(offsets, defaulted=False, start=datetime(2026, 11, 18, 21, 0)):
    return _Draft(starts_at_local=start, recurrence_rule="FREQ=DAILY", reminder_offsets=offsets, offsets_defaulted=defaulted)


@pytest.mark.parametrize(
    "offsets, defaulted, expected",
    [
        ((0,), False, ["21:00"]),            # at the time
        ((), False, ["21:00"]),
        ((60,), True, ["21:00"]),            # parser default (no reminder word) is ignored: a pill is taken AT the time
        ((30,), False, None),                # «30 minutes before»: the schedule would move the DOSE to 20:30 -> generic route
        ((30, 0), False, None),
        ((10,), False, None),
    ],
)
def test_dose_time_is_never_moved_by_an_advance_reminder(offsets, defaulted, expected):
    assert mc.fire_times(_offset_draft(offsets, defaulted)) == expected


def test_a_request_with_an_advance_reminder_keeps_the_generic_route(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    draft = _offset_draft((30,))
    assert mc.start_interview(None, user_id=1, message="هر شب ساعت ۹ قرصم را نیم‌ساعت قبل یادم بنداز", draft=draft, language="fa", timezone_name=TZ) is None
    assert owner == []


def test_the_owner_write_keeps_the_stated_dose_time(monkeypatch):
    import backend.app.services.user_medication_service as svc

    seen = []
    monkeypatch.setattr(svc, "create_user_medication", lambda db, uid, body: seen.append(body) or {"id": 1})
    out = mc._create(None, user_id=1, draft=_offset_draft((0,)), language="fa", timezone_name=TZ, name="لووتیروکسین")
    assert out["created"] and out["time"] == "21:00" and seen[0].reminder_times == ["21:00"]


# --- A3 (R-088 am.2 / R-051 / R-068): the companionship after the reason is ONE tracked commitment -----------------
class _FakeDb:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _reason_rows(name="لووتیروکسین", lang="fa"):
    ask_reason = sedi_copy.t("medication.chat.q.ask_reason", lang, name=name)
    return [SimpleNamespace(user_message=name, sedi_response=ask_reason, created_at=datetime.utcnow())] + _turns()


def _go_db(monkeypatch, rows, message, db, lang="fa"):
    monkeypatch.setattr(mc, "history_available", lambda d, uid: True)
    monkeypatch.setattr(mc, "_recent_turns", lambda d, uid, now: rows)
    return mc.continue_interview(db, user_id=1, message=message, language=lang, timezone_name=TZ)


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_capture(db, user_id, step, *, user_message=""):
        calls.append((user_id, step, user_message))
        return SimpleNamespace(id=7)

    from backend.app.services.i10 import commitment_followup as cf

    monkeypatch.setattr(cf, "capture_step", fake_capture)
    return calls


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
@pytest.mark.parametrize("name", ["لووتیروکسین", "Metformin 500 mg", "Zed"])
def test_the_commitment_step_is_generic_named_and_never_cancels_another_subject(lang, name):
    from backend.app.services.i10.commitment_followup import commitment_domain

    step = sedi_copy.t("medication.chat.commitment_step", lang, name=name)
    assert name in step and "{" not in step
    assert commitment_domain(step) == "other"  # «other» chains are never superseded by domain: a 2nd medicine keeps the 1st


@pytest.mark.parametrize("lang,reason", [("fa", "برای کم‌کاری تیروئید مصرفش می‌کنم"), ("ar", "لقصور الغدة الدرقية"), ("en", "for my thyroid")])
def test_the_reason_creates_one_tracked_commitment_and_the_reply_promises_it(monkeypatch, owner, captured, lang, reason):
    db = _FakeDb()
    reply = _go_db(monkeypatch, _reason_rows(lang=lang), reason, db, lang=lang)
    assert reply and sedi_copy.t("medication.chat.created.followup_promise", lang) in reply
    assert len(captured) == 1 and captured[0][0] == 1 and captured[0][2] == reason
    assert "لووتیروکسین" in captured[0][1]
    assert db.commits == 1
    assert reply.count("?") + reply.count("؟") == 0  # the companionship is a statement, one question per reply (R-020)


def test_no_promise_when_the_commitment_could_not_be_created(monkeypatch, owner):
    """Honest text: Sedi promises tomorrow's check-in only if the tracked commitment really exists (no consent / severe / error)."""
    from backend.app.services.i10 import commitment_followup as cf

    monkeypatch.setattr(cf, "capture_step", lambda db, uid, step, *, user_message="": None)
    db = _FakeDb()
    reply = _go_db(monkeypatch, _reason_rows(), "برای کم‌کاری تیروئید", db)
    assert reply and "14:00" in reply
    assert sedi_copy.t("medication.chat.created.followup_promise", "fa") not in reply and db.commits == 0


def test_insistence_and_duplicates_create_no_commitment(monkeypatch, owner, captured):
    assert _go_db(monkeypatch, _reason_rows(), "همین ساعت فقط", _FakeDb())  # the safe escape: created, no interview, no commitment
    assert captured == []
    monkeypatch.setattr(
        mc, "_create", lambda db, **kw: {"kind": "medication", "created": False, "duplicate": True, "name": "X", "named": True, "time": "14:00"}
    )
    reply = _go_db(monkeypatch, _reason_rows(), "برای تیروئید", _FakeDb())
    assert reply == sedi_copy.t("medication.chat.already_tracked", "fa", name="X") and captured == []


def test_capture_step_is_the_single_gate(monkeypatch):
    """Consent, severe-symptom floor, blank step and errors are all handled in ONE place (reply hook + A3 share it)."""
    from backend.app.services.i10 import commitment_followup as cf
    from backend.app.services.i6 import consent_service

    created = []

    class _Nested:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    db = SimpleNamespace(begin_nested=lambda: _Nested())
    monkeypatch.setattr(cf, "create_commitment", lambda d, uid, step: created.append(step) or SimpleNamespace(id=1))
    monkeypatch.setattr(consent_service, "has_permission", lambda d, uid, perm: True)
    assert cf.capture_step(db, 1, "step one", user_message="برای تیروئید") is not None and created == ["step one"]
    assert cf.capture_step(db, 1, "   ") is None and cf.capture_step(db, 1, "step", user_message="chest pain now") is None
    monkeypatch.setattr(consent_service, "has_permission", lambda d, uid, perm: False)
    assert cf.capture_step(db, 1, "step two") is None and created == ["step one"]
    monkeypatch.setattr(consent_service, "has_permission", lambda d, uid, perm: True)
    monkeypatch.setattr(cf, "create_commitment", lambda d, uid, step: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cf.capture_step(db, 1, "step three") is None  # fail-open


def test_the_reply_hook_still_extracts_a_promise_and_goes_through_the_same_gate(monkeypatch):
    """R-068 hook refactor (A3): capture_from_reply extracts the step and hands it to capture_step; no promise -> no call."""
    from backend.app.services.i10 import commitment_followup as cf

    seen = []
    monkeypatch.setattr(cf, "capture_step", lambda db, uid, step, *, user_message="": seen.append((uid, step, user_message)) or "task")
    reply = "Try a ten minute walk after dinner tonight. I will ask tomorrow how it went."
    assert cf.capture_from_reply(None, 5, reply, "en", user_message="my back hurts") == "task"
    assert len(seen) == 1 and seen[0][0] == 5 and "walk" in seen[0][1] and seen[0][2] == "my back hurts"
    assert cf.capture_from_reply(None, 5, "Drink some water.", "en") is None and len(seen) == 1


# --- Codex P2 (PR 185): an explicit cancellation at ANY stage creates nothing -----------------------------------------
@pytest.mark.parametrize(
    "lang,text",
    [
        ("en", "Don't set the reminder; cancel it"), ("en", "No, I do not want a reminder"), ("en", "cancel"),
        ("fa", "یادآور رو نمی‌خوام"), ("fa", "لغو کن"), ("fa", "نمی‌خوام یادآوری بذاری"), ("ar", "لا أريد تذكير"), ("ar", "إلغاء"),
    ],
)
def test_explicit_cancellation_at_the_reason_stage_creates_nothing(monkeypatch, owner, captured, lang, text):
    reply = _go_db(monkeypatch, _reason_rows(lang=lang), text, _FakeDb(), lang=lang)
    assert reply == sedi_copy.t("medication.chat.cancelled", lang)
    assert owner == [] and captured == []
    assert reply.count("?") + reply.count("؟") == 0
    assert mc._stage_of(reply, lang) is None  # the interview is over


def test_cancellation_also_ends_the_name_stage_and_a_bare_refusal_still_keeps_the_request(monkeypatch, owner, captured):
    assert _go(monkeypatch, _turns(), "لغو کن") == sedi_copy.t("medication.chat.cancelled", "fa") and owner == []  # name stage
    # «نمی‌خوام» alone is NOT a withdrawal: the existing safe escape creates the reminder with the requested time
    assert _go_db(monkeypatch, _reason_rows(), "نمیخوام", _FakeDb()) and owner == ["لووتیروکسین"] and captured == []
