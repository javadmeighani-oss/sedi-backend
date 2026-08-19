"""Gate 1 — structured profile facts API."""

import os
from unittest.mock import patch

import pytest

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc


@pytest.fixture(autouse=True)
def _enable_legacy_profile_fact_writes(monkeypatch):
    """Legacy user_profile_facts stack is frozen by default (I6); gate1 tests exercise that API."""
    monkeypatch.setenv("SEDI_LEGACY_FACT_WRITES_ENABLED", "true")


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_profile_facts_requires_auth(client):
    assert client.get("/user/profile-facts").status_code == 401


def test_profile_facts_crud(client, db, monkeypatch):
    phone = "+989142002001"
    token = _token(client, db, monkeypatch, phone)
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/user/profile-facts",
        json={"fact_type": "allergy", "value": "peanuts", "source": "manual"},
        headers=headers,
    )
    assert create.status_code == 200, create.text
    fact_id = create.json()["data"]["id"]

    listing = client.get("/user/profile-facts", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()["data"]["profile_facts"]) == 1

    patch_r = client.patch(
        f"/user/profile-facts/{fact_id}",
        json={"value": "tree pollen", "verified": True},
        headers=headers,
    )
    assert patch_r.status_code == 200
    assert patch_r.json()["data"]["value"] == "tree pollen"

    delete_r = client.delete(f"/user/profile-facts/{fact_id}", headers=headers)
    assert delete_r.status_code == 200


def test_profile_facts_rejects_user_id_query(client, db, monkeypatch):
    phone = "+989142002002"
    token = _token(client, db, monkeypatch, phone)
    r = client.get("/user/profile-facts?user_id=1", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_profile_facts_cross_user_isolation(client, db, monkeypatch):
    t1 = _token(client, db, monkeypatch, "+989142002003")
    t2 = _token(client, db, monkeypatch, "+989142002004")
    created = client.post(
        "/user/profile-facts",
        json={"fact_type": "occupation", "value": "engineer"},
        headers={"Authorization": f"Bearer {t1}"},
    )
    fid = created.json()["data"]["id"]
    assert client.patch(
        f"/user/profile-facts/{fid}",
        json={"value": "hacker"},
        headers={"Authorization": f"Bearer {t2}"},
    ).status_code == 404
