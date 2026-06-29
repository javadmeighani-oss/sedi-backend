"""Gate 1 — RAG context includes profile facts, not caregiver internals."""

import os
from unittest.mock import patch

os.environ["SMS_DISABLED"] = "true"

from backend.app.services.rag_context.rag_context_builder import build_rag_context_pack
from backend.app.services.user_profile_fact_service import create_profile_fact
from backend.app.schemas.gate1 import ProfileFactCreateIn
from backend.app.services import auth_otp_service as svc
from backend.app.services.user_caregiver_service import create_caregiver
from backend.app.schemas.gate1 import CaregiverCreateIn


def _user_id(client, db, monkeypatch, phone: str) -> int:
    monkeypatch.setenv("OTP_SECRET", f"test_otp_{phone[-4:]}")
    with patch.object(svc, "generate_otp_code", return_value="123456"):
        svc.request_otp(db, phone)
    r = client.post("/auth/verify_otp", json={"phone": phone, "code": "123456"})
    return r.json()["data"]["user_id"]


def test_rag_includes_profile_facts_not_caregiver_phones(client, db, monkeypatch):
    uid = _user_id(client, db, monkeypatch, "+989146006001")
    create_profile_fact(
        db,
        uid,
        ProfileFactCreateIn(fact_type="allergy", value="latex", source="manual"),
    )
    create_caregiver(
        db,
        uid,
        CaregiverCreateIn(name="Secret Contact", phone="+989199999999", relationship="nurse"),
    )

    pack = build_rag_context_pack(db, uid)
    facts = (pack.stable_facts or {}).get("identity_facts") or []
    assert any("latex" in str(f) for f in facts)
    serialized = " ".join(str(pack.stable_facts))
    assert "+989199999999" not in serialized
    assert "Secret Contact" not in serialized or "nurse" not in serialized.lower()
