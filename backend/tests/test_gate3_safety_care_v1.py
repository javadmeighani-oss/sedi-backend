"""Gate 3 — safety core, care context, recommendations, follow-ups."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app import models
from backend.app.services import auth_otp_service as svc
from backend.app.services.gate3.safety_core import RiskClassifier, SafetyPolicy
from backend.app.services.gate3.safety_validator import validate_response_text
from backend.app.services.gate3.care_intelligence import build_care_context, get_vitals_summary


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]



def test_risk_classifier_emergency_cases():
    rc = RiskClassifier()
    for msg in [
        "I have severe chest pain",
        "signs of stroke slurred speech",
        "I want to kill myself",
        "severe bleeding won't stop",
        "anaphylaxis severe allergic reaction",
        "درد قفسه سینه دارم",
    ]:
        assert rc.classify(msg, "en" if msg[0].isascii() else "fa").risk_level == "emergency"


def test_safety_policy_forbids_unsafe_llm_on_emergency():
    p = SafetyPolicy().evaluate("emergency")
    assert p["llm_allowed"] is False
    assert p["kb_allowed"] is False
    assert p["template_key"] == "emergency"


def test_safety_validator_blocks_diagnosis_and_medication_orders():
    assert validate_response_text("You have diabetes for sure")[0] is False
    assert validate_response_text("You have depression disorder")[0] is False
    assert validate_response_text("Increase your dose to 20mg")[0] is False
    assert validate_response_text("Stop taking your medication now")[0] is False
    assert validate_response_text("the best doctor in town")[0] is False
    assert validate_response_text("General wellness tips are helpful.")[0] is True


def test_risk_classifier_mental_wellbeing_medium():
    rc = RiskClassifier()
    assert rc.classify("I feel stressed at night and need sleep support", "en").risk_level == "medium"
    assert rc.classify("احساس استرس دارم و خوابم بد شده", "fa").risk_level == "medium"


def test_care_context_uses_canonical_gate2_data(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004001")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/user/goals", json={"category": "health", "title": "walk daily"}, headers=headers)
    client.post(
        "/user/restrictions",
        json={"restriction_type": "diet", "title": "low salt"},
        headers=headers,
    )
    r = client.get("/care/context", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(g.get("title") == "walk daily" for g in data.get("goals", []))
    assert any(x.get("title") == "low salt" for x in data.get("restrictions", []))
    assert "vitals_summary" in data


def test_vitals_read_unified_sources(db, monkeypatch):
    from backend.app.models import User

    user = User(phone="+989143004099", secret_key="<otp>", created_at=datetime.utcnow())
    db.add(user)
    db.flush()
    db.add(
        models.HealthData(
            user_id=user.id,
            heart_rate="72",
            temperature="36.6",
            spo2="98",
            created_at=datetime.utcnow(),
        )
    )
    db.add(
        models.DeviceEvent(
            user_id=user.id,
            device_id="dev1",
            event_type="heart_rate",
            payload_json='{"bpm": 70}',
            received_at=datetime.utcnow(),
        )
    )
    db.flush()
    summary = get_vitals_summary(db, user.id)
    assert "health_data" in summary["sources"]
    assert "device_events" in summary["sources"]


def test_safety_check_endpoint(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004002")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/care/safety-check", headers=headers, json={"message": "chest pain"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["assessment"]["risk_level"] == "emergency"
    assert data["template"]
    assert "forbidden_actions" in data["policy"]


def test_recommendations_educational_only(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004003")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/user/events",
        json={
            "title": "Blood test",
            "event_type": "lab_test",
            "starts_at": (datetime.utcnow() + timedelta(days=3)).isoformat() + "Z",
        },
        headers=headers,
    )
    r = client.post(
        "/care/recommendations",
        headers=headers,
        json={"trigger_message": "prepare for my lab test"},
    )
    assert r.status_code == 200
    recs = r.json()["data"]["recommendations"]
    assert recs
    body = recs[0]["body"].lower()
    assert "educational" in body or "general" in body
    assert "stop" not in body or "not medical orders" in body


def test_emergency_blocks_recommendations(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004004")
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/care/recommendations",
        headers=headers,
        json={"trigger_message": "severe chest pain emergency"},
    )
    assert r.json()["data"]["recommendations"] == []


def test_follow_up_crud_and_cross_user_isolation(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989143004005")
    t2 = _token(client, db, monkeypatch, "+989143004006")
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}
    created = client.post("/care/follow-ups", headers=h1, json={"title": "Call clinic"}).json()["data"]
    tid = created["id"]
    assert client.get("/care/follow-ups", headers=h1).json()["data"]["follow_ups"][0]["title"] == "Call clinic"
    assert client.patch(f"/care/follow-ups/{tid}", headers=h1, json={"status": "done"}).status_code == 200
    assert client.patch(f"/care/follow-ups/{tid}", headers=h2, json={"status": "done"}).status_code == 404
    assert client.delete(f"/care/follow-ups/{tid}", headers=h1).status_code == 200


def test_care_endpoints_require_auth(client):
    assert client.get("/care/context").status_code == 401
    assert client.post("/care/safety-check", json={"message": "hi"}).status_code == 401


def test_care_rejects_user_id_query(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004007")
    r = client.get("/care/context", headers={"Authorization": f"Bearer {token}"}, params={"user_id": "1"})
    assert r.status_code == 422


def test_no_notification_delivery_from_care(client, db, monkeypatch):
    """Gate 4: care endpoints must not create notification rows."""
    token = _token(client, db, monkeypatch, "+989143004008")
    headers = {"Authorization": f"Bearer {token}"}
    before = db.query(models.Notification).count()
    client.post("/care/analyze", headers=headers, json={"message": "mild headache"})
    client.post("/care/recommendations", headers=headers, json={"trigger_message": "wellness"})
    after = db.query(models.Notification).count()
    assert before == after


def test_build_care_context_no_legacy_user_facts_only(db, monkeypatch):
    from backend.app.models import User

    user = User(phone="+989143004010", secret_key="<otp>", created_at=datetime.utcnow())
    db.add(user)
    db.flush()
    ctx = build_care_context(db, user.id)
    assert "legacy_user_facts" not in ctx
    assert "pending_kc_candidates" not in ctx
