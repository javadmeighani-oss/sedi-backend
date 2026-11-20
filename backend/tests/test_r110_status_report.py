"""R-110 amendment 1 (Javad 2026-11-20): ONE status report for five kinds (health status, doctor visit, nutrition, lifestyle, exercise plan).

DB-free: the data owners (I6 facts, medications, I8 projection, weekly report, journey state, UserState) are stubbed; the contract, the
section order, consent gating, line ids, limits, fail-open and the router run for real.
"""
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.status_report import builder as b

FACTS = {
    ("medical", "health_concerns"): ["درد قفسه سینه"],
    ("medical", "symptom_episodes"): ["از دو روز پیش شروع شد", "وضعیت بعدی: بهتر شده است"],
    ("medical", "family_history"): ["پدرم بیماری قلبی دارد"],
    ("intake", "allergies"): ["پنی‌سیلین"],
    ("intake", "goal"): "کاهش وزن",
    ("intake", "food_preferences"): ["بدون لبنیات"],
    ("intake", "exercise_preferences"): ["پیاده‌روی"],
    ("lifestyle", "sleep_duration_hours"): "۶",
    ("work", "occupation"): "معلم",
    ("work", "work_schedule"): "شنبه تا چهارشنبه، ۸ تا ۱۴",
    ("work", "work_stressors"): "شلوغی کلاس",
    ("social", "household_context"): "با همسر و دو فرزند",
    ("preferences", "interests"): ["کتاب"],
}


@pytest.fixture
def owners(monkeypatch):
    monkeypatch.setattr(b, "_has_read_consent", lambda db, uid: True)
    monkeypatch.setattr(b, "_facts", lambda db, uid: dict(FACTS))
    monkeypatch.setattr(b, "_about", lambda db, uid, lang: [sedi_copy.t("report.about.name", lang, name="سارا"), sedi_copy.t("report.about.age", lang, age=34)])
    monkeypatch.setattr(b, "_meds", lambda db, uid, lang: ["متفورمین - ۵۰۰ (ساعت مصرف: 08:00)"])
    monkeypatch.setattr(b, "_plan_lines", lambda db, uid, domain, lang: [sedi_copy.t("report.plan.line_timed", lang, day=1, time="07:00", title=f"برنامه {domain}")])
    monkeypatch.setattr(b, "_week_lines", lambda db, uid, lang: [sedi_copy.t("report.week.line", lang, done=5, not_done=2)])
    monkeypatch.setattr(b, "_follow_up_lines", lambda db, uid, lang: [sedi_copy.t("report.followup.open", lang)])


def _keys(report):
    return [s["key"] for s in report["sections"]]


# --- the contract ------------------------------------------------------------------------------------------------------------------------------
def test_five_kinds_exist_with_titles_in_every_language():
    for lang in ("fa", "ar", "en"):
        listed = b.kinds(lang)
        assert [k["kind"] for k in listed] == list(b.KINDS) and all(k["title"] and "{" not in k["title"] for k in listed)
    assert b.kinds(None)[0]["title"] == sedi_copy.t("report.kind.health_status", "fa")


def test_an_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        b.build_status_report(None, 1, "diagnosis", "fa")


@pytest.mark.parametrize("kind", list(b.KINDS))
def test_every_kind_is_ready_with_its_own_ordered_sections_and_stable_line_ids(owners, kind):
    report = b.build_status_report(None, 1, kind, "fa")
    assert report["state"] == "ready" and report["kind"] == kind and report["language"] == "fa"
    assert report["note"] == sedi_copy.t("report.note", "fa") and report["title"] == sedi_copy.t(f"report.kind.{kind}", "fa")
    order = [k for k in b.SECTIONS[kind]]
    assert _keys(report) == [k for k in order if k in _keys(report)]  # the contract order, empty sections left out
    ids = [line["id"] for s in report["sections"] for line in s["lines"]]
    assert len(ids) == len(set(ids)) and all(i.startswith(s["key"] + "-") for s in report["sections"] for i in [l["id"] for l in s["lines"]])
    assert all(s["title"] == sedi_copy.t(f"report.section.{s['key']}", "fa") for s in report["sections"])


