"""R-108 / R-074 step 2 - CareState: the shared, read-only, consent-gated care view (unit level; the DB loop is test_r108_care_loop_e2e)."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services import care_state as cs
from backend.app.services.care_state import state as st

BETTER = {lang: sedi_copy.t("journey.status_note.better", lang) for lang in ("fa", "ar", "en")}
WORSE = {lang: sedi_copy.t("journey.status_note.worse", lang) for lang in ("fa", "ar", "en")}


def _facts(monkeypatch, **by_key):
    rows = [SimpleNamespace(domain="medical", key=k, value_json=json.dumps(v, ensure_ascii=False)) for k, v in by_key.items()]
    rows.append(SimpleNamespace(domain="work", key="occupation", value_json='"معلم"'))  # an unrelated fact is ignored
    rows.append(SimpleNamespace(domain="medical", key="symptom_episodes_broken", value_json="{nope"))
    from backend.app.services.i6 import memory_writes

    monkeypatch.setattr(memory_writes, "list_facts_readonly_or_empty", lambda db, uid, domain=None: rows)


# --- the issue and where it stands ---------------------------------------------------------------------------------------------------------------
def test_the_status_notes_are_recognised_in_every_language():
    for lang in ("fa", "ar", "en"):
        assert st._status_of(BETTER[lang]) == "better" and st._status_of(WORSE[lang]) == "worse"
    assert st._status_of("از دو روز پیش") is None and st._status_of("") is None


def test_the_stated_concern_leads_and_the_newest_status_note_wins(monkeypatch):
    _facts(monkeypatch, health_concerns=["درد قفسه سینه"], symptom_episodes=["از دو روز پیش", WORSE["fa"], BETTER["fa"]])
    issue = st._issues(None, 1)[0]
    assert issue.text == "درد قفسه سینه" and issue.status == "better"  # the later note replaces the earlier one


def test_without_a_stated_concern_the_newest_episode_is_the_issue(monkeypatch):
    _facts(monkeypatch, symptom_episodes=["قدیمی", "تازه تر", WORSE["fa"]])
    issue = st._issues(None, 1)[0]
    assert issue.text == "تازه تر" and issue.status == "worse"


def test_status_notes_alone_are_not_an_issue_and_nothing_stored_means_none(monkeypatch):
    _facts(monkeypatch, symptom_episodes=[BETTER["fa"]])
    assert st._issues(None, 1) == ()
    _facts(monkeypatch)
    assert st._issues(None, 1) == ()


# --- the contract ------------------------------------------------------------------------------------------------------------------------------------
def test_properties_describe_the_picture():
    journey = cs.CareFollowUp(kind="journey", tier="acute")
    assert cs.CareState(user_id=1).is_empty
    state = cs.CareState(user_id=1, follow_ups=(journey,))
    assert state.has_open_journey and state.is_acute and not state.is_empty
    soon = cs.CareState(user_id=1, follow_ups=(cs.CareFollowUp(kind="journey", tier="soon"),))
    assert soon.has_open_journey and not soon.is_acute
    plain = cs.CareState(user_id=1, follow_ups=(cs.CareFollowUp(kind="commitment"),))
    assert not plain.has_open_journey and not plain.is_acute


def test_the_state_is_frozen():
    with pytest.raises(Exception):
        cs.CareState(user_id=1).consent = False  # type: ignore[misc]


def test_no_db_gives_none_and_no_consent_gives_an_empty_state_without_reading(monkeypatch):
    assert cs.get_care_state(None, 1) is None
    monkeypatch.setattr(st, "_has_read_consent", lambda db, uid: False)
    read = []
    for name in ("_issues", "_follow_ups", "_events", "_medications", "_resolved"):
        monkeypatch.setattr(st, name, lambda *a, _n=name, **k: read.append(_n))
    state = cs.get_care_state(object(), 1)
    assert state.consent is False and state.is_empty and read == []


def test_the_state_is_assembled_from_its_owners(monkeypatch):
    when = datetime(2026, 11, 21, 9, 0)
    monkeypatch.setattr(st, "_has_read_consent", lambda db, uid: True)
    monkeypatch.setattr(st, "_issues", lambda db, uid: (cs.CareIssue("درد", "worse"),))
    monkeypatch.setattr(st, "_follow_ups", lambda db, uid: (cs.CareFollowUp("journey", "acute", when, 2),))
    monkeypatch.setattr(st, "_events", lambda db, uid, now: (cs.CareEvent("ملاقات", when),))
    monkeypatch.setattr(st, "_medications", lambda db, uid: 2)
    monkeypatch.setattr(st, "_resolved", lambda db, uid, now: 1)
    state = cs.get_care_state(object(), 7, now=datetime(2026, 11, 20, 8, 0))
    assert (state.user_id, state.medications, state.resolved_recent) == (7, 2, 1) and state.is_acute and state.events[0].title == "ملاقات"


def test_every_section_fails_open(monkeypatch):
    class Broken:
        def query(self, *a, **k):
            raise RuntimeError("down")

    monkeypatch.setattr(st, "_has_read_consent", lambda db, uid: True)
    from backend.app.services.i6 import memory_writes

    monkeypatch.setattr(memory_writes, "list_facts_readonly_or_empty", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    state = cs.get_care_state(Broken(), 1)
    assert state is not None and state.is_empty  # the care view degrades to «nothing known», it never breaks the caller


# --- the one summary line -----------------------------------------------------------------------------------------------------------------------------
def _full(status="open"):
    return cs.CareState(
        user_id=1,
        issues=(cs.CareIssue("درد قفسه سینه", status),),
        follow_ups=(cs.CareFollowUp("journey", "acute"),),
        events=(cs.CareEvent("ملاقات دکتر", datetime(2026, 11, 21, 10, 0)),),
        resolved_recent=2,
    )


@pytest.mark.parametrize("status", ["open", "better", "worse"])
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_summary_line_is_deterministic_catalog_text_in_every_language(status, lang):
    line = cs.summary_line(_full(status), lang)
    assert line.count(" · ") == 3 and "{" not in line and "درد قفسه سینه" in line
    assert line == cs.summary_line(_full(status), lang)


def test_the_summary_line_is_empty_when_there_is_nothing_to_say_or_no_consent():
    assert cs.summary_line(None, "fa") == "" and cs.summary_line(cs.CareState(user_id=1), "fa") == ""
    assert cs.summary_line(cs.CareState(user_id=1, consent=False), "fa") == ""
    assert cs.summary_line(_full(), None).startswith("موضوع باز")  # unknown language -> Persian, the product default


# --- the guard: consumers are listed so a new reader is a conscious decision ------------------------------------------------------------------------
APPROVED_READERS = {
    "backend/app/services/status_report/builder.py",
}


def test_only_the_approved_modules_read_the_care_state():
    root = Path(__file__).resolve().parents[2]
    users = set()
    for path in (root / "backend" / "app").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("backend/app/services/care_state/"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "services.care_state" in text or "import care_state" in text:
            users.add(rel)
    assert users == APPROVED_READERS, f"care state readers changed (add new ones here on purpose): {sorted(users ^ APPROVED_READERS)}"


def test_the_owner_exposes_the_plain_follow_up_read_the_state_uses():
    from backend.app.services.i10 import commitment_followup as cf

    assert callable(cf.open_follow_ups) and callable(cf.resolved_journeys_since)
    assert isinstance(timedelta(days=7), timedelta) and st.RESOLVED_WINDOW == timedelta(days=7)
