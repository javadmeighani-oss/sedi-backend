"""R-109 step 1b-2 (Javad 2026-11-20): the CARE JOURNEY on the provider-finding path.

Pilot: «a heart doctor in Pardis» produced links and nothing else - no follow-up, no episode, no «what happened / new or old / why /
what to do until the visit». The journey adds, on existing owners only: an hour-level follow-up chain (I10), an I6 episode note, and a
compact block (conservative NON-DRUG stabilising care + an emergency line + up to three grouped questions).
DB-free: owners are stubbed; tiers, text, cadence arithmetic, the chain and the orchestrator hook run for real.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import pytz

from backend.app import sedi_copy
from backend.app.services.care_journey import journey as j
from backend.app.services.i10 import commitment_followup as cf

TEHRAN = pytz.timezone("Asia/Tehran")


# --- tiers -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,tier",
    [
        ("یه دکتر قلب در شهر پردیس", "acute"),
        ("find a heart doctor in Shiraz", "acute"),
        ("یه دکتر پوست در شیراز", "routine"),
        ("دکتر اعصاب برای سردرد در شیراز", "soon"),
    ],
)
def test_tier_matrix(text, tier):
    assert j.tier_for(text, "fa" if any("؀" <= c <= "ۿ" for c in text) else "en") == tier


def test_an_emergency_red_flag_starts_no_journey():
    assert j.tier_for("قفسه سینه‌ام درد می‌کند و نفسم تنگ است، دکتر قلب", "fa") is None


# --- the text --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
@pytest.mark.parametrize("area", ["chest", "generic"])
def test_the_journey_block_is_conservative_compact_and_has_at_most_three_questions(lang, area):
    text = j.journey_text(lang, area, new_journey=True)
    assert text.count("؟") + text.count("?") <= 3  # R-105
    care = sedi_copy.t(f"journey.care.{area}", lang)
    # non-drug only: no medicine is started/stopped/changed, and the emergency line is always there
    for forbidden in ("قرص بخور", "دارو را قطع", "دوز", "take a pill", "stop taking", "dose", "جرعة"):
        assert forbidden not in care
    assert any(w in care for w in ("اورژانس", "emergency", "الطوارئ"))
    assert j.is_interview_reply(text)


def test_an_open_journey_adds_only_the_status_question():
    assert j.journey_text("fa", "chest", new_journey=False) == "الان وضعیتت چطور است؟"


# --- starting the journey ---------------------------------------------------------------------------------------------------------------
def _owners(monkeypatch, *, open_count=0, created=True):
    calls = []
    monkeypatch.setattr(cf, "open_journey_count", lambda db, uid: open_count)
    monkeypatch.setattr(cf, "create_journey_followup", lambda db, uid, step, tier: calls.append((step, tier)) or (SimpleNamespace(id=9) if created else None))
    return calls


def test_a_new_journey_tracks_one_follow_up_and_returns_the_block(monkeypatch):
    calls = _owners(monkeypatch)
    db = MagicMock()
    block = j.start(db, 1, "یه دکتر قلب در شهر پردیس", "fa")
    assert calls == [("پیگیری وضعیتت تا رسیدن به پزشک", "acute")] and db.commit.call_count == 1
    assert "فعالیت سنگین نکن" in block and "تنگی نفس" in block and j.is_interview_reply(block)


def test_an_open_journey_is_not_started_twice(monkeypatch):
    calls = _owners(monkeypatch, open_count=1)
    assert j.start(MagicMock(), 1, "یه دکتر قلب در شهر پردیس", "fa") == "الان وضعیتت چطور است؟" and calls == []


def test_without_memory_consent_nothing_is_tracked_so_nothing_is_promised(monkeypatch):
    _owners(monkeypatch, created=False)
    assert j.start(MagicMock(), 1, "یه دکتر قلب در شهر پردیس", "fa") is None


def test_kill_switch_emergency_and_errors_are_silent(monkeypatch):
    _owners(monkeypatch)
    monkeypatch.setenv(j.DISABLED_ENV, "1")
    assert j.start(MagicMock(), 1, "یه دکتر قلب در شهر پردیس", "fa") is None
    monkeypatch.delenv(j.DISABLED_ENV)
    assert j.start(MagicMock(), 1, "قفسه سینه‌ام درد می‌کند و نفسم تنگ است، دکتر قلب", "fa") is None
    db = MagicMock()
    monkeypatch.setattr(cf, "open_journey_count", lambda d, u: (_ for _ in ()).throw(RuntimeError("db")))
    assert j.start(db, 1, "یه دکتر قلب در شهر پردیس", "fa") is None and db.rollback.call_count == 1  # fail-open
    assert j.start(None, 1, "x", "fa") is None


# --- the hour-level cadence --------------------------------------------------------------------------------------------------------------
def _db_with_taken(n):
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = n
    return db


@pytest.fixture(autouse=True)
def _tehran(monkeypatch):
    monkeypatch.setattr(cf, "_zone", lambda db, uid: TEHRAN)


def _local(due_naive_utc):
    return pytz.UTC.localize(due_naive_utc).astimezone(TEHRAN)


@pytest.mark.parametrize(
    "tier,attempt,base_hour,expect_hour",
    [("acute", 1, 8, 10), ("acute", 2, 8, 12), ("acute", 3, 8, 14), ("acute", 4, 8, 20), ("acute", 9, 8, 20), ("soon", 1, 8, 12), ("soon", 2, 8, 16)],
)
def test_hour_level_due_times_by_tier(tier, attempt, base_hour, expect_hour):
    base = TEHRAN.localize(datetime(2026, 11, 20, base_hour, 0)).astimezone(timezone.utc)
    due = cf.journey_due(_db_with_taken(0), 1, base_utc=base, tier=tier, attempt=attempt)
    assert _local(due).hour == expect_hour and _local(due).minute == 0


def test_quiet_hours_move_a_push_to_07_00():
    base = TEHRAN.localize(datetime(2026, 11, 20, 20, 30)).astimezone(timezone.utc)
    due = _local(cf.journey_due(_db_with_taken(0), 1, base_utc=base, tier="acute", attempt=1))  # 22:30 -> 07:00 next morning
    assert (due.day, due.hour, due.minute) == (21, 7, 0)
    base2 = TEHRAN.localize(datetime(2026, 11, 20, 3, 0)).astimezone(timezone.utc)  # 05:00 is quiet too -> 07:00 the same day
    due2 = _local(cf.journey_due(_db_with_taken(0), 1, base_utc=base2, tier="acute", attempt=1))
    assert (due2.day, due2.hour) == (20, 7)


def test_a_full_day_pushes_the_next_one_to_tomorrow_morning():
    base = TEHRAN.localize(datetime(2026, 11, 20, 8, 0)).astimezone(timezone.utc)
    due = _local(cf.journey_due(_db_with_taken(cf.JOURNEY_DAILY_CAP), 1, base_utc=base, tier="acute", attempt=1))
    assert (due.day, due.hour) == (21, 9)


def test_the_cadence_table_is_the_approved_one():
    assert cf.JOURNEY_HOURS == {"acute": (2, 4, 6, 12), "soon": (4, 8, 16, 24)}
    assert (cf.JOURNEY_QUIET_FROM, cf.JOURNEY_QUIET_TO, cf.JOURNEY_DAILY_CAP) == (22, 7, 5)


# --- the chain: the next attempt keeps the hour-level cadence ---------------------------------------------------------------------------
def _task(domain, attempt):
    from backend.app.services.i10.contextual_followup_task_meta import BoundedFollowUpMeta, pack_description

    return SimpleNamespace(
        id=5, user_id=1, title="x",
        description=pack_description(None, BoundedFollowUpMeta(follow_up_kind=cf.COMMITMENT_KIND, attempt=attempt, domain=domain, chain_id=5, approach="first")),
    )


def test_the_next_journey_attempt_is_hours_later_and_the_chain_ends_after_about_a_week(monkeypatch):
    made = []
    monkeypatch.setattr(cf, "chain_of", lambda db, task, statuses=None: [])
    monkeypatch.setattr(cf, "_create_task", lambda db, uid, title, due, **k: made.append((due, k["attempt"], k["domain"])) or "next")
    base = TEHRAN.localize(datetime(2026, 11, 20, 8, 0)).astimezone(timezone.utc)
    assert cf.schedule_next_attempt(_db_with_taken(0), _task("journey_acute", 1), now=base) == "next"
    due, attempt, domain = made[0]
    assert attempt == 2 and domain == "journey_acute" and _local(due).hour == 12  # +4 h after the previous send
    assert cf.schedule_next_attempt(_db_with_taken(0), _task("journey_acute", cf.JOURNEY_MAX_ATTEMPTS), now=base) is None


def test_a_plain_commitment_keeps_its_day_ladder(monkeypatch):
    made = []
    monkeypatch.setattr(cf, "chain_of", lambda db, task, statuses=None: [])
    monkeypatch.setattr(cf, "_create_task", lambda db, uid, title, due, **k: made.append((due, k["domain"])) or "next")
    monkeypatch.setattr(cf, "follow_up_time", lambda db, uid, base_utc, days_ahead: datetime(2026, 11, 21, 5, 30))
    cf.schedule_next_attempt(MagicMock(), _task("other", 1), now=datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc))
    assert made == [(datetime(2026, 11, 21, 5, 30), "other")]


# --- the follow-up wording ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_journey_follow_ups_ask_how_the_user_is_now_and_never_name_an_illness(lang):
    for attempt in (1, 2, 3, 4):
        title, body = cf.commitment_copy(lang, attempt, domain="journey_acute")
        assert body and "{" not in body
        for illness in ("قلب", "heart", "قلبي", "سرطان", "cancer", "دیابت", "diabetes"):
            assert illness not in body
    assert cf.commitment_copy("fa", 1, domain="journey_soon")[1] == "الان وضعیتت چطور است؟"
    assert cf.commitment_copy("fa", 1)[1] == sedi_copy.t("commitment.body.1", "fa")  # a plain commitment is unchanged


# --- the creation gate ------------------------------------------------------------------------------------------------------------------------
def test_create_journey_followup_is_consent_gated_and_uses_the_tier_domain(monkeypatch):
    from backend.app.services.i6 import consent_service

    made = []
    monkeypatch.setattr(cf, "_supersede", lambda db, uid, domain: made.append(("supersede", domain)))
    monkeypatch.setattr(cf, "_create_task", lambda db, uid, step, due, **k: made.append(("create", k["domain"], k["attempt"])) or "task")
    monkeypatch.setattr(cf, "journey_due", lambda db, uid, **k: datetime(2026, 11, 20, 8, 0))
    db = MagicMock()
    monkeypatch.setattr(consent_service, "has_permission", lambda d, u, p: True)
    assert cf.create_journey_followup(db, 1, "step", "acute") == "task"
    assert made == [("supersede", "journey_acute"), ("create", "journey_acute", 1)]
    monkeypatch.setattr(consent_service, "has_permission", lambda d, u, p: False)
    assert cf.create_journey_followup(db, 1, "step", "acute") is None
    monkeypatch.setattr(consent_service, "has_permission", lambda d, u, p: True)
    assert cf.create_journey_followup(db, 1, "", "acute") is None and cf.create_journey_followup(db, 1, "s", "bogus") is None


# --- the interview answer -> I6 episode ---------------------------------------------------------------------------------------------------------
def test_the_interview_answer_becomes_an_episode_note(monkeypatch):
    from backend.app.services import candidate_promotion_service as cp
    from backend.app.services.i6 import memory_writes

    wrote = []
    monkeypatch.setattr(cp, "_merge_list_value", lambda db, uid, dom, key, value: [value])
    monkeypatch.setattr(memory_writes, "write_fact", lambda db, uid, dom, key, value, **k: wrote.append((dom, key, value)))
    reply = j.journey_text("fa", "chest", new_journey=True)
    assert j.record_answer(MagicMock(), 1, "از دو روز پیش شروع شد، با پله بالا رفتن بدتر می‌شود", reply) is True
    assert wrote == [("medical", "symptom_episodes", ["از دو روز پیش شروع شد، با پله بالا رفتن بدتر می‌شود"])]
    assert j.record_answer(MagicMock(), 1, "سلام", "یه جواب معمولی") is False  # not an answer to the interview
    assert j.record_answer(MagicMock(), 1, "  ", reply) is False and j.record_answer(None, 1, "x" * 10, reply) is False
    assert len(wrote) == 1


def test_a_revoked_consent_records_nothing(monkeypatch):
    from backend.app.services.i6 import memory_writes
    from backend.app.services.i6.consent_service import ConsentDenied

    monkeypatch.setattr(memory_writes, "write_fact", lambda *a, **k: (_ for _ in ()).throw(ConsentDenied()))
    assert j.record_answer(MagicMock(), 1, "دو روز است درد دارم", j.journey_text("fa", "generic", new_journey=True)) is False


# --- through the real orchestrator -------------------------------------------------------------------------------------------------------------
def _orch(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention
    from backend.app.services.i5 import care_navigation_directory as cn

    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: [])
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: [])
    return IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)


def test_orchestrator_appends_the_journey_to_a_doctor_answer(monkeypatch):
    _owners(monkeypatch)
    out = _orch(monkeypatch).process(authenticated_user_id=42, message="یه دکتر قلب در شهر پردیس معرفی کن", language="fa")
    assert "R109_CARE_JOURNEY" in out.reason_codes
    assert "فعالیت سنگین نکن" in out.message and j.is_interview_reply(out.message)


def test_orchestrator_adds_no_journey_to_a_pharmacy_lookup(monkeypatch):
    _owners(monkeypatch)
    out = _orch(monkeypatch).process(authenticated_user_id=42, message="یه داروخانه شبانه‌روزی در شهر شیراز", language="fa")
    assert "R109_CARE_JOURNEY" not in out.reason_codes


def test_orchestrator_records_the_answer_to_the_interview(monkeypatch):
    import backend.app.services.i7.retention as retention
    from backend.app.services import candidate_promotion_service as cp
    from backend.app.services.i6 import memory_writes

    wrote = []
    monkeypatch.setattr(cp, "_merge_list_value", lambda db, uid, dom, key, value: [value])
    monkeypatch.setattr(memory_writes, "write_fact", lambda db, uid, dom, key, value, **k: wrote.append(value))
    orch = _orch(monkeypatch)
    last = SimpleNamespace(user_message="یه دکتر قلب در شهر پردیس", sedi_response=j.journey_text("fa", "chest", new_journey=True), created_at=datetime.utcnow())
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: [last])
    orch.process(authenticated_user_id=42, message="از دو روز پیش شروع شده و قبلاً نداشتم", language="fa")
    assert wrote and "دو روز" in wrote[0][0]
