"""Gate 3 — curated knowledge base admin, search, freshness."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app import models
from backend.app.services import auth_otp_service as svc


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _admin_headers(monkeypatch) -> dict:
    monkeypatch.setenv("ADMIN_TOKEN", "gate3-admin-test")
    return {"X-Admin-Token": "gate3-admin-test"}


def _ingest_and_approve(client, h, **payload) -> dict:
    ing = client.post("/knowledge-base/ingest", headers=h, json=payload)
    assert ing.status_code == 200
    data = ing.json()["data"]
    if data.get("review_status") == "pending_review":
        run_id = data["ingestion_run_id"]
        appr = client.post(f"/knowledge-base/ingestion-runs/{run_id}/approve", headers=h)
        assert appr.status_code == 200
        return appr.json()["data"]
    return data


def _seed_source(db, slug: str, *, status="active", last_checked=None, trust="clinical_guideline"):
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug=slug,
        name=f"Source {slug}",
        category="medical_condition",
        trust_level=trust,
        source_url=f"https://example.org/{slug}",
        locale="fa",
        last_checked_at=last_checked or now,
        freshness_policy_days=180,
        ingestion_status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(src)
    db.flush()
    return src


def test_kb_admin_requires_token(client, db, monkeypatch):
    assert client.get("/knowledge-base/sources").status_code in (401, 404)
    h = _admin_headers(monkeypatch)
    assert client.get("/knowledge-base/sources", headers=h).status_code == 200


def test_kb_source_document_ingest_search(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    r = client.post(
        "/knowledge-base/sources",
        headers=h,
        json={
            "slug": "who-hypertension",
            "name": "WHO Hypertension",
            "category": "medical_condition",
            "trust_level": "clinical_guideline",
            "source_url": "https://who.int/hypertension",
            "ingestion_status": "draft",
        },
    )
    assert r.status_code == 200
    source_id = r.json()["data"]["id"]

    doc = client.post(
        "/knowledge-base/documents",
        headers=h,
        json={"source_id": source_id, "title": "Hypertension basics", "category": "medical_condition", "status": "active"},
    )
    assert doc.status_code == 200
    document_id = doc.json()["data"]["id"]

    ing = client.post(
        "/knowledge-base/ingest",
        headers=h,
        json={
            "source_id": source_id,
            "document_id": document_id,
            "content": "Hypertension education: monitor blood pressure regularly and follow clinician guidance.",
            "category": "medical_condition",
        },
    )
    assert ing.status_code == 200
    run_id = ing.json()["data"]["ingestion_run_id"]
    assert ing.json()["data"]["review_status"] == "pending_review"
    appr = client.post(f"/knowledge-base/ingestion-runs/{run_id}/approve", headers=h)
    assert appr.status_code == 200
    assert appr.json()["data"]["chunks_created"] >= 1

    token = _token(client, db, monkeypatch, "+989143003001")
    search = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "hypertension blood pressure"},
    )
    assert search.status_code == 200
    chunks = search.json()["data"]["chunks"]
    assert chunks
    assert chunks[0]["citation"]["source_name"]


def test_kb_stale_and_deprecated_excluded(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    stale = _seed_source(db, "stale-src", last_checked=datetime.utcnow() - timedelta(days=400))
    fresh = _seed_source(db, "fresh-src")
    db.commit()

    for src, title, text in [
        (stale, "Stale doc", "stale unique term xyz123 for knowledge freshness testing scenario"),
        (fresh, "Fresh doc", "fresh unique term xyz123 for knowledge freshness testing scenario"),
    ]:
        _ingest_and_approve(
            client, h,
            source_id=src.id, title=title, content=text, category="lifestyle",
        )

    token = _token(client, db, monkeypatch, "+989143003002")
    res = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "xyz123"},
    )
    chunks = res.json()["data"]["chunks"]
    assert len(chunks) == 1
    assert chunks[0]["citation"]["source_name"] == "Source fresh-src"

    client.patch(
        f"/knowledge-base/sources/{fresh.id}",
        headers=h,
        json={"ingestion_status": "deprecated"},
    )
    res2 = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "xyz123"},
    )
    assert res2.json()["data"]["chunks"] == []


def test_kb_provider_multi_option_and_no_best_doctor(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_source(db, "providers-curated", trust="vetted_partner")
    db.commit()
    for city, name in [("Tehran", "Clinic Alpha"), ("Tehran", "Clinic Beta")]:
        _ingest_and_approve(
            client, h,
            source_id=src.id,
            title=name,
            category="provider_directory",
            content=f"{name} cardiology provider directory curated listing Tehran with citation metadata",
        )

    token = _token(client, db, monkeypatch, "+989143003003")
    res = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "cardiology Tehran provider", "category": "provider_directory"},
    )
    chunks = res.json()["data"]["chunks"]
    assert len(chunks) >= 2
    assert res.json()["data"].get("disclaimer")

    blocked = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "best doctor cardiology Tehran"},
    )
    data = blocked.json()["data"]
    assert data.get("ranking_language_reframed") is True
    assert len(data.get("chunks") or []) >= 2
    assert data.get("disclaimer")


def test_kb_search_requires_jwt(client, db):
    assert client.get("/knowledge-base/search", params={"q": "test"}).status_code == 401


def test_kb_rejects_user_id_query(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143003004")
    r = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "test", "user_id": "1"},
    )
    assert r.status_code == 422
