"""A4 P2A.1 — concurrent same-action idempotency via Notification FOR UPDATE."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import InteractionEvent, Notification, NotificationFeedback, User
from backend.app.routers.notifications import submit_notification_feedback
from backend.tests.test_db_config import get_test_database_url

_WORKERS = 8


def _require_postgres_engine(engine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for FOR UPDATE concurrency proof")


def _session_factory():
    engine = create_engine(get_test_database_url(), pool_pre_ping=True, future=True)
    _require_postgres_engine(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True), engine


def _seed_user_and_notif(SessionLocal, label: str):
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:10]
        u = User(
            name=f"p2a1-{label}-{suffix}",
            secret_key=f"sk-p2a1-{label}-{suffix}",
            preferred_language="en",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        now = datetime.utcnow()
        n = Notification(
            user_id=u.id,
            type="connection_ping",
            title="T",
            body="B",
            priority="normal",
            is_read=False,
            is_sent=True,
            sent_at=now,
            status="sent",
            provider="fcm",
            created_at=now,
            channel="engagement",
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        return int(u.id), int(n.id)
    finally:
        db.close()


def _cleanup(SessionLocal, user_id: int, notif_id: int) -> None:
    db = SessionLocal()
    try:
        db.query(InteractionEvent).filter(
            InteractionEvent.source_notification_id == notif_id
        ).delete(synchronize_session=False)
        db.query(NotificationFeedback).filter(
            NotificationFeedback.notification_id == notif_id
        ).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.id == notif_id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _run_concurrent_feedback(
    SessionLocal,
    *,
    user_id: int,
    notif_id: int,
    payload: dict,
    workers: int = _WORKERS,
) -> List[BaseException]:
    barrier = threading.Barrier(workers)
    errors: List[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        s = SessionLocal()
        try:
            user = s.query(User).filter(User.id == user_id).one()
            barrier.wait(timeout=30)
            submit_notification_feedback(
                notification_id=notif_id,
                payload=payload,
                auth_user=user,
                user_id=None,
                db=s,
            )
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            with lock:
                errors.append(exc)
            try:
                s.rollback()
            except Exception:
                pass
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(worker) for _ in range(workers)]
        for f in as_completed(futs):
            f.result()
    return errors


def _assert_single_action_read(
    SessionLocal,
    *,
    notif_id: int,
    action: str,
    event_type: str,
) -> None:
    db = SessionLocal()
    try:
        n = db.query(Notification).filter(Notification.id == notif_id).one()
        assert n.is_read is True
        assert (
            db.query(NotificationFeedback)
            .filter(
                NotificationFeedback.notification_id == notif_id,
                NotificationFeedback.action == action,
            )
            .count()
            == 1
        )
        assert (
            db.query(InteractionEvent)
            .filter(
                InteractionEvent.source_notification_id == notif_id,
                InteractionEvent.event_type == event_type,
            )
            .count()
            == 1
        )
        assert (
            db.query(InteractionEvent)
            .filter(
                InteractionEvent.source_notification_id == notif_id,
                InteractionEvent.event_type == "notification_read",
            )
            .count()
            == 1
        )
    finally:
        db.close()


@pytest.mark.parametrize(
    "label,payload,action,event_type",
    [
        ("like", {"action": "like"}, "like", "notification_like"),
        ("dislike", {"action": "dislike"}, "dislike", "notification_dislike"),
        (
            "dislike_reason",
            {"action": "dislike", "reason": "irrelevant"},
            "dislike",
            "notification_dislike_reason",
        ),
        ("talk", {"action": "open_chat"}, "open_chat", "notification_open_chat"),
    ],
)
def test_concurrent_identical_action_dedupes(label, payload, action, event_type):
    SessionLocal, engine = _session_factory()
    user_id, notif_id = _seed_user_and_notif(SessionLocal, label)
    try:
        errors = _run_concurrent_feedback(
            SessionLocal,
            user_id=user_id,
            notif_id=notif_id,
            payload=payload,
        )
        assert not errors, errors
        _assert_single_action_read(
            SessionLocal,
            notif_id=notif_id,
            action=action,
            event_type=event_type,
        )
    finally:
        _cleanup(SessionLocal, user_id, notif_id)
        engine.dispose()


def test_lock_helper_uses_for_update():
    from backend.app.services.i10 import interaction_recorder as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert "with_for_update" in src
    assert "lock_notification_for_interaction_mutation" in src
