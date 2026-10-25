"""R-021 / M4: documents, images and voice from the chat box — governed, bounded, confirmed by the user."""
from __future__ import annotations

import json

import pytest

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i7 import attachments as att
from backend.app.services.i7 import life_events as le
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

JPEG = b"\xff\xd8\xff\xe0" + b"sedi-test-image" * 20
PDF = b"%PDF-1.4\n" + b"sedi-test-pdf" * 20
M4A = b"\x00\x00\x00\x18ftypM4A " + b"sedi-test-audio" * 20


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SEDI_ATTACHMENTS_ENABLED", "true")


def _up(client, uid, data, name="x.jpg", mime="image/jpeg"):
    return client.post("/memory/attachments", files={"file": (name, data, mime)}, headers=_auth(uid))


def test_feature_is_off_by_default(client, db, monkeypatch):
    monkeypatch.delenv("SEDI_ATTACHMENTS_ENABLED", raising=False)
    u = _user(db, "+17770023001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    assert _up(client, u.id, JPEG).status_code == 404
    assert client.get("/memory/attachments", headers=_auth(u.id)).status_code == 404


def test_upload_validates_type_content_size_consent_and_dedupes(client, db, monkeypatch):
    u = _user(db, "+17770023002", tz="Asia/Tehran")
    assert _up(client, u.id, JPEG).status_code == 403  # no memory.write
    _seed_consent(db, u.id)
    ok = _up(client, u.id, JPEG, "../../etc/passwd.jpg")
    assert ok.status_code == 200, ok.text
    meta = ok.json()["data"]
    assert meta["kind"] == "image" and meta["status"] == "stored" and "/" not in (meta["filename"] or "")
    assert _up(client, u.id, JPEG).json()["data"]["id"] == meta["id"]  # same bytes -> same row
    assert _up(client, u.id, b"not really a jpeg at all", "a.jpg").status_code == 415  # magic bytes decide
    assert _up(client, u.id, PDF, "a.exe", "application/x-msdownload").status_code == 415
    monkeypatch.setitem(att.MAX_BYTES, "image", 100)
    assert _up(client, u.id, JPEG + b"x" * 300, "big.jpg").status_code == 413
    assert _up(client, u.id, b"", "empty.jpg").status_code in (400, 415)


def test_document_is_read_then_confirmed_by_the_user_then_forgotten(client, db, monkeypatch):
    u = _user(db, "+17770023003", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    payload = {"document_type": "lab_result", "summary": "آزمایش خون؛ قند ناشتا کمی بالاتر از محدوده", "date": "2026-10-01",
               "findings": [{"name": "FBS", "value": "118", "unit": "mg/dL", "flag": "high"}, {"name": "", "value": "x"}],
               "medications": ["Metformin"], "diagnosis": "SHOULD_BE_DROPPED"}
    monkeypatch.setattr(att, "_analyze_with_openai", lambda b, m, lang: json.dumps(payload, ensure_ascii=False))
    aid = _up(client, u.id, PDF, "lab.pdf", "application/pdf").json()["data"]["id"]
    done = client.post(f"/memory/attachments/{aid}/process", headers=_auth(u.id)).json()["data"]
    assert done["status"] == "ready" and done["findings"]["findings"] == [{"name": "FBS", "value": "118", "unit": "mg/dL", "flag": "high"}]
    assert "diagnosis" not in done["findings"]
    assert le.list_life_events(db, u.id) == []  # nothing is remembered until the user says so
    conf = client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id)).json()["data"]
    assert conf["status"] == "confirmed"
    tl = le.list_life_events(db, u.id)
    assert tl[0]["kind"] == "medical_document" and tl[0]["source"] == "document" and tl[0]["occurred_at"].startswith("2026-10-01")
    other = _user(db, "+17770023004", tz="Asia/Tehran")
    _seed_consent(db, other.id)
    assert client.get(f"/memory/attachments/{aid}", headers=_auth(other.id)).status_code == 404
    assert client.delete(f"/memory/attachments/{aid}", headers=_auth(other.id)).status_code == 404
    assert client.delete(f"/memory/attachments/{aid}", headers=_auth(u.id)).json()["data"]["deleted"] is True
    assert le.list_life_events(db, u.id) == []  # forgetting the document forgets what came from it
    assert db.query(models.UserAttachment).count() == 0


def test_voice_is_transcribed_and_the_audio_is_not_kept(client, db, monkeypatch):
    u = _user(db, "+17770023005", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    monkeypatch.setattr(att, "_transcribe_with_openai", lambda b, n, m, lang: "امروز سرم خیلی درد می‌کنه")
    aid = _up(client, u.id, M4A, "voice.m4a", "audio/mp4").json()["data"]["id"]
    out = client.post(f"/memory/attachments/{aid}/process", headers=_auth(u.id)).json()["data"]
    assert out["transcript"] == "امروز سرم خیلی درد می‌کنه" and out["status"] == "ready"
    row = db.query(models.UserAttachment).filter_by(id=aid).one()
    assert row.content is None
    assert client.post(f"/memory/attachments/{aid}/confirm", headers=_auth(u.id)).status_code == 409  # audio is not a document


def test_processing_failure_is_reported_not_stored_as_truth(client, db, monkeypatch):
    u = _user(db, "+17770023006", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    monkeypatch.setattr(att, "_analyze_with_openai", lambda b, m, lang: "I cannot read this")
    aid = _up(client, u.id, JPEG).json()["data"]["id"]
    r = client.post(f"/memory/attachments/{aid}/process", headers=_auth(u.id))
    assert r.status_code == 502 and r.json()["detail"] == "PROCESSING_FAILED"
    assert db.query(models.UserAttachment).filter_by(id=aid).one().status == "failed"


def test_findings_validator_bounds():
    assert att.validate_document_findings("nope") is None
    assert att.validate_document_findings('{"summary": ""}') is None
    big = {"summary": "x" * 900, "findings": [{"name": f"n{i}", "value": "v"} for i in range(80)], "date": "31/12/2026"}
    out = att.validate_document_findings(json.dumps(big))
    assert len(out["summary"]) == att.MAX_SUMMARY_CHARS and len(out["findings"]) == att.MAX_FINDINGS and out["date"] == ""