def test_the_doctor_summary_carries_reason_timeline_history_medicines_and_questions(owners):
    report = b.build_status_report(None, 1, "doctor_visit", "fa")
    sections = {s["key"]: [l["text"] for l in s["lines"]] for s in report["sections"]}
    assert sections["reason"] == ["درد قفسه سینه"]
    assert sections["timeline"] == ["از دو روز پیش شروع شد", "وضعیت بعدی: بهتر شده است"]
    assert sections["history"] == ["پدرم بیماری قلبی دارد"] and sections["allergies"] == ["پنی‌سیلین"] and sections["meds"]
    assert len(sections["questions"]) == 3 and all(q.endswith("؟") for q in sections["questions"])
    assert "follow_up" in sections and "plan_nutrition" not in sections and "plan_exercise" not in sections


def test_the_other_kinds_use_their_own_owners(owners):
    nutrition = {s["key"]: s for s in b.build_status_report(None, 1, "nutrition", "fa")["sections"]}
    assert "plan_nutrition" in nutrition and "plan_exercise" not in nutrition and nutrition["food"]["lines"][0]["text"] == "بدون لبنیات"
    exercise = {s["key"]: s for s in b.build_status_report(None, 1, "exercise_plan", "fa")["sections"]}
    assert "plan_exercise" in exercise and exercise["exercise"]["lines"][0]["text"] == "پیاده‌روی" and "meds" not in exercise
    life = {s["key"]: s for s in b.build_status_report(None, 1, "lifestyle", "fa")["sections"]}
    assert [l["text"] for l in life["work"]["lines"]] == ["معلم", "شنبه تا چهارشنبه، ۸ تا ۱۴", "شلوغی کلاس"]
    assert life["sleep"]["lines"][0]["text"] == sedi_copy.t("report.sleep.line", "fa", hours="۶")
    health = {s["key"]: s for s in b.build_status_report(None, 1, "health_status", "fa")["sections"]}
    assert {"concerns", "timeline", "meds", "week", "follow_up"} <= set(health)


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_every_language_renders_without_placeholders(owners, lang):
    for kind in b.KINDS:
        report = b.build_status_report(None, 1, kind, lang)
        texts = [report["title"], report["note"]] + [s["title"] for s in report["sections"]] + [l["text"] for s in report["sections"] for l in s["lines"]]
        assert all(t and "{" not in t and "}" not in t for t in texts)


# --- consent, empty, failure -------------------------------------------------------------------------------------------------------------------
def test_without_memory_consent_nothing_is_read(monkeypatch):
    read = []
    monkeypatch.setattr(b, "_has_read_consent", lambda db, uid: False)
    monkeypatch.setattr(b, "_facts", lambda db, uid: read.append("facts") or {})
    monkeypatch.setattr(b, "_meds", lambda *a: read.append("meds") or [])
    report = b.build_status_report(None, 1, "doctor_visit", "fa")
    assert report["state"] == "no_consent" and report["sections"] == [] and read == []


def test_when_sedi_knows_nothing_the_report_is_honestly_empty(monkeypatch):
    monkeypatch.setattr(b, "_has_read_consent", lambda db, uid: True)
    monkeypatch.setattr(b, "_facts", lambda db, uid: {})
    monkeypatch.setattr(b, "_about", lambda db, uid, lang: ["نام: سارا"])
    for name in ("_meds", "_plan_lines", "_week_lines", "_follow_up_lines"):
        monkeypatch.setattr(b, name, lambda *a, **k: [])
    for kind in ("doctor_visit", "health_status"):  # an «about + questions» skeleton is not a report
        report = b.build_status_report(None, 1, kind, "fa")
        assert report["state"] == "empty" and report["sections"] == []


def test_one_failing_section_never_breaks_the_report(owners, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(b, "_meds", boom)
    report = b.build_status_report(None, 1, "doctor_visit", "fa")
    assert report["state"] == "ready" and "meds" not in _keys(report) and "reason" in _keys(report)


def test_lines_are_cleaned_deduplicated_clipped_and_capped():
    assert b._items(["  a  b ", "a b", "", None, "x" * 500] + [f"i{n}" for n in range(20)])[0] == "a b"
    items = b._items(["x" * 500] + [f"i{n}" for n in range(20)])
    assert len(items) == b.MAX_ITEMS and len(items[0]) == b.MAX_ITEM_CHARS
    assert b._items("one") == ["one"] and b._items(None) == [] and b._items(5) == []


def test_the_reason_falls_back_to_the_newest_episode():
    facts = {("medical", "symptom_episodes"): ["قدیمی", "تازه"]}
    assert b._section_lines("reason", None, 1, facts, "fa") == ["تازه"]


# --- the real I6 reader ------------------------------------------------------------------------------------------------------------------------
def test_facts_are_read_through_the_consent_gated_i6_reader(monkeypatch):
    from backend.app.services.i6 import memory_writes

    rows = [
        SimpleNamespace(domain="medical", key="health_concerns", value_json='["a"]'),
        SimpleNamespace(domain="work", key="occupation", value_json='"معلم"'),
        SimpleNamespace(domain="x", key="broken", value_json="{not json"),
    ]
    monkeypatch.setattr(memory_writes, "list_facts_readonly_or_empty", lambda db, uid, domain=None: rows)
    assert b._facts(None, 1) == {("medical", "health_concerns"): ["a"], ("work", "occupation"): "معلم"}


# --- the router --------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def client(owners):
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.main import app
    from backend.app.routers.auth_otp import get_current_user

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=7, preferred_language="fa")
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


