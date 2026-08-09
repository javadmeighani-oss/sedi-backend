"""Regression proofs for Iran directory production apply session lifecycle."""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import MagicMock

from sqlalchemy.orm import Session


def test_sessionlocal_is_generator_style_not_session():
    """Pinned contract: SessionLocal() yields a generator, not a Session.

    Calling SessionLocal() and treating the result as a Session reproduced the
    production AttributeError: 'generator' object has no attribute 'query'.
    """
    from backend.app.database import SessionFactory, SessionLocal

    gen = SessionLocal()
    assert inspect.isgenerator(gen)
    assert not isinstance(gen, Session)
    assert not hasattr(gen, "query")
    session = SessionFactory()
    try:
        assert isinstance(session, Session)
        assert hasattr(session, "query")
    finally:
        session.close()
    try:
        db = next(gen)
        db.close()
    except StopIteration:
        pass


def test_open_script_session_returns_session_with_query(monkeypatch):
    from backend.scripts import iran_directory_prod_apply as apply_mod
    import backend.app.database as dbmod

    fake_session = MagicMock(spec=["query", "commit", "rollback", "close"])
    monkeypatch.setattr(dbmod, "SessionFactory", lambda: fake_session)

    with apply_mod.open_script_session(commit=False) as db:
        assert db is fake_session
        db.query("IranDoctor")
    fake_session.close.assert_called_once()
    fake_session.commit.assert_not_called()

    with apply_mod.open_script_session(commit=True) as db:
        assert db is fake_session
    assert fake_session.commit.call_count == 1


def test_prod_apply_dry_run_uses_session_not_generator(monkeypatch, tmp_path):
    """CLI dry-run must not hit AttributeError: generator has no attribute query."""
    from backend.scripts import iran_directory_prod_apply as apply_mod

    payload = tmp_path / "payload.json"
    payload.write_text(
        '[{"entity_family":"DOCTOR","profile_id":"11111111-2222-3333-4444-555555555555",'
        '"full_name":"دکتر نمونه","specialty":"داخلی","city":"تهران"}]',
        encoding="utf-8",
    )

    fake_db = MagicMock(spec=["query", "commit", "rollback", "close"])
    plans = {"doctor": {"insert": 1, "update": 0, "unchanged": 0, "reject": 0}}

    @contextmanager
    def _fake_open(*, commit: bool = False) -> Iterator[Any]:
        yield fake_db

    monkeypatch.setattr(apply_mod, "open_script_session", _fake_open)
    monkeypatch.setattr(
        "backend.app.services.i5.iran_directory_import.dry_run_plan",
        lambda records, db: plans,
    )

    rc = apply_mod.main(["dry-run", "--payload", str(payload)])
    assert rc == 0
