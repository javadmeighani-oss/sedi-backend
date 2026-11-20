"""DEBT-080 (R-109): the user's own words «it got better» / «it got worse» drive the care journey - better closes the follow-up chain
(I7 user_done via apply_done), worse replaces it with an ACUTE chain (hours-level follow-up). DB-free: owners stubbed, text rules real."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.care_journey import journey as j
from backend.app.services.i10 import commitment_followup as cf


@pytest.mark.parametrize(
    "text,lang,expected",
    [
        ("الان بهترم", "fa", "better"),
        ("حالم بهتر شده", "fa", "better"),
        ("درد برطرف شد", "fa", "better"),
        ("دیگه درد ندارم", "fa", "better"),
        ("I feel better now", "en", "better"),
        ("it's gone", "en", "better"),
        ("تحسنت", "ar", "better"),
        ("بدتر شدم", "fa", "worse"),
        ("حالم بدتر شده", "fa", "worse"),
        ("درد شدیدتر شد", "fa", "worse"),
        ("I'm getting worse", "en", "worse"),
        ("it got worse overnight", "en", "worse"),
        ("ساءت حالتي", "ar", "worse"),
        # not a status
        ("بهتر است دکتر بروم", "fa", None),
        ("بهتر شد؟ نه، بهتر نشده", "fa", None),
        ("it is not better", "en", None),
        ("not getting worse", "en", None),
        ("سلام", "fa", None),
        ("", "fa", None),
        ("خیلی طولانی " * 20 + "بهترم", "fa", None),
    ],
)
def test_status_signal_matrix(text, lang, expected):
    assert j.status_signal(text, lang) == expected


def _task(chain, domain="journey_acute", due_in_h=2):
    meta = SimpleNamespace(chain_id=chain, domain=domain)
    return SimpleNamespace(id=chain, status="open", due_at=datetime.utcnow() + timedelta(hours=due_in_h), updated_at=None, _meta=meta)


@pytest.fixture
def tasks(monkeypatch):
    ts = [_task(1), _task(2, "journey_soon")]
    monkeypatch.setattr(cf, "_commitment_tasks", lambda db, uid, statuses=cf._OPEN_STATUSES: list(ts))
    monkeypatch.setattr(cf, "meta_of", lambda t: t._meta)
    return ts


def test_resolve_closes_every_open_journey_chain_once(monkeypatch, tasks):
    done = []
    monkeypatch.setattr(cf, "apply_done", lambda db, t: done.append(t.id))
    assert cf.resolve_journey(MagicMock(), 1) is True and done == [1, 2]
    monkeypatch.setattr(cf, "_commitment_tasks", lambda db, uid, statuses=None: [])
    assert cf.resolve_journey(MagicMock(), 1) is False


def test_escalate_cancels_the_open_chains_and_creates_an_acute_one(monkeypatch, tasks):
    made = []
    monkeypatch.setattr(cf, "create_journey_followup", lambda db, uid, step, tier: made.append((step, tier)) or SimpleNamespace(id=9))
    assert cf.escalate_journey(MagicMock(), 1, "step") is True
    assert made == [("step", "acute")] and all(t.status == "cancelled" for t in tasks)
    monkeypatch.setattr(cf, "_commitment_tasks", lambda db, uid, statuses=None: [])
    assert cf.escalate_journey(MagicMock(), 1, "step") is False and len(made) == 1  # nothing open: nothing to escalate


def _wire(monkeypatch, *, open_count=1, resolved=True, escalated=True):
    calls = []
    monkeypatch.setattr(cf, "open_journey_count", lambda db, uid: open_count)
    monkeypatch.setattr(cf, "resolve_journey", lambda db, uid: calls.append("resolve") or resolved)
    monkeypatch.setattr(cf, "escalate_journey", lambda db, uid, step: calls.append(("escalate", step)) or escalated)
    notes = []
    monkeypatch.setattr(j, "_store_episode", lambda db, uid, text: notes.append(text) or True)
    return calls, notes


def test_better_closes_the_journey_and_leaves_a_note(monkeypatch):
    calls, notes = _wire(monkeypatch)
    db = MagicMock()
    assert j.apply_status(db, 1, "الان بهترم", "fa") == "better"
    assert calls == ["resolve"] and notes == [sedi_copy.t("journey.status_note.better", "fa")] and db.commit.call_count == 1


def test_worse_escalates_the_journey_and_leaves_a_note(monkeypatch):
    calls, notes = _wire(monkeypatch)
    assert j.apply_status(MagicMock(), 1, "بدتر شدم", "fa") == "worse"
    assert calls == [("escalate", sedi_copy.t("journey.step", "fa"))] and notes == [sedi_copy.t("journey.status_note.worse", "fa")]


def test_no_open_journey_no_signal_or_the_kill_switch_changes_nothing(monkeypatch):
    calls, notes = _wire(monkeypatch, open_count=0)
    assert j.apply_status(MagicMock(), 1, "بهترم", "fa") is None
    calls, notes = _wire(monkeypatch)
    assert j.apply_status(MagicMock(), 1, "سلام", "fa") is None and j.apply_status(None, 1, "بهترم", "fa") is None
    monkeypatch.setenv(j.DISABLED_ENV, "1")
    assert j.apply_status(MagicMock(), 1, "بهترم", "fa") is None and calls == [] and notes == []


def test_a_failed_change_is_rolled_back_and_nothing_is_noted(monkeypatch):
    calls, notes = _wire(monkeypatch, resolved=False)
    db = MagicMock()
    assert j.apply_status(db, 1, "بهترم", "fa") is None and db.rollback.call_count == 1 and notes == []


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_note_wording_exists_in_every_language(lang):
    for signal in ("better", "worse"):
        assert sedi_copy.t(f"journey.status_note.{signal}", lang)


def test_the_orchestrator_applies_the_status_before_answering(monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    seen = []
    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: [])
    monkeypatch.setattr(j, "apply_status", lambda db, uid, text, lang: seen.append((uid, text, lang)))
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    orch.process(authenticated_user_id=42, message="الان بهترم", language="fa")
    assert seen == [(42, "الان بهترم", "fa")]


# --- Codex round 1 on PR 199 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,lang,expected",
    [
        ("My mother is feeling better now", "en", None),   # a relative
        ("مادرم الان بهتر شده", "fa", None),
        ("I hope I feel better tomorrow", "en", None),     # a hope
        ("امیدوارم فردا بهتر شوم", "fa", None),
        ("اگه بدتر شدم چکار کنم", "fa", None),              # a condition / question
        ("Will I feel better soon?", "en", None),
        ("it has not got worse", "en", None),              # a denial of worsening
        ("it is not getting worse", "en", None),
        ("حالم بدتر نشده", "fa", None),
        ("no more pain", "en", "better"),                  # «no» inside the improvement phrase
        ("No, it got worse", "en", "worse"),
        ("بله، بدتر شده", "fa", "worse"),
    ],
)
def test_p1_only_a_real_first_person_status_counts(text, lang, expected):
    assert j.status_signal(text, lang) == expected


# --- Codex round 2 on PR 199 ------------------------------------------------------------------------------------------------------------------
def test_p2_it_got_better_is_an_improvement_report():
    assert j.status_signal("it got better", "en") == "better" and j.status_signal("it has gotten better", "en") == "better"


def test_p2_a_relatives_earlier_complaint_makes_the_answer_not_the_users_episode(monkeypatch):
    from backend.app.services import candidate_promotion_service as cp
    from backend.app.services.i6 import memory_writes

    wrote = []
    monkeypatch.setattr(cp, "_merge_list_value", lambda db, uid, dom, key, value: [value])
    monkeypatch.setattr(memory_writes, "write_fact", lambda db, uid, dom, key, value, **k: wrote.append(value))
    assert j.record_answer(MagicMock(), 1, "It started two days ago", "When did her pain start?", last_user_message="My mother has pain", language="en") is False
    assert j.record_answer(MagicMock(), 1, "از دو روز پیش شروع شد", "از کی شروع شده؟", last_user_message="مادرم درد دارد") is False
    assert wrote == []
    assert j.record_answer(MagicMock(), 1, "از دو روز پیش شروع شد", "از کی شروع شده؟", last_user_message="سرم درد دارد") is True
