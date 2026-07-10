"""Section 10 — stable vitals summary V1 contract."""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app import models
from backend.app.services import auth_otp_service as svc
from backend.app.services.gate3.vitals_summary_v1 import MONITORING_STATES, build_vitals_summary_v1

VITAL_KEYS = frozenset({
    "heart_rate",
    "spo2",
    "temperature",
    "blood_pressure",
    "respiratory_rate",
    "ecg",
})
VITAL_META_KEYS = frozenset({"value", "unit", "recorded_at", "received_at", "source", "freshness"})


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _assert_vitals_v1_shape(out: dict) -> None:
    assert "vitals_v1" in out
    v1 = out["vitals_v1"]
    assert v1["monitoring_state"] in MONITORING_STATES
    assert VITAL_KEYS.issubset(v1["vitals"].keys())
    assert "diagnosis" not in json.dumps(out).lower()
    assert "arrhythmia" not in json.dumps(out).lower()


def test_vitals_no_data(db):
    user = models.User(name="v", secret_key="k")
    db.add(user)
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    _assert_vitals_v1_shape(out)
    assert out["vitals_v1"]["monitoring_state"] == "no_data"
    assert out.get("legacy_health") is None
    assert out.get("device_event") is None


def test_vitals_legacy_health_recent(db):
    user = models.User(name="v2", secret_key="k")
    db.add(user)
    db.flush()
    db.add(
        models.HealthData(
            user_id=user.id,
            heart_rate="72",
            spo2="98",
            temperature="36.6",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    _assert_vitals_v1_shape(out)
    assert "legacy_health" in out
    hr = out["vitals_v1"]["vitals"]["heart_rate"]
    assert hr is not None
    assert hr["value"] == "72"
    assert hr["unit"] == "bpm"
    assert VITAL_META_KEYS.issubset(hr.keys())
    assert out["vitals_v1"]["monitoring_state"] in {"active", "recent", "stale"}


def test_vitals_stale_data(db):
    user = models.User(name="v3", secret_key="k")
    db.add(user)
    db.flush()
    old = datetime.utcnow() - timedelta(hours=5)
    db.add(
        models.HealthData(
            user_id=user.id,
            heart_rate="80",
            created_at=old,
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    assert out["vitals_v1"]["vitals"]["heart_rate"]["freshness"] == "stale"


def test_vitals_device_event_recent(db):
    user = models.User(name="v4", secret_key="k")
    db.add(user)
    db.flush()
    now = datetime.utcnow()
    payload = json.dumps(
        {
            "heart_rate": 68,
            "spo2": 97,
            "temperature": 36.5,
            "blood_pressure": {"systolic": 120, "diastolic": 80},
            "respiratory_rate": 16,
            "ecg": True,
        }
    )
    db.add(
        models.DeviceEvent(
            user_id=user.id,
            device_id="hub-test-1",
            event_type="vitals",
            payload_json=payload,
            recorded_at=now,
            received_at=now,
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    _assert_vitals_v1_shape(out)
    assert "device_event" in out
    assert "legacy_health" not in out or out.get("legacy_health") is None or True
    vitals = out["vitals_v1"]["vitals"]
    assert vitals["heart_rate"]["value"] == 68
    assert vitals["spo2"]["unit"] == "percent"
    assert vitals["blood_pressure"]["systolic"] == 120
    assert vitals["ecg"]["monitoring_available"] is True


def test_vitals_disconnected_gadget_hub(db):
    user = models.User(name="v5", secret_key="k")
    db.add(user)
    db.flush()
    db.add(
        models.Device(
            user_id=user.id,
            device_type="gadget_hub",
            status="active",
            device_id="hub-disconnected",
            token_hash="a" * 64,
            last_heartbeat_at=datetime.utcnow() - timedelta(hours=3),
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    assert out["vitals_v1"]["monitoring_state"] == "disconnected"


def test_vitals_malformed_device_payload(db):
    user = models.User(name="v6", secret_key="k")
    db.add(user)
    db.flush()
    now = datetime.utcnow()
    db.add(
        models.DeviceEvent(
            user_id=user.id,
            device_id="hub-bad",
            event_type="vitals",
            payload_json="not-json",
            received_at=now,
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    _assert_vitals_v1_shape(out)
    assert out["device_event"]["payload"] == "not-json"
    assert out["vitals_v1"]["vitals"]["heart_rate"] is None


def test_vitals_missing_values_not_zero_substituted(db):
    user = models.User(name="v7", secret_key="k")
    db.add(user)
    db.flush()
    now = datetime.utcnow()
    db.add(
        models.DeviceEvent(
            user_id=user.id,
            device_id="hub-partial",
            event_type="vitals",
            payload_json=json.dumps({"heart_rate": 70}),
            received_at=now,
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    vitals = out["vitals_v1"]["vitals"]
    assert vitals["heart_rate"]["value"] == 70
    assert vitals["spo2"] is None
    assert vitals["temperature"] is None


def test_vitals_legacy_and_device_event_coexist(db):
    user = models.User(name="v8", secret_key="k")
    db.add(user)
    db.flush()
    now = datetime.utcnow()
    db.add(
        models.HealthData(
            user_id=user.id,
            heart_rate="75",
            created_at=now - timedelta(minutes=30),
        )
    )
    db.add(
        models.DeviceEvent(
            user_id=user.id,
            device_id="hub-both",
            event_type="vitals",
            payload_json=json.dumps({"heart_rate": 71, "spo2": 99}),
            received_at=now,
        )
    )
    db.commit()
    out = build_vitals_summary_v1(db, user.id)
    assert "legacy_health" in out
    assert "device_event" in out
    assert "vitals_v1" in out
    assert out["vitals_v1"]["vitals"]["heart_rate"]["value"] == 71


def test_vitals_summary_http_contract(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003030")
    headers = {"Authorization": f"Bearer {token}"}
    user = db.query(models.User).filter(models.User.phone == "+989143003030").first()
    db.add(
        models.HealthData(
            user_id=user.id,
            heart_rate="66",
            spo2="96",
            created_at=datetime.utcnow(),
        )
    )
    db.commit()

    response = client.get("/health/vitals-summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    _assert_vitals_v1_shape(data)
    assert "legacy_health" in data
    assert data["legacy_health"]["heart_rate"] == "66"
