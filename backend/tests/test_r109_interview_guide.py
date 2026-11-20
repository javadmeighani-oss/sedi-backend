"""R-109 step 1b-1 (Javad 2026-11-20): the slot-driven interview guide.

Sedi must converse precisely and in detail about EVERYTHING (illness to work/life) until she understands the user; what she learns is
recorded in memory; «how are you now?» belongs to every conversation with an open care follow-up; up to THREE questions per reply.
DB-free: memory reads and the safety paths are stubbed; topic detection, the checklist, the gaps and the hint run for real.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services.interview import guide as g


# --- topics ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message,topics",
    [
        ("قلبم درد می‌کند", {"symptom"}),
        ("my chest hurts when I climb stairs", {"symptom"}),
        ("يؤلمني صدري منذ يومين", {"symptom"}),
        ("رئیسم خیلی فشار میاره و شب‌ها خوابم نمی‌بره", {"symptom", "work_life"}),  # poor sleep is a health topic too
        ("I was laid off last month and I feel lonely", {"work_life"}),
        ("بعد از اخراج از کار سردرد دارم", {"symptom", "work_life"}),
        ("سلام، امروز هوا خوبه", set()),
        ("فردا عمل جراحی دارم", set()),          # «عمل» is surgery, not work
    ],
)
def test_topic_detection_matrix(message, topics):
    assert g.detect_topics(message, "fa") == topics


# --- the hint ------------------------------------------------------------------------------------------------------------------------------
def test_the_symptom_hint_carries_the_checklist_the_cap_and_the_safety_form():
    hint = g.build_hint({"symptom"}, [], 0)
    for part in g.SYMPTOM_CHECKLIST:
        assert part in hint
    assert "at most 3 short" in hint and "Start with the current state" in hint
    assert "non-drug only" in hint and "never start/stop/change a medicine" in hint
    assert "Do NOT diagnose" in hint


def test_the_work_life_hint_and_the_memory_gaps():
    hint = g.build_hint({"work_life"}, ["what work the user does", "working days and hours, shifts"], 0)
    assert "LIFE/WORK INTERVIEW" in hint and "what work the user does" in hint and "STILL UNKNOWN" in hint


def test_an_open_care_follow_up_adds_how_are_you_now():
    hint = g.build_hint({"symptom"}, [], 2)
    assert "OPEN CARE FOLLOW-UP" in hint and "الان وضعیتت چطور است؟" in hint
    assert g.build_hint(set(), [], 1) and "OPEN CARE FOLLOW-UP" in g.build_hint(set(), [], 1)  # even a plain greeting gets the status check
    assert g.build_hint(set(), [], 0) is None and g.build_hint(set(), ["x"], 0) is not None


# --- memory gaps -----------------------------------------------------------------------------------------------------------------------------
def _facts(monkeypatch, known):
    rows = [SimpleNamespace(domain=d, key=k) for d, k in known]
    from backend.app.services.i6 import memory_writes

    monkeypatch.setattr(memory_writes, "list_facts_readonly_or_empty", lambda db, uid, domain=None: [r for r in rows if r.domain == domain])


def test_gaps_are_only_what_memory_does_not_hold_yet(monkeypatch):
    _facts(monkeypatch, [("medical", "health_concerns"), ("work", "occupation"), ("social", "household_context")])
    sym = g.memory_gaps(None, 1, {"symptom"})
    assert len(sym) == 1 and "close relatives" in sym[0]  # family history is missing, known illnesses are not
    work = g.memory_gaps(None, 1, {"work_life"})
    assert not any("what work the user does" in w or "who they live with" in w for w in work) and "working days and hours, shifts" in work


def test_no_topic_no_gaps():
    assert g.memory_gaps(None, 1, set()) == []


# --- the turn ----------------------------------------------------------------------------------------------------------------------------------
def _stubs(monkeypatch, *, red=False, crisis=False, follow_ups=0, known=()):
    from backend.app.services.care_navigation import crisis_support, symptom_triage

    monkeypatch.setattr(symptom_triage, "triage", lambda text, lang="fa": SimpleNamespace(red_flag=red, areas=("chest",) if "قلب" in text else ()))
    monkeypatch.setattr(crisis_support, "hint_for_turn", lambda db, uid, text, lang: "CRISIS" if crisis else None)
    monkeypatch.setattr(g, "open_care_follow_ups", lambda db, uid: follow_ups)
    _facts(monkeypatch, known)


def test_a_symptom_turn_gets_the_guide(monkeypatch):
    _stubs(monkeypatch, follow_ups=1)
    hint = g.hint_for_turn(None, 1, "قلبم درد می‌کند", "fa")
    assert hint and "SYMPTOM INTERVIEW" in hint and "OPEN CARE FOLLOW-UP" in hint and "STILL UNKNOWN" in hint


def test_an_emergency_or_self_harm_turn_is_left_to_its_own_path(monkeypatch):
    _stubs(monkeypatch, red=True)
    assert g.hint_for_turn(None, 1, "قلبم درد می‌کند و نفسم بند آمده", "fa") is None
    _stubs(monkeypatch, crisis=True)
    assert g.hint_for_turn(None, 1, "قلبم درد می‌کند", "fa") is None  # R-099 keeps its single gentle question


def test_the_kill_switch_and_an_empty_message_and_errors_are_silent(monkeypatch):
    _stubs(monkeypatch)
    monkeypatch.setenv(g.DISABLED_ENV, "1")
    assert g.hint_for_turn(None, 1, "قلبم درد می‌کند", "fa") is None
    monkeypatch.delenv(g.DISABLED_ENV)
    assert g.hint_for_turn(None, 1, "   ", "fa") is None
    monkeypatch.setattr(g, "detect_topics", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert g.hint_for_turn(None, 1, "قلبم درد می‌کند", "fa") is None  # fail-open: the chat is never broken


# --- the status hook owner --------------------------------------------------------------------------------------------------------------------------
def test_open_commitment_count_uses_the_i10_owner(monkeypatch):
    from backend.app.services.i10 import commitment_followup as cf

    monkeypatch.setattr(cf, "_commitment_tasks", lambda db, uid: [object(), object()])
    assert cf.open_commitment_count(None, 1) == 2 and g.open_care_follow_ups(None, 1) == 2
    monkeypatch.setattr(cf, "_commitment_tasks", lambda db, uid: (_ for _ in ()).throw(RuntimeError("db")))
    assert cf.open_commitment_count(None, 1) == 0  # fail-open


# --- the memory vocabulary: what the interview learns can be written, read and edited ------------------------------------------------------------
def test_the_new_memory_keys_are_valid_and_wired_end_to_end():
    from backend.app.services import candidate_promotion_service as cp
    from backend.app.services.knowledge import llm_memory_extractor_v2 as ex
    from backend.app.services.memory.memory_contract import I6_USER_STATED_HEALTH_KEYS, MemoryContract

    assert MemoryContract.validate_fact("medical", "symptom_episodes")[0]
    assert ("medical", "symptom_episodes") in I6_USER_STATED_HEALTH_KEYS  # readable by chat (consent-gated)
    assert cp.LIFESTYLE_SCALAR_MAP["symptom_episode"] == ("medical", "symptom_episodes")
    assert ("medical", "symptom_episodes") in cp.LIST_MERGE_KEYS  # a growing list: each episode is merged, never replaced
    assert cp.LIFESTYLE_SCALAR_MAP["work_stressors"] == ("work", "work_stressors")
    for key in ("symptom_episode", "work_schedule", "work_stressors"):
        assert key in ex.ALLOWED_FACTS and key in ex.SYSTEM_PROMPT
    assert MemoryContract.validate_fact("work", "work_stressors")[0] and MemoryContract.validate_fact("work", "work_schedule")[0]


# --- the chat wiring ------------------------------------------------------------------------------------------------------------------------------------
def test_brain_appends_the_guide_as_one_system_message_and_never_breaks(monkeypatch):
    from backend.app.core.conversation import brain

    monkeypatch.setattr(g, "hint_for_turn", lambda db, uid, msg, lang: "GUIDE")
    msgs = []
    brain._maybe_append_interview_guide(msgs, MagicMock(), 1, "قلبم درد می‌کند", "fa")
    assert msgs == [{"role": "system", "content": "GUIDE"}]
    monkeypatch.setattr(g, "hint_for_turn", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    brain._maybe_append_interview_guide(msgs, MagicMock(), 1, "x", "fa")
    assert len(msgs) == 1


# --- Codex round 1 on PR 195 ------------------------------------------------------------------------------------------------------------------------------
def test_p2_the_new_facts_are_accepted_automatically_like_health_concerns():
    from backend.app.services.knowledge.conversation_extraction_service import _AUTO_ACCEPT_KEYS

    for key in ("symptom_episode", "work_schedule", "work_stressors"):
        assert key in _AUTO_ACCEPT_KEYS  # otherwise the answers would stay pending and never reach memory


def test_p2_a_symptom_episode_is_never_presented_as_family_history():
    from backend.app.services.intelligence import adapters

    assert adapters._STATED_HEALTH_LABELS["symptom_episodes"] == "stated_symptom_episodes"
    assert adapters._STATED_HEALTH_LABELS.get("family_history", "stated_family_history") == "stated_family_history"
