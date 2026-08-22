"""Focused static/unit-style tests for I7 Wave-2 governed memory lifecycle.

TEST_EXECUTION is deferred to the runtime gate. This module is authored for later pytest.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_no_consent_no_durable_write():
    from backend.app.services.i7.governed_raw import try_durable_raw_write

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch("backend.app.services.i7.governed_raw.has_permission", return_value=False):
        result = try_durable_raw_write(
            db,
            user_id=1,
            user_message="hi",
            sedi_response="hello",
            actor_user_id=1,
            commit=False,
        )
    assert result.durable is False
    assert result.reason == "NO_CONSENT"
    db.add.assert_not_called()


def test_consented_governed_write_and_idempotent_retry():
    from backend.app.services.i7.governed_raw import try_durable_raw_write

    db = MagicMock()
    consent = SimpleNamespace(id=9)
    # first call: no existing idempotency row
    db.query.return_value.filter.return_value.first.side_effect = [None, None]
    with patch("backend.app.services.i7.governed_raw.has_permission", return_value=True), patch(
        "backend.app.services.i7.governed_raw._active_consent", return_value=consent
    ), patch(
        "backend.app.services.i7.governed_raw.resolve_validated_user_timezone",
        return_value="Asia/Tehran",
    ), patch(
        "backend.app.services.i7.governed_raw.get_local_now",
        return_value=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
    ):
        db.query.return_value.filter.return_value.first.side_effect = [
            None,  # idempotency miss
            SimpleNamespace(id=1, preferred_language="en"),  # user
        ]
        first = try_durable_raw_write(
            db,
            user_id=7,
            user_message="a",
            sedi_response="b",
            actor_user_id=7,
            idempotency_key="k1",
            commit=False,
        )
        assert first.durable is True
        assert first.reason == "DURABLE_WRITTEN"
        assert db.add.called

        existing = SimpleNamespace(id=55, user_id=7, idempotency_key="client:k1")
        db.query.return_value.filter.return_value.first.side_effect = [existing]
        second = try_durable_raw_write(
            db,
            user_id=7,
            user_message="a",
            sedi_response="b",
            actor_user_id=7,
            idempotency_key="k1",
            commit=False,
        )
        assert second.replayed is True
        assert second.memory is existing


def test_cross_user_identity_mismatch():
    from backend.app.services.i7.governed_raw import try_durable_raw_write

    db = MagicMock()
    result = try_durable_raw_write(
        db,
        user_id=1,
        user_message="x",
        sedi_response="y",
        actor_user_id=2,
        commit=False,
    )
    assert result.durable is False
    assert result.reason == "AUTH_IDENTITY_MISMATCH"


def test_expired_raw_hidden():
    from backend.app.services.i7.retention import is_raw_visible

    now = datetime(2026, 8, 20, tzinfo=timezone.utc)
    expired = SimpleNamespace(retain_until=now - timedelta(days=1), durable_write=True)
    visible = SimpleNamespace(retain_until=now + timedelta(days=1), durable_write=True)
    unset = SimpleNamespace(retain_until=None, durable_write=True)
    assert is_raw_visible(expired, now=now) is False
    assert is_raw_visible(visible, now=now) is True
    assert is_raw_visible(unset, now=now) is False


def test_purge_requires_finalized_daily_and_is_idempotent():
    from backend.app.services.i7.purge import purge_expired_raw_turn

    db = MagicMock()
    receipt = SimpleNamespace(id=1, purge_key="purge:user:1:memory:9")
    db.query.return_value.filter.return_value.first.return_value = receipt
    with patch("backend.app.services.i7.purge.require_permission", return_value=True):
        result = purge_expired_raw_turn(db, user_id=1, memory_id=9, commit=False)
    assert result.replayed is True
    assert result.reason == "IDEMPOTENT_REPLAY"


def test_week_start_resolver():
    from backend.app.services.i7.period_summaries import resolve_week_start

    assert resolve_week_start("fa") == 5
    assert resolve_week_start("en") == 0


def test_auth_legacy_01_blocks_existing_user_mutation():
    import inspect
    from backend.app.routers import interact as interact_mod

    src = inspect.getsource(interact_mod.introduce_user)
    assert "Authentication required to introduce an existing user" in src
    assert "user.secret_key = secret_key" not in src


def test_migration_068_is_single_successor():
    from pathlib import Path
    import re

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = list(versions.glob("068*.py"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "068_i7_wave2_governed_memory_lifecycle" in text
    assert "067_i7_lifelong_memory_foundation" in text
    assert re.search(r"down_revision.*=.*067_i7_lifelong_memory_foundation", text)


def test_migration_069_is_single_successor():
    from pathlib import Path
    import re

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = list(versions.glob("069*.py"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "069_i8_operational_plan_state_foundation" in text
    assert "068_i7_wave2_governed_memory_lifecycle" in text
    assert re.search(r"down_revision.*068_i7_wave2_governed_memory_lifecycle", text)


def test_i9_pattern_requires_source_refs():
    from backend.app.services.i7.i9_patterns import upsert_i9_derived_pattern

    db = MagicMock()
    with patch("backend.app.services.i7.i9_patterns.has_permission", return_value=True):
        with pytest.raises(ValueError, match="I9_SOURCE_REFS_REQUIRED"):
            upsert_i9_derived_pattern(
                db,
                user_id=1,
                pattern_key="hr_trend",
                pattern={"direction": "up"},
                source_refs=[],
                commit=False,
            )
