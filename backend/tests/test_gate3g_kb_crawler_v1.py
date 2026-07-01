"""Gate 3G — curated KB fetch, SSRF, robots, AI review, admin approval."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

os.environ["SMS_DISABLED"] = "true"

import pytest

from backend.app import models
from backend.app.services import auth_otp_service as svc
from backend.app.services.gate3.content_parser import parse_content
from backend.app.services.gate3.fetch_security import FetchSecurityError, validate_fetch_url
from backend.app.services.gate3.knowledge_ai_review_service import KnowledgeAIReviewService
from backend.app.services.gate3.kb_scheduler import run_scheduled_kb_fetch, scheduled_fetch_enabled
from backend.app.services.gate3.knowledge_update_service import apply_ai_review_to_run
from backend.app.services.gate3.source_review_policy import normalize_source_review_policy


def test_normalize_sensitive_category_review_policy():
    review_required, auto_approve = normalize_source_review_policy(
        "medical_condition", review_required=False, auto_approve_low_risk=True,
    )
    assert review_required is True
    assert auto_approve is False
    review_required, auto_approve = normalize_source_review_policy(
        "provider_directory", review_required=False, auto_approve_low_risk=True,
    )
    assert review_required is True
    assert auto_approve is False


def test_normalize_low_risk_allows_auto_approve_when_configured():
    review_required, auto_approve = normalize_source_review_policy(
        "culture", review_required=False, auto_approve_low_risk=True,
    )
    assert review_required is False
    assert auto_approve is True


def test_apply_ai_review_to_run_persists_booleans():
    now = datetime.utcnow()
    run = models.KnowledgeIngestionRun(
        source_id=1,
        status="running",
        run_type="manual_upload",
        review_status="pending_review",
        started_at=now,
    )
    review = KnowledgeAIReviewService().review(
        models.KnowledgeSource(
            slug="c",
            name="C",
            category="culture",
            trust_level="official",
            source_url="https://example.org",
            locale="fa",
            ingestion_status="active",
            auto_approve_low_risk=True,
            review_required=False,
            created_at=now,
            updated_at=now,
        ),
        "Culture and sports lifestyle guidance " * 30,
        parser_type="text",
    )
    apply_ai_review_to_run(run, review, findings_json="[]")
    assert run.requires_human_review == review.requires_human_review
    assert run.auto_approve_allowed == review.auto_approve_allowed
    assert run.recommended_action == review.recommended_action


def _admin_headers(monkeypatch) -> dict:
    monkeypatch.setenv("ADMIN_TOKEN", "gate3g-admin")
    return {"X-Admin-Token": "gate3g-admin"}


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def _seed_fetch_source(db, slug: str, **kwargs):
    now = datetime.utcnow()
    defaults = dict(
        slug=slug,
        name=f"Source {slug}",
        category=kwargs.pop("category", "lifestyle"),
        trust_level=kwargs.pop("trust_level", "editorial"),
        source_url=kwargs.pop("source_url", f"https://example.org/{slug}.html"),
        locale="fa",
        last_checked_at=now,
        freshness_policy_days=180,
        ingestion_status="active",
        source_fetch_enabled=True,
        allowed_domain="example.org",
        fetch_method="url_fetch",
        review_required=True,
        auto_approve_low_risk=False,
        max_fetch_bytes=4096,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    src = models.KnowledgeSource(**defaults)
    db.add(src)
    db.flush()
    return src


def test_admin_fetch_endpoint_requires_admin(client, db, monkeypatch):
    src = _seed_fetch_source(db, "fetch-guard")
    db.commit()
    assert client.post(f"/knowledge-base/sources/{src.id}/fetch").status_code in (401, 404)
    token = _token(client, db, monkeypatch, "+989143005001")
    assert client.post(
        f"/knowledge-base/sources/{src.id}/fetch",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code in (401, 404)


def test_source_fetch_disabled_blocks(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_fetch_source(db, "fetch-off", source_fetch_enabled=False)
    db.commit()
    r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 400
    assert "source_fetch_disabled" in r.json()["detail"]


def test_disallowed_domain_blocks_fetch(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_fetch_source(db, "bad-domain", allowed_domain="who.int", source_url="https://example.org/x.html")
    db.commit()
    r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 400
    assert "domain_not_allowed" in r.json()["detail"]


def test_ssrf_private_ip_blocked(db):
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug="ssrf-test",
        name="SSRF",
        category="lifestyle",
        trust_level="editorial",
        source_url="https://evil.example/page",
        locale="fa",
        ingestion_status="active",
        source_fetch_enabled=True,
        allowed_domain="evil.example",
        created_at=now,
        updated_at=now,
    )
    with patch("backend.app.services.gate3.fetch_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
        with pytest.raises(FetchSecurityError, match="private_ip"):
            validate_fetch_url("https://evil.example/page", src)


def test_redirect_to_private_ip_blocked(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_fetch_source(db, "redirect-ssrf")
    db.commit()
    redirect_resp = MagicMock(status_code=302, headers={"Location": "http://127.0.0.1/secret"})
    with patch("backend.app.services.gate3.knowledge_source_fetcher.requests.get", return_value=redirect_resp):
        with patch("backend.app.services.gate3.fetch_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
            with patch("backend.app.services.gate3.robots_checker.requests.get") as robots_get:
                robots_get.return_value = MagicMock(status_code=404)
                r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 400
    assert "private_ip" in r.json()["detail"] or "localhost" in r.json()["detail"]


def test_robots_disallowed_blocks_fetch(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_fetch_source(db, "robots-block", trust_level="editorial", review_required=False)
    db.commit()
    ok_page = MagicMock(status_code=200, content=b"<html><body>" + b"x" * 120 + b"</body></html>", headers={"Content-Type": "text/html"})
    robots_resp = MagicMock(status_code=200, text="User-agent: *\nDisallow: /")
    with patch("backend.app.services.gate3.knowledge_source_fetcher.requests.get", return_value=ok_page):
        with patch("backend.app.services.gate3.robots_checker.requests.get", return_value=robots_resp):
            with patch("backend.app.services.gate3.fetch_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
                r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 400
    assert "robots" in r.json()["detail"]


def test_max_fetch_bytes_enforced(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_fetch_source(db, "max-bytes", max_fetch_bytes=100)
    db.commit()
    big = b"a" * 200
    ok_page = MagicMock(status_code=200, content=big, headers={"Content-Type": "text/plain"}, raise_for_status=lambda: None)
    with patch("backend.app.services.gate3.knowledge_source_fetcher.requests.get", return_value=ok_page):
        with patch("backend.app.services.gate3.robots_checker.requests.get", return_value=MagicMock(status_code=404)):
            with patch("backend.app.services.gate3.fetch_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
                r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 400
    assert "max_fetch_bytes" in r.json()["detail"]


def test_unsupported_pdf_handled_safely():
    parsed = parse_content(b"%PDF-1.4", "application/pdf")
    assert parsed.parser_type == "unsupported_pdf"


def test_content_hash_unchanged_no_new_chunks(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    text = "Lifestyle tip: consistent sleep schedule supports daily wellbeing and energy levels for adults."
    parsed = parse_content(text.encode(), "text/plain")
    src = _seed_fetch_source(db, "no-change", content_hash=parsed.content_hash, category="lifestyle")
    db.commit()
    ok_page = MagicMock(status_code=200, content=text.encode(), headers={"Content-Type": "text/plain"}, raise_for_status=lambda: None)
    with patch("backend.app.services.gate3.knowledge_source_fetcher.requests.get", return_value=ok_page):
        with patch("backend.app.services.gate3.robots_checker.requests.get", return_value=MagicMock(status_code=404)):
            with patch("backend.app.services.gate3.fetch_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
                r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["review_status"] == "no_change"
    assert r.json()["data"]["chunks_created"] == 0


def test_changed_content_pending_review(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = _seed_fetch_source(db, "pending-review", category="medical_condition", trust_level="clinical_guideline")
    db.commit()
    text = "Medical education content about hypertension monitoring and clinician follow-up for adults over forty."
    ok_page = MagicMock(status_code=200, content=text.encode(), headers={"Content-Type": "text/plain"}, raise_for_status=lambda: None)
    with patch("backend.app.services.gate3.knowledge_source_fetcher.requests.get", return_value=ok_page):
        with patch("backend.app.services.gate3.robots_checker.requests.get", return_value=MagicMock(status_code=200, text="User-agent: *\nAllow: /")):
            with patch("backend.app.services.gate3.fetch_security.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
                r = client.post(f"/knowledge-base/sources/{src.id}/fetch", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["review_status"] == "pending_review"
    assert data["recommended_action"] == "pending_review"
    assert data["chunks_created"] == 0


def test_ai_review_high_medical_cannot_auto_approve(db):
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug="med-high",
        name="Med",
        category="medical_condition",
        trust_level="clinical_guideline",
        source_url="https://who.int/x",
        locale="fa",
        ingestion_status="active",
        auto_approve_low_risk=True,
        review_required=False,
        created_at=now,
        updated_at=now,
    )
    review = KnowledgeAIReviewService().review(
        src,
        "Diagnosis and dose guidance for chronic condition management in clinical settings.",
        parser_type="text",
    )
    assert review.medical_risk_level in ("high", "critical")
    assert review.recommended_action != "auto_approve"


def test_low_risk_auto_approve_only_when_configured(db):
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug="auto-low",
        name="Culture",
        category="culture",
        trust_level="official",
        source_url="https://example.org/culture",
        locale="fa",
        ingestion_status="active",
        auto_approve_low_risk=True,
        review_required=False,
        created_at=now,
        updated_at=now,
    )
    long_text = "Culture and sports lifestyle guidance " * 30
    review = KnowledgeAIReviewService().review(src, long_text, parser_type="text")
    assert review.recommended_action == "auto_approve"


def test_approve_creates_active_chunks_reject_does_not(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug="approve-flow",
        name="Approve",
        category="lifestyle",
        trust_level="editorial",
        source_url="https://example.org/a",
        locale="fa",
        last_checked_at=now,
        ingestion_status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(src)
    db.commit()
    content = "Approved lifestyle knowledge chunk about hydration and daily walking for general wellness support."
    ing = client.post(
        "/knowledge-base/ingest",
        headers=h,
        json={"source_id": src.id, "title": "Hydration", "content": content, "category": "lifestyle"},
    )
    run_id = ing.json()["data"]["ingestion_run_id"]
    appr = client.post(f"/knowledge-base/ingestion-runs/{run_id}/approve", headers=h)
    assert appr.status_code == 200
    assert appr.json()["data"]["chunks_created"] >= 1

    token = _token(client, db, monkeypatch, "+989143005002")
    search = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "hydration walking wellness"},
    )
    assert search.json()["data"]["chunks"]

    ing2 = client.post(
        "/knowledge-base/ingest",
        headers=h,
        json={
            "source_id": src.id,
            "title": "Rejected",
            "content": "Rejected pending content unique phrase zzzreject999 should never appear in search results.",
            "category": "lifestyle",
        },
    )
    run2 = ing2.json()["data"]["ingestion_run_id"]
    rej = client.post(
        f"/knowledge-base/ingestion-runs/{run2}/reject",
        headers=h,
        json={"reason": "quality insufficient"},
    )
    assert rej.status_code == 200
    search2 = client.get(
        "/knowledge-base/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": "zzzreject999"},
    )
    assert search2.json()["data"]["chunks"] == []


def test_crisis_kb_content_rejected_on_review(db):
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug="crisis-kb",
        name="Crisis",
        category="mental_wellbeing",
        trust_level="editorial",
        source_url="https://example.org/mw",
        locale="fa",
        ingestion_status="active",
        created_at=now,
        updated_at=now,
    )
    review = KnowledgeAIReviewService().review(
        src,
        "Content mentioning suicide and self-harm is not suitable for automated knowledge activation.",
        parser_type="text",
    )
    assert review.psychological_risk_level == "critical"
    assert review.recommended_action == "reject"


def test_scheduler_disabled_by_default(db, monkeypatch):
    monkeypatch.delenv("SEDI_KB_SCHEDULED_FETCH_ENABLED", raising=False)
    assert scheduled_fetch_enabled() is False
    assert run_scheduled_kb_fetch(db) is None


def test_no_runtime_fetch_during_chat(client, db, monkeypatch):
    """Chat path must not invoke KnowledgeSourceFetcher."""
    token = _token(client, db, monkeypatch, "+989143005003")
    with patch("backend.app.services.gate3.knowledge_source_fetcher.KnowledgeSourceFetcher.fetch") as mocked:
        r = client.post(
            "/interact/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "How can I manage stress?"},
        )
        assert r.status_code in (200, 422, 503)
        mocked.assert_not_called()


def test_create_sensitive_source_normalizes_review_flags(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    r = client.post(
        "/knowledge-base/sources",
        headers=h,
        json={
            "slug": "who-clinical",
            "name": "WHO Clinical",
            "category": "clinical_guideline",
            "trust_level": "clinical_guideline",
            "source_url": "https://who.int/guideline",
            "review_required": False,
            "auto_approve_low_risk": True,
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["review_required"] is True
    assert data["auto_approve_low_risk"] is False


def test_create_low_risk_source_keeps_auto_approve(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    r = client.post(
        "/knowledge-base/sources",
        headers=h,
        json={
            "slug": "culture-curated",
            "name": "Culture Curated",
            "category": "culture",
            "trust_level": "official",
            "source_url": "https://example.org/culture",
            "review_required": False,
            "auto_approve_low_risk": True,
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["review_required"] is False
    assert data["auto_approve_low_risk"] is True


def test_patch_category_to_sensitive_enforces_policy(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    created = client.post(
        "/knowledge-base/sources",
        headers=h,
        json={
            "slug": "lifestyle-temp",
            "name": "Lifestyle Temp",
            "category": "lifestyle",
            "trust_level": "editorial",
            "source_url": "https://example.org/lifestyle",
            "review_required": False,
            "auto_approve_low_risk": True,
        },
    ).json()["data"]
    patched = client.patch(
        f"/knowledge-base/sources/{created['id']}",
        headers=h,
        json={"category": "medication_education"},
    )
    assert patched.status_code == 200
    data = patched.json()["data"]
    assert data["category"] == "medication_education"
    assert data["review_required"] is True
    assert data["auto_approve_low_risk"] is False


def test_ingestion_run_detail_returns_review_booleans(client, db, monkeypatch):
    h = _admin_headers(monkeypatch)
    src = client.post(
        "/knowledge-base/sources",
        headers=h,
        json={
            "slug": "ingest-review-bools",
            "name": "Ingest Review",
            "category": "medical_condition",
            "trust_level": "clinical_guideline",
            "source_url": "https://who.int/hbp",
            "ingestion_status": "active",
        },
    ).json()["data"]
    content = (
        "Hypertension education content for adults: monitor blood pressure regularly and "
        "follow clinician guidance for lifestyle and medication questions."
    )
    ing = client.post(
        "/knowledge-base/ingest",
        headers=h,
        json={"source_id": src["id"], "title": "Hypertension", "content": content, "category": "medical_condition"},
    )
    assert ing.status_code == 200
    run_id = ing.json()["data"]["ingestion_run_id"]
    detail = client.get(f"/knowledge-base/ingestion-runs/{run_id}", headers=h)
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["requires_human_review"] is True
    assert data["auto_approve_allowed"] is False
    assert data["recommended_action"] == "pending_review"
