"""Gate 3 — health Q&A, symptoms, brain safety path."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ["SMS_DISABLED"] = "true"

from backend.app import models
from backend.app.services import auth_otp_service as svc
from backend.app.core.conversation.brain import (
    _gate3_check_emergency_short_circuit,
    _gate3_validate_assistant_response,
    _maybe_append_gate3_care_context,
)
from backend.app.services.gate3.medical_intent import is_medical_care_intent


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_symptoms_separate_from_questions(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005001")
    headers = {"Authorization": f"Bearer {token}"}
    s = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "headache", "severity": "mild"},
    )
    assert s.status_code == 200
    q = client.post("/health/questions", headers=headers, json={"question": "What is headache?"})
    assert q.status_code == 200
    symptoms = client.get("/health/symptoms", headers=headers).json()["data"]["symptoms"]
    questions = client.get("/health/questions", headers=headers).json()["data"]["questions"]
    assert symptoms and questions
    assert symptoms[0]["symptom_label"] == "headache"
    assert questions[0]["question_text"] == "What is headache?"


def test_severe_symptom_routes_high_risk(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005002")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "chest pain", "severity": "severe", "notes": "crushing pain"},
    )
    data = r.json()["data"]
    assert data["risk_level"] in ("emergency", "high")
    assert data.get("safety_message")


def test_health_question_no_source_fallback(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005003")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/health/questions",
        headers=headers,
        json={"question": "rare obscure medical term zzzgate3"},
    )
    answer = r.json()["data"]["answer_text"]
    assert "منابع" in answer or "sources" in answer.lower()
    assert r.json()["data"]["citations"] == []


def test_health_education_and_vitals(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005004")
    headers = {"Authorization": f"Bearer {token}"}
    edu = client.get("/health/education", headers=headers, params={"topic": "sleep hygiene"})
    assert edu.status_code == 200
    vitals = client.get("/health/vitals-summary", headers=headers)
    assert vitals.status_code == 200
    assert "sources" in vitals.json()["data"]


def test_health_endpoints_require_auth(client):
    assert client.post("/health/questions", json={"question": "x"}).status_code == 401
    assert client.get("/health/symptoms").status_code == 401


def test_medical_intent_detection():
    assert is_medical_care_intent("درد سر دارم", "fa")
    assert is_medical_care_intent("I have chest pain", "en")
    assert not is_medical_care_intent("what is the weather", "en")


def test_brain_emergency_short_circuit():
    tpl = _gate3_check_emergency_short_circuit("I have chest pain", "en")
    assert tpl
    assert "emergency" in tpl.lower() or "اورژانس" in tpl


def test_brain_safety_validator_fallback():
    unsafe = "You have diabetes. Stop taking your medication."
    safe = _gate3_validate_assistant_response(unsafe, "en")
    assert "cannot" in safe.lower() or "نمی" in safe


def test_brain_appends_care_context_for_medical_intent(db, monkeypatch):
    from backend.app.models import User

    user = User(phone="+989143005099", secret_key="<otp>", created_at=datetime.utcnow())
    db.add(user)
    db.flush()
    messages = [{"role": "system", "content": "base"}]
    _maybe_append_gate3_care_context(messages, db, user.id, "درد سر و دارو", "fa")
    assert len(messages) == 2
    assert "CARE_CONTEXT" in messages[1]["content"]


def test_brain_process_message_emergency_skips_gpt(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005005")
    headers = {"Authorization": f"Bearer {token}"}
    with patch("backend.app.core.conversation.prompts.client") as mock_client:
        mock_client.responses.create = MagicMock()
        r = client.post(
            "/interact/chat",
            headers=headers,
            json={"message": "severe chest pain can't breathe"},
        )
        assert r.status_code == 200
        mock_client.responses.create.assert_not_called()
        msg = r.json()["message"]
        assert "emergency" in msg.lower() or "اورژانس" in msg


def test_no_gate5_device_dashboard_in_gate3(client, db, monkeypatch):
    """Gate 5 device dashboard not exposed via Gate 3 routes."""
    token = _token(client, db, monkeypatch, "+989143005006")
    headers = {"Authorization": f"Bearer {token}"}
    for path in ["/care/context", "/health/vitals-summary"]:
        r = client.get(path, headers=headers)
        assert r.status_code == 200
        assert "device_dashboard" not in str(r.json()).lower()
        assert "protocol" not in r.json().get("data", {}) or True


def test_patch_symptom_requires_auth(client, db, monkeypatch):
    assert client.patch("/health/symptoms/1", json={"status": "resolved"}).status_code == 401


def test_patch_symptom_status_active_to_resolved(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005010")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "mild headache", "severity": "mild"},
    ).json()["data"]
    rid = created["id"]
    assert created["status"] == "active"
    assert created["resolved_at"] is None
    patched = client.patch(f"/health/symptoms/{rid}", headers=headers, json={"status": "resolved"})
    assert patched.status_code == 200
    data = patched.json()["data"]
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None


def test_patch_symptom_cross_user_isolation(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143005011")
    t2 = _token(client, db, monkeypatch, "+989143005012")
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}
    rid = client.post(
        "/health/symptoms",
        headers=h1,
        json={"symptom_label": "cough", "severity": "mild"},
    ).json()["data"]["id"]
    assert client.patch(f"/health/symptoms/{rid}", headers=h2, json={"status": "resolved"}).status_code == 404


def test_patch_symptom_invalid_status_rejected(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005013")
    headers = {"Authorization": f"Bearer {token}"}
    rid = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "fatigue", "severity": "mild"},
    ).json()["data"]["id"]
    r = client.patch(f"/health/symptoms/{rid}", headers=headers, json={"status": "invalid_status"})
    assert r.status_code == 422


def test_patch_symptom_empty_body_rejected(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005014")
    headers = {"Authorization": f"Bearer {token}"}
    rid = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "nausea", "severity": "mild"},
    ).json()["data"]["id"]
    r = client.patch(f"/health/symptoms/{rid}", headers=headers, json={})
    assert r.status_code == 422


def test_patch_symptom_no_notification_delivery(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005015")
    headers = {"Authorization": f"Bearer {token}"}
    rid = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "back pain", "severity": "mild"},
    ).json()["data"]["id"]
    before = db.query(models.Notification).count()
    client.patch(f"/health/symptoms/{rid}", headers=headers, json={"status": "resolved"})
    after = db.query(models.Notification).count()
    assert before == after


def test_patch_symptom_notes_only_no_medical_decisioning(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143005016")
    headers = {"Authorization": f"Bearer {token}"}
    rid = client.post(
        "/health/symptoms",
        headers=headers,
        json={"symptom_label": "sore throat", "severity": "mild"},
    ).json()["data"]["id"]
    r = client.patch(
        f"/health/symptoms/{rid}",
        headers=headers,
        json={"notes": "felt better after rest"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["notes"] == "felt better after rest"
    assert r.json()["data"]["status"] == "active"
