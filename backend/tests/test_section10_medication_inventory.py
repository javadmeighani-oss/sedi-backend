"""Section 10 — medication inventory and stock classification."""

import os
from datetime import datetime
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app import models
from backend.app.services import auth_otp_service as svc
from backend.app.services.section10.medication_stock_service import StockLevel, classify_medication_stock

MEDICATION_INVENTORY_FIELDS = frozenset({
    "remaining_quantity",
    "quantity_unit",
    "refill_threshold",
    "last_refill_at",
    "estimated_end_at",
    "stock_level",
    "reminder_enabled",
    "reminder_times",
    "interval_hours",
    "timezone",
})


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _create_medication(client, headers, **overrides):
    body = {
        "name": "InventoryMed",
        "user_dosage": "10mg",
        "reminder_enabled": True,
        "timezone": "Asia/Tehran",
        "reminder_times": ["08:00"],
        "interval_hours": 8,
    }
    body.update(overrides)
    return client.post("/user/medications", json=body, headers=headers)


def test_stock_classification():
    um = models.UserMedication(user_id=1, medication_id=1, interval_hours=8)
    assert classify_medication_stock(um) == StockLevel.UNKNOWN

    um.remaining_quantity = 5
    um.refill_threshold = 3
    assert classify_medication_stock(um) == StockLevel.SUFFICIENT

    um.remaining_quantity = 2
    assert classify_medication_stock(um) == StockLevel.LOW

    um.remaining_quantity = 0
    assert classify_medication_stock(um) == StockLevel.EMPTY


def test_medication_response_contract_get_and_patch(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003020")
    headers = {"Authorization": f"Bearer {token}"}

    created = _create_medication(
        client,
        headers,
        remaining_quantity=30,
        quantity_unit="tablets",
        refill_threshold=5,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True
    data = body["data"]
    assert MEDICATION_INVENTORY_FIELDS.issubset(data.keys())
    assert data["stock_level"] == "sufficient"
    assert data["remaining_quantity"] == 30
    assert data["quantity_unit"] == "tablets"
    assert data["user_dosage"] == "10mg"
    med_id = data["id"]

    listed = client.get("/user/medications", headers=headers)
    assert listed.status_code == 200
    med = listed.json()["data"]["medications"][0]
    assert MEDICATION_INVENTORY_FIELDS.issubset(med.keys())
    assert med["stock_level"] == "sufficient"

    refill_at = datetime(2026, 6, 1, 12, 0, 0).isoformat() + "Z"
    end_at = datetime(2026, 7, 1, 12, 0, 0).isoformat() + "Z"
    patch_body = {
        "reminder_enabled": False,
        "reminder_times": ["09:00", "21:00"],
        "interval_hours": 12,
        "timezone": "UTC",
        "remaining_quantity": 4,
        "quantity_unit": "capsules",
        "refill_threshold": 5,
        "last_refill_at": refill_at,
        "estimated_end_at": end_at,
    }
    patched = client.patch(f"/user/medications/{med_id}", json=patch_body, headers=headers)
    assert patched.status_code == 200
    pdata = patched.json()["data"]
    assert pdata["reminder_enabled"] is False
    assert set(pdata["reminder_times"]) == {"09:00", "21:00"}
    assert pdata["interval_hours"] == 12
    assert pdata["timezone"] == "UTC"
    assert pdata["remaining_quantity"] == 4
    assert pdata["quantity_unit"] == "capsules"
    assert pdata["stock_level"] == "low"
    assert pdata["user_dosage"] == "10mg"


def test_medication_missing_inventory_stock_unknown(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003021")
    headers = {"Authorization": f"Bearer {token}"}
    created = _create_medication(client, headers)
    assert created.status_code == 200
    assert created.json()["data"]["stock_level"] == "unknown"


def test_medication_negative_quantity_rejected(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003022")
    headers = {"Authorization": f"Bearer {token}"}
    bad_create = _create_medication(client, headers, remaining_quantity=-1)
    assert bad_create.status_code == 422
    med_id = _create_medication(client, headers).json()["data"]["id"]
    bad_patch = client.patch(
        f"/user/medications/{med_id}",
        json={"remaining_quantity": -2},
        headers=headers,
    )
    assert bad_patch.status_code == 422


def test_medication_negative_refill_threshold_rejected(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003023")
    headers = {"Authorization": f"Bearer {token}"}
    med_id = _create_medication(client, headers).json()["data"]["id"]
    bad_patch = client.patch(
        f"/user/medications/{med_id}",
        json={"refill_threshold": -1},
        headers=headers,
    )
    assert bad_patch.status_code == 422


def test_medication_patch_accepts_gate3_frontend_keys(client, db, monkeypatch):
    """PATCH accepts exactly the keys sent by Gate 3 UserMedicationDto.toScheduleUpdateJson."""
    token = _token(client, db, monkeypatch, "+989143003024")
    headers = {"Authorization": f"Bearer {token}"}
    med_id = _create_medication(client, headers).json()["data"]["id"]
    frontend_patch = {
        "reminder_enabled": True,
        "reminder_times": ["07:30"],
        "interval_hours": 8,
        "timezone": "Asia/Tehran",
        "remaining_quantity": 12.5,
        "quantity_unit": "tablets",
        "refill_threshold": 3,
    }
    patched = client.patch(f"/user/medications/{med_id}", json=frontend_patch, headers=headers)
    assert patched.status_code == 200
    pdata = patched.json()["data"]
    assert pdata["remaining_quantity"] == 12.5
    assert pdata["quantity_unit"] == "tablets"
    assert pdata["refill_threshold"] == 3
    assert pdata["stock_level"] == "sufficient"