def test_the_router_lists_kinds_and_returns_a_report(client):
    kinds = client.get("/status-report/kinds").json()
    assert kinds["ok"] is True and [k["kind"] for k in kinds["data"]["kinds"]] == list(b.KINDS)
    body = client.get("/status-report", params={"kind": "doctor_visit"}).json()
    assert body["ok"] is True and body["data"]["state"] == "ready" and body["data"]["kind"] == "doctor_visit"


def test_the_router_rejects_an_unknown_kind_and_honours_the_kill_switch(client, monkeypatch):
    assert client.get("/status-report", params={"kind": "diagnosis"}).status_code == 422
    assert client.get("/status-report").status_code == 422  # kind is required
    monkeypatch.setenv(b.DISABLED_ENV, "1")
    assert client.get("/status-report", params={"kind": "nutrition"}).status_code == 404
    assert client.get("/status-report/kinds").status_code == 404


def test_the_router_needs_an_authenticated_user():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    assert TestClient(app).get("/status-report", params={"kind": "nutrition"}).status_code in (401, 403)


# --- the real owner adapters (owners stubbed at THEIR module) ----------------------------------------------------------------------------------
def test_the_medicine_plan_week_and_follow_up_adapters_read_their_owners(monkeypatch):
    from backend.app.services import user_medication_service as ums
    from backend.app.services.i8 import weekly_user_report as wur
    from backend.app.services.i10 import commitment_followup as cf
    from backend.app.services.lifestyle import a3_weekly_plan_projection as proj

    monkeypatch.setattr(ums, "list_user_medications", lambda db, uid: [{"name": "متفورمین", "user_dosage": "۵۰۰", "reminder_times": ["08:00", "20:00"]}, {"name": "", "reminder_times": []}])
    assert b._meds(None, 1, "fa") == ["متفورمین - ۵۰۰ (ساعت مصرف: 08:00, 20:00)"]
    monkeypatch.setattr(
        proj,
        "build_lifestyle_weekly_plan_projection",
        lambda db, uid: {"days": [{"day_index": 2, "nutrition": [{"title": "املت", "local_time": "08:00"}], "exercise": [{"activity_title": "پیاده‌روی"}]}]},
    )
    assert b._plan_lines(None, 1, "nutrition", "fa") == ["روز 2، ساعت 08:00: املت"]
    assert b._plan_lines(None, 1, "exercise", "fa") == ["روز 2: پیاده‌روی"]
    monkeypatch.setattr(wur, "build_weekly_user_report", lambda db, uid, language=None: {"state": "ready", "totals": {"done": 4, "not_done": 1}})
    assert "4" in b._week_lines(None, 1, "fa")[0] and "1" in b._week_lines(None, 1, "fa")[0]
    monkeypatch.setattr(wur, "build_weekly_user_report", lambda db, uid, language=None: {"state": "empty", "totals": {"done": 0, "not_done": 0}})
    assert b._week_lines(None, 1, "fa") == []  # nothing marked: no invented number
    monkeypatch.setattr(cf, "open_journey_count", lambda db, uid: 1)
    assert b._follow_up_lines(None, 1, "en") == [sedi_copy.t("report.followup.open", "en")]
    monkeypatch.setattr(cf, "open_journey_count", lambda db, uid: 0)
    assert b._follow_up_lines(None, 1, "en") == []


def test_the_identity_lines_come_from_user_state(monkeypatch):
    from backend.app.services.user_context import user_state as us

    monkeypatch.setattr(us, "get_user_state", lambda db, uid: us.UserState(user_id=uid, preferred_name="سارا", age=34))
    assert b._about(None, 1, "fa") == ["نام: سارا", "سن: 34 سال"]
    monkeypatch.setattr(us, "get_user_state", lambda db, uid: None)
    assert b._about(None, 1, "fa") == []
