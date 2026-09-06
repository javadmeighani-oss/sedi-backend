"""Capacity hardening focused tests — GATE SEDI-V1-BE-1000U-100CC-CAPACITY-HARDENING-01."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SEDI_DISABLE_SCHEDULER", "1")


# ---------------------------------------------------------------------------
# T01–T03 process role / scheduler
# ---------------------------------------------------------------------------


def test_t01_api_role_scheduler_off(monkeypatch):
    monkeypatch.setenv("SEDI_PROCESS_ROLE", "api")
    monkeypatch.delenv("SEDI_DISABLE_SCHEDULER", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    from backend.app.core.process_role import should_start_scheduler

    assert should_start_scheduler() is False


def test_t01b_disable_scheduler_env(monkeypatch):
    monkeypatch.setenv("SEDI_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("SEDI_PROCESS_ROLE", "combined")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    from backend.app.core.process_role import should_start_scheduler

    assert should_start_scheduler() is False


def test_t02_scheduler_role_enabled(monkeypatch):
    monkeypatch.setenv("SEDI_PROCESS_ROLE", "scheduler")
    monkeypatch.delenv("SEDI_DISABLE_SCHEDULER", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    from backend.app.core.process_role import should_start_scheduler

    assert should_start_scheduler() is True


def test_t03_multi_worker_config_does_not_imply_scheduler(monkeypatch):
    monkeypatch.setenv("SEDI_PROCESS_ROLE", "api")
    monkeypatch.setenv("UVICORN_WORKERS", "4")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    from backend.app.core.process_role import should_start_scheduler, uvicorn_workers_configured

    assert uvicorn_workers_configured() == 4
    assert should_start_scheduler() is False


def test_main_should_start_scheduler_uses_process_role():
    import backend.app.main as main_mod

    src = inspect.getsource(main_mod._should_start_scheduler)
    assert "should_start_scheduler" in src


# ---------------------------------------------------------------------------
# T09–T11 DB pool / budget
# ---------------------------------------------------------------------------


def test_t09_db_pool_env_parses(monkeypatch):
    monkeypatch.setenv("SEDI_DB_POOL_SIZE", "8")
    monkeypatch.setenv("SEDI_DB_MAX_OVERFLOW", "12")
    from backend.app.core.capacity_budget import resolve_max_overflow, resolve_pool_size

    size, src = resolve_pool_size()
    overflow, osrc = resolve_max_overflow()
    assert size == 8 and src == "env"
    assert overflow == 12 and osrc == "env"


def test_t10_invalid_pool_falls_back(monkeypatch):
    monkeypatch.setenv("SEDI_DB_POOL_SIZE", "not-a-number")
    monkeypatch.setenv("SEDI_DB_MAX_OVERFLOW", "9999")
    from backend.app.core.capacity_budget import resolve_max_overflow, resolve_pool_size

    size, src = resolve_pool_size()
    overflow, osrc = resolve_max_overflow()
    assert size == 5 and src == "invalid_fallback"
    assert overflow == 10 and osrc == "range_fallback"


def test_t11_connection_budget_formula():
    from backend.app.core.capacity_budget import (
        CONNECTION_BUDGET_FORMULA,
        compute_connection_budget,
    )

    b = compute_connection_budget(
        api_workers=4,
        pool_size=5,
        max_overflow=10,
        background_process_db_capacity=15,
        reserved_operational_margin=5,
    )
    assert b.total_potential_app_connections == 4 * 15 + 15 + 5
    assert "API_WORKERS" in CONNECTION_BUDGET_FORMULA


# ---------------------------------------------------------------------------
# T07 chat offload / T25 observability sanitization
# ---------------------------------------------------------------------------


def test_t07_interact_chat_uses_asyncio_to_thread():
    import backend.app.routers.interact as interact_mod

    src = inspect.getsource(interact_mod.chat)
    assert "asyncio.to_thread" in src
    assert "orchestrator.process" in src


def test_t07_to_thread_keeps_event_loop_responsive():
    """Prove offload pattern: slow sync work does not freeze awaiting gather peer."""

    async def _run():
        def slow():
            import time

            time.sleep(0.15)
            return "done"

        async def tick():
            await asyncio.sleep(0.01)
            return "tick"

        loop = asyncio.get_running_loop()
        t0 = loop.time()
        results = await asyncio.gather(asyncio.to_thread(slow), tick())
        elapsed = loop.time() - t0
        assert results == ["done", "tick"]
        assert elapsed < 0.35

    asyncio.run(_run())


def test_t25_observability_strips_sensitive_keys(caplog):
    import logging

    from backend.app.core.capacity_observability import log_event

    with caplog.at_level(logging.INFO, logger="sedi.capacity"):
        log_event(
            "probe",
            route="/interact/chat",
            message="SECRET_CHAT_BODY",
            phone="+98912",
            token="abc",
            duration_ms=12,
        )
    text = " ".join(r.message for r in caplog.records)
    assert "SECRET_CHAT_BODY" not in text
    assert "+98912" not in text
    assert "token=abc" not in text
    assert "duration_ms=12" in text
    assert "event=probe" in text


# ---------------------------------------------------------------------------
# T13–T19 bounded scans (unit)
# ---------------------------------------------------------------------------


def test_t13_morning_uses_bounded_iter():
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.run_morning_notifications)
    assert "iter_users_bounded" in src
    assert "User).all()" not in src.replace(" ", "")


def test_t14_inactivity_uses_bounded_iter():
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.run_inactivity_notifications)
    assert "iter_users_bounded" in src


def test_t15_engagement_uses_bounded_iter():
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.run_engagement_nudge)
    assert "iter_users_bounded" in src


def test_fetch_users_keyset_page_and_cap(db_session_factory=None):
    """Static contract for keyset helper."""
    from backend.app.core.scheduler_user_batch import (
        fetch_users_keyset_page,
        user_scan_batch_size,
        user_scan_max_per_tick,
    )

    assert user_scan_batch_size() >= 1
    assert user_scan_max_per_tick() >= 1
    assert callable(fetch_users_keyset_page)


def test_t16_coaching_list_accepts_limit():
    sig = inspect.signature(
        __import__(
            "backend.app.services.i10.coaching_worker",
            fromlist=["list_eligible_coaching_actions"],
        ).list_eligible_coaching_actions
    )
    assert "limit" in sig.parameters
    assert "after_action_id" in sig.parameters


def test_t17_t18_coaching_cursor_progression():
    from backend.app.services.i10 import coaching_worker as cw

    cw.reset_coaching_scan_cursor()
    assert cw.get_coaching_scan_cursor() == 0
    cw._advance_coaching_cursor(page_last_id=42, page_len=2, limit=2)
    assert cw.get_coaching_scan_cursor() == 42
    cw._advance_coaching_cursor(page_last_id=None, page_len=0, limit=2)
    assert cw.get_coaching_scan_cursor() == 0  # wrap


def test_t19_isolated_failure_helper():
    from backend.app.core.scheduler_user_batch import run_per_user_isolated

    class U:
        def __init__(self, i):
            self.id = i

    users = [U(1), U(2), U(3)]

    def handler(u):
        if u.id == 2:
            raise RuntimeError("boom")
        return None

    stats = run_per_user_isolated(users, handler, job_id="test")
    assert stats["ok"] == 2
    assert stats["failed"] == 1
    assert stats["scanned"] == 3
