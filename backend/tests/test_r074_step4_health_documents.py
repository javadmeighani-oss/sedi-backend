"""R-074 step 4: lab results / prescriptions the user CONFIRMS become part of the overall health picture.

Plain-words analysis (flags exactly as the document printed them + arithmetic trends against the user's own earlier documents),
I6 facts read back into chat context, forgotten with the document, three languages, consent and ownership intact."""
from __future__ import annotations

import json

import pytest

from backend.app.core.security import create_access_token
from backend.app.services.i6.memory_writes import list_facts_readonly_or_empty
from backend.app.services.i7 import attachments as att
from backend.app.services.i7 import health_documents as hd
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

PDF = b"%PDF-1.4\n" + b"sedi-test-pdf" * 20


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SEDI_ATTACHMENTS_ENABLED", "true")


def _doc(client, db, monkeypatch, uid, payload, tag):
    monkeypatch.setattr(att, "_analyze_with_openai", lambda b, m, lang: json.dumps(payload, ensure_ascii=False))
    up = client.post("/memory/attachments", files={"file": (f"{tag}.pdf", PDF + tag.encode() * 3, "application/pdf")}, headers=_auth(uid))
    aid = up.json()["data"]["id"]
    done = client.post(f"/memory/attachments/{aid}/process", headers=_auth(uid)).json()["data"]
    return aid, done


def _facts(db, uid):
    return {f.key: str(f.value_json) for f in list_facts_readonly_or_empty(db, uid, domain="medical")}


LAB1 = {
    "document_type": "lab_result", "summary": "آزمایش خون", "date": "2026-09-01",
    "findings": [
        {"name": "LDL", "value": "160", "unit": "mg/dL", "flag": "high"},
        {"name": "HbA1c", "value": "6.4", "unit": "%", "flag": "normal"},
        {"name": "Hemoglobin", "value": "11.2", "unit": "g/dL", "flag": "low"},
    ],
    "medications": [],
}
LAB2 = {
    "document_type": "lab_result", "summary": "آزمایش خون", "date": "2026-11-01",
    "findings": [
        {"name": "LDL", "value": "140", "unit": "mg/dL", "flag": "high"},
        {"name": "HbA1c", "value": "6.4", "unit": "%", "flag": "normal"},
        {"name": "Hemoglobin", "value": "12.9", "unit": "g/dL", "flag": ""},
    ],
    "medications": [],
}
RX = {"document_type": "prescription", "summary": "نسخه", "date": "2026-11-02", "findings": [], "medications": ["Metformin 500", "Atorvastatin"]}


def test_preview_flags_exactly_what_the_document_printed_and_nothing_is_remembered_before_confirm(client, db, monkeypatch):
    u = _user(db, "+17770024001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _aid, done = _doc(client, db, monkeypatch, u.id, LAB1, "a")
    a = done["analysis"]
    assert [f["name"] for f in a["flagged"]] == ["LDL", "Hemoglobin"]  # only what the document marked low/high
    assert a["text"].startswith("3 test results were read, and 2 are marked out of range") and "LDL" in a["text"]  # user language = en
    assert a["trends"] == []  # no earlier confirmed document yet
    assert _facts(db, u.id) == {}  # nothing is stored before the user confirms


def test_confirm_writes_the_picture_and_the_next_document_shows_trends(client, db, monkeypatch):
    u = _user(db, "+17770024002", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid1, _ = _doc(client, db, monkeypatch, u.id, LAB1, "b1")
    conf = client.post(f"/memory/attachments/{aid1}/confirm", headers=_auth(u.id)).json()["data"]
    assert conf["status"] == "confirmed" and "analysis" in conf
    facts = _facts(db, u.id)
    assert "LDL 160 mg/dL (high)" in facts["lab_results"] and "Hemoglobin 11.2" in facts["lab_results"]

    aid2, done2 = _doc(client, db, monkeypatch, u.id, LAB2, "b2")
    trends = {t["name"]: t["direction"] for t in done2["analysis"]["trends"]}
    assert trends == {"LDL": "down", "HbA1c": "same", "Hemoglobin": "up"}
    client.post(f"/memory/attachments/{aid2}/confirm", headers=_auth(u.id))
    latest = _facts(db, u.id)["lab_results"]
    assert "LDL 140" in latest and "LDL 160" not in latest  # the picture holds the LATEST value per test


def test_prescription_names_enter_the_picture_and_deleting_the_document_forgets_them(client, db, monkeypatch):
    u = _user(db, "+17770024003", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, done = _doc(client, db, monkeypatch, u.id, RX, "c")
    assert "Metformin 500" in done["analysis"]["text"]
    client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id))
    assert "Atorvastatin" in _facts(db, u.id)["prescribed_medications"]
    assert client.delete(f"/memory/attachments/{aid}", headers=_auth(u.id)).json()["data"]["deleted"] is True
    assert "prescribed_medications" not in _facts(db, u.id)  # forgetting the document forgets what the picture took from it


def test_chat_context_reads_the_documented_values_back(client, db, monkeypatch):
    from backend.app.services.intelligence.adapters import HealthContextAdapter

    u = _user(db, "+17770024004", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    aid, _ = _doc(client, db, monkeypatch, u.id, LAB1, "d")
    client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id))
    items = HealthContextAdapter._user_stated_health(db, u.id)
    texts = [i.display_text for i in items]
    assert any(t.startswith("documented_lab_results=") and "LDL 160" in t for t in texts)


