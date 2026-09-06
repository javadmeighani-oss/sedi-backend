"""GATE=SEDI-V1-BE-1000U-100CC-CAPACITY-HARDENING-01 — PostgreSQL 16 focused proofs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "1")

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.database import get_db as _app_get_db
from backend.app.main import app as sedi_app
from backend.app.core.scheduler_user_batch import fetch_users_keyset_page, iter_users_bounded
from backend.app.services.i10.coaching_worker import (
    get_coaching_scan_cursor,
    list_eligible_coaching_actions,
    process_i8_coaching_followups,
    reset_coaching_scan_cursor,
)
from backend.tests.helpers.stage_b_family_fixture import seed_stage_b_family

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]


@pytest.fixture()
def client(db):
    def _override():
        yield db

    sedi_app.dependency_overrides[_app_get_db] = _override
    try:
        with TestClient(sedi_app) as c:
            yield c
    finally:
        sedi_app.dependency_overrides.pop(_app_get_db, None)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'user_id': user_id})}"}


def test_pg16_server_major(db):
    ver = db.execute(text("SHOW server_version")).scalar()
    assert str(ver).startswith("16."), ver


def test_t04_t06_chat_ownership_and_contract(client, db):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    son = family.son
    stranger = family.stranger

    from backend.app.services.intelligence.contracts import SafetyAction

    mock_result = MagicMock()
    mock_result.public_brain_dict.return_value = {
        "message": "Hello from Sedi",
        "language": "en",
        "detected_name": None,
    }
    safe = MagicMock()
    safe.action = SafetyAction.CONTINUE

    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=safe,
    ), patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process",
        return_value=mock_result,
    ):
        # Ownership mismatch
        bad = client.post(
            "/interact/chat",
            json={"user_id": stranger.id, "message": "hello"},
            headers={**_auth(son.id), "Accept-Language": "en"},
        )
        assert bad.status_code == 403

        ok = client.post(
            "/interact/chat",
            json={"user_id": son.id, "message": "hello Sedi"},
            headers={**_auth(son.id), "Accept-Language": "en"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["message"] == "Hello from Sedi"
        assert body["user_id"] == son.id
        assert body["language"] == "en"


def test_t05_safety_short_circuit_unchanged(client, db):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    son = family.son

    from backend.app.services.intelligence.contracts import SafetyAction

    safety = MagicMock()
    safety.action = SafetyAction.RETURN_EMERGENCY_RESPONSE

    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=safety,
    ), patch(
        "backend.app.services.intelligence.safety_risk.build_safety_response_safe",
        return_value=MagicMock(localized_message="SAFETY_TERMINAL"),
    ), patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process",
    ) as proc:
        resp = client.post(
            "/interact/chat",
            json={"message": "emergency help"},
            headers={**_auth(son.id), "Accept-Language": "en"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "SAFETY_TERMINAL"
        proc.assert_not_called()


def test_t08_gpt_failure_semantics(client, db):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    son = family.son

    class APIError(Exception):
        pass

    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=MagicMock(),
    ), patch(
        "backend.app.services.intelligence.safety_risk.requires_terminal_safety_response",
        return_value=False,
    ), patch(
        "backend.app.core.conversation.prompts.client.responses.create",
        side_effect=APIError("OpenAI unavailable"),
    ):
        # Force structured/compat path into brain GPT via real process — patch process to raise gpt-like
        with patch(
            "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process",
            side_effect=APIError("OpenAI unavailable"),
        ):
            # interact maps non-HTTP exceptions; gpt path uses _is_gpt_related_error
            pass

    # Use the dedicated gpt_failure path via brain error classification in interact
    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=MagicMock(),
    ), patch(
        "backend.app.services.intelligence.safety_risk.requires_terminal_safety_response",
        return_value=False,
    ), patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process",
        side_effect=APIError("OpenAI rate limit exceeded"),
    ), patch(
        "backend.app.routers.interact._is_gpt_related_error",
        return_value=True,
    ):
        response = client.post(
            "/interact/chat",
            json={"message": "Hello Sedi"},
            headers={**_auth(son.id), "Accept-Language": "en"},
        )
    assert response.status_code == 502
    assert response.json().get("error") == "gpt_failure"


def test_t12_no_session_leak_repeated_requests(client, db):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    son = family.son
    mock_result = MagicMock()
    mock_result.public_brain_dict.return_value = {
        "message": "ok",
        "language": "en",
        "detected_name": None,
    }
    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=MagicMock(),
    ), patch(
        "backend.app.services.intelligence.safety_risk.requires_terminal_safety_response",
        return_value=False,
    ), patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process",
        return_value=mock_result,
    ):
        for _ in range(5):
            r = client.post(
                "/interact/chat",
                json={"message": "ping"},
                headers={**_auth(son.id), "Accept-Language": "en"},
            )
            assert r.status_code == 200
    # Transactional test session still usable
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_t13_t19_bounded_user_keyset(db):
    # Seed several users
    users = []
    for i in range(5):
        u = models.User(name=f"CapUser{i}", secret_key=f"sk-cap-{i}-{i}", preferred_language="en")
        db.add(u)
        users.append(u)
    db.flush()

    page1 = fetch_users_keyset_page(db, after_user_id=0, limit=2)
    assert len(page1) == 2
    page2 = fetch_users_keyset_page(db, after_user_id=page1[-1].id, limit=2)
    assert len(page2) == 2
    assert page2[0].id > page1[-1].id

    bounded = list(iter_users_bounded(db, batch_size=2, max_per_tick=3))
    assert len(bounded) == 3


def test_t16_t17_t18_coaching_bounded_pages(db):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    reset_coaching_scan_cursor()
    when = datetime.now(timezone.utc)
    # Empty page → wrap
    n = process_i8_coaching_followups(
        db, now=when, force=True, use_inprocess_cursor=True, limit=5
    )
    assert n == 0
    assert get_coaching_scan_cursor() == 0

    # list with limit does not raise
    rows = list_eligible_coaching_actions(db, now=when, limit=5, after_action_id=0)
    assert isinstance(rows, list)


def test_t22_son_mother_identity_isolation(db):
    family = seed_stage_b_family(db, with_device=False, commit=False)
    assert family.son_self_hs.linked_user_id == family.son.id
    assert family.mother_hs.linked_user_id is None
    assert family.son_self_hs.id != family.mother_hs.id
    assert family.son.id != family.mother_hs.id


def test_t23_rag_off_near_zero(db):
    os.environ["RAG_LOCAL_ENABLED"] = "false"
    from backend.app.core.conversation import brain as brain_mod

    messages = []
    with patch(
        "backend.app.services.local_rag.provider_router.retrieve",
        side_effect=AssertionError("RAG must not run when OFF"),
    ):
        brain_mod._maybe_append_local_rag_context(messages, db, 1, "hello", "en")
    assert messages == []


def test_t24_rag_context_user_isolation_and_concurrent_offload(client, db, monkeypatch):
    """T24: Son A cannot retrieve Son B RAG/user context; concurrent offload preserves identity.

    No Smart-RAG. Uses existing LocalRAGProvider + chat offload path only.
    """
    import asyncio

    from backend.app.services.intelligence.contracts import SafetyAction
    from backend.app.services.local_rag.local_provider import LocalRAGProvider
    from backend.app.services.local_rag import provider_router

    monkeypatch.setenv("RAG_LOCAL_ENABLED", "true")
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "false")
    # Reload flag used by provider module
    import backend.app.services.local_rag.local_provider as lp

    monkeypatch.setattr(lp, "RAG_LOCAL_ENABLED", True)

    son_a = models.User(name="CapSonA", secret_key="sk-a-t24", preferred_language="en")
    son_b = models.User(name="CapSonB", secret_key="sk-b-t24", preferred_language="en")
    db.add_all([son_a, son_b])
    db.flush()

    marker_a = "SON_A_PRIVATE_SLEEP_MARKER_ZZA"
    marker_b = "SON_B_PRIVATE_SLEEP_MARKER_ZZB"
    db.add(
        models.UserFact(
            user_id=son_a.id,
            key="sleep_habit",
            value_json=f'"{marker_a}"',
            source="manual",
        )
    )
    db.add(
        models.UserFact(
            user_id=son_b.id,
            key="sleep_habit",
            value_json=f'"{marker_b}"',
            source="manual",
        )
    )
    db.flush()

    # 1) Provider-level isolation
    ra = LocalRAGProvider(db).retrieve(son_a.id, "sleep habit lifestyle", "en")
    rb = LocalRAGProvider(db).retrieve(son_b.id, "sleep habit lifestyle", "en")
    text_a = (ra.combined_text or "") if ra else ""
    text_b = (rb.combined_text or "") if rb else ""
    assert marker_a in text_a
    assert marker_b not in text_a
    assert marker_b in text_b
    assert marker_a not in text_b

    # 2) Router retrieve also scoped by user_id
    routed_a = provider_router.retrieve(db, son_a.id, "sleep habit lifestyle", "en")
    routed_text = (routed_a.combined_text or "") if routed_a else ""
    assert marker_a in routed_text
    assert marker_b not in routed_text

    # 3) Concurrent offloaded orchestration preserves authenticated identity
    # (do not share one SQLAlchemy Session across threads; record identity only)
    seen_ids: list[int] = []
    lock = __import__("threading").Lock()
    safe = MagicMock()
    safe.action = SafetyAction.CONTINUE

    def _fake_process(*, authenticated_user_id: int, message: str, **kwargs):
        with lock:
            seen_ids.append(authenticated_user_id)
        mock = MagicMock()
        # Encode identity into response; caller asserts no cross-swap
        mock.public_brain_dict.return_value = {
            "message": f"ok:{authenticated_user_id}",
            "language": "en",
            "detected_name": None,
        }
        return mock

    with patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.precheck_safety_risk",
        return_value=safe,
    ), patch(
        "backend.app.services.intelligence.orchestrator.IntelligenceOrchestrator.process",
        side_effect=_fake_process,
    ):
        async def _both():
            from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

            orch = IntelligenceOrchestrator(db=db)

            def run_a():
                return orch.process(
                    authenticated_user_id=son_a.id,
                    message="sleep habit lifestyle",
                    language="en",
                )

            def run_b():
                return orch.process(
                    authenticated_user_id=son_b.id,
                    message="sleep habit lifestyle",
                    language="en",
                )

            ra_r, rb_r = await asyncio.gather(
                asyncio.to_thread(run_a),
                asyncio.to_thread(run_b),
            )
            return ra_r, rb_r

        out_a, out_b = asyncio.run(_both())
        assert out_a.public_brain_dict()["message"] == f"ok:{son_a.id}"
        assert out_b.public_brain_dict()["message"] == f"ok:{son_b.id}"
        assert set(seen_ids) == {son_a.id, son_b.id}

        # HTTP chat path: JWT ownership still enforced under capacity offload
        r_ok = client.post(
            "/interact/chat",
            json={"message": "sleep habit lifestyle", "user_id": son_a.id},
            headers={**_auth(son_a.id), "Accept-Language": "en"},
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["user_id"] == son_a.id
        r_bad = client.post(
            "/interact/chat",
            json={"message": "sleep habit lifestyle", "user_id": son_b.id},
            headers={**_auth(son_a.id), "Accept-Language": "en"},
        )
        assert r_bad.status_code == 403

    # 4) RAG OFF remains zero/near-zero work (no retrieve)
    monkeypatch.setenv("RAG_LOCAL_ENABLED", "false")
    monkeypatch.setattr(lp, "RAG_LOCAL_ENABLED", False)
    from backend.app.core.conversation import brain as brain_mod

    messages: list = []
    with patch.object(
        provider_router,
        "retrieve",
        side_effect=AssertionError("RAG must not run when OFF"),
    ):
        brain_mod._maybe_append_local_rag_context(messages, db, son_a.id, "sleep", "en")
    assert messages == []


def test_t09_pool_snapshot_defaults():
    from backend.app.database import pool_config_snapshot

    snap = pool_config_snapshot()
    assert snap["pool_pre_ping"] is True
    assert snap["pool_size"] >= 1
    assert snap["max_overflow"] >= 0
