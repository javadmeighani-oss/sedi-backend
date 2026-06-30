"""Gate 2 — lifestyle events, care plan items, memory context, promotion, RAG."""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services import auth_otp_service as svc
from backend.app.services.knowledge.service import create_candidate, accept_candidate
from backend.app.services.candidate_promotion_service import promote_kc_candidate
from backend.app.services.rag_context.rag_context_builder import build_rag_context_pack


def _token(client, db, monkeypatch, phone: str) -> str:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    return client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"}).json()["data"]["access_token"]


def test_lifestyle_events_and_care_plan(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004001")
    headers = {"Authorization": f"Bearer {token}"}
    le = client.post(
        "/user/lifestyle-events",
        json={"event_type": "walk", "value": {"minutes": 30}, "occurred_at": datetime.utcnow().isoformat()},
        headers=headers,
    )
    assert le.status_code == 200
    cp = client.post("/user/care-plan-items", json={"title": "Daily stretching", "category": "mobility"}, headers=headers)
    assert cp.status_code == 200
    cid = cp.json()["data"]["id"]
    assert client.delete(f"/user/care-plan-items/{cid}", headers=headers).status_code == 200


def test_memory_context_aggregation(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004002")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/user/habits", json={"name": "hydration"}, headers=headers)
    client.post("/user/goals", json={"title": "sleep better", "category": "health"}, headers=headers)
    ctx = client.get("/user/memory-context", headers=headers)
    assert ctx.status_code == 200
    data = ctx.json()["data"]
    assert "habits" in data and "goals" in data
    assert data["user_id"] is not None


def test_candidate_promotion_lifestyle_scalar(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004003")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers)
    user_id = me.json()["data"]["user_id"]
    cand = create_candidate(
        db=db,
        user_id=user_id,
        source="chat_extraction_v1",
        fact_type="sleep_quality",
        value_json=json.dumps("poor"),
        confidence=0.9,
    )
    accept_candidate(db, cand.id, verified_by="system")
    db.refresh(cand)
    result = promote_kc_candidate(db, cand)
    assert result["target"] == "user_memory_facts"


def test_rag_includes_gate2_canonical_only(client, db, monkeypatch):
    token = _token(client, db, monkeypatch, "+989143004004")
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/auth/me", headers=headers)
    user_id = me.json()["data"]["user_id"]
    client.post("/user/goals", json={"title": "RAG goal", "category": "health"}, headers=headers)
    pack = build_rag_context_pack(db, user_id)
    assert "goals_structured" in (pack.stable_facts or {}) or pack.goals