@pytest.mark.parametrize("lang,marker", [("fa", "خارج از محدوده"), ("ar", "خارج النطاق"), ("en", "out of range")])
def test_the_analysis_speaks_three_languages(db, lang, marker):
    u = _user(db, f"+1777002402{['fa', 'ar', 'en'].index(lang)}", tz="Asia/Tehran")
    a = hd.analyse(db, u.id, LAB1, attachment_id=None, language=lang, confirmed=False)
    assert marker in a["text"]


def test_numbers_trends_and_bounds_are_deterministic():
    assert hd._num("۱۴۰٫۵") == 140.5 and hd._num("abc") is None and hd._num("6,4 %") == 6.4
    prev = [{"date": "2026-01-01", "findings": [{"name": "LDL ", "value": "100", "unit": "mg/dL"}]}]
    cur = [{"name": "ldl", "value": "102", "unit": "mg/dL"}]
    assert hd._trends(cur, prev)[0]["direction"] == "same"  # within 3 %
    assert hd._trends([{"name": "LDL", "value": "130", "unit": "mg/dL"}], prev)[0]["direction"] == "up"
    assert hd._trends([{"name": "LDL", "value": "130", "unit": ""}], prev) == []  # a missing unit is not guessed
    assert hd._trends([{"name": "X", "value": "1", "unit": ""}], prev) == []


def test_without_consent_nothing_is_written_and_the_confirm_is_refused(client, db, monkeypatch):
    u = _user(db, "+17770024005", tz="Asia/Tehran")
    r = client.post("/memory/attachments", files={"file": ("a.pdf", PDF, "application/pdf")}, headers=_auth(u.id))
    assert r.status_code == 403
    assert _facts(db, u.id) == {}


def test_the_two_keys_are_i6_owned_and_projected():
    from backend.app.services.memory.memory_contract import I6_USER_STATED_HEALTH_KEYS, MemoryContract

    for key in ("lab_results", "prescribed_medications"):
        assert ("medical", key) in I6_USER_STATED_HEALTH_KEYS
        assert MemoryContract.validate_fact("medical", key) == (True, None)


def test_trends_compare_only_matching_units_and_only_earlier_documents():
    """Codex P2 (PR 157): mg/dL vs mmol/L are different scales; a later-dated document is never a 'before'."""
    prev = [{"date": "2026-01-01", "findings": [{"name": "LDL", "value": "3.4", "unit": "mmol/L"}]}]
    assert hd._trends([{"name": "LDL", "value": "130", "unit": "mg/dL"}], prev, "2026-06-01") == []
    same_unit = [{"date": "2026-01-01", "findings": [{"name": "LDL", "value": "100", "unit": "mg/dL"}]}]
    assert hd._trends([{"name": "LDL", "value": "130", "unit": "mg / dL"}], same_unit, "2026-06-01")[0]["direction"] == "up"
    later = [{"date": "2026-12-01", "findings": [{"name": "LDL", "value": "100", "unit": "mg/dL"}]}]
    assert hd._trends([{"name": "LDL", "value": "130", "unit": "mg/dL"}], later, "2026-06-01") == []


def test_a_backdated_report_confirmed_later_does_not_overwrite_the_newer_result(client, db, monkeypatch):
    u = _user(db, "+17770024006", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    newer = dict(LAB2)  # 2026-11-01, LDL 140
    older = dict(LAB1)  # 2026-09-01, LDL 160
    aid_new, _ = _doc(client, db, monkeypatch, u.id, newer, "e1")
    client.post(f"/memory/attachments/{aid_new}/confirm", headers=_auth(u.id))
    aid_old, _ = _doc(client, db, monkeypatch, u.id, older, "e2")
    client.post(f"/memory/attachments/{aid_old}/confirm", headers=_auth(u.id))
    latest = _facts(db, u.id)["lab_results"]
    assert "LDL 140" in latest and "LDL 160" not in latest  # the picture keeps the newest REPORT date
