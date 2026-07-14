"""Section 15-B8 — notification chat_message idempotency (service + migration)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sqlalchemy.schema import CreateIndex
from sqlalchemy.dialects import postgresql as pg_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect

from backend.app.models import InteractionEvent, Notification, User
from backend.app.services.gate4.interaction_event_service import (
    UQ_NOTIF_CHAT_ONCE,
    create_chat_message_event,
    create_interaction_event,
    find_existing_notification_chat_message_event,
)


def _pg_only(db) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _require_postgres(db):
    if not _pg_only(db):
        pytest.skip(
            "Partial unique index + concurrency IntegrityError require PostgreSQL "
            "(CI/test DB). Service-layer sequential coverage still runs on all dialects."
        )


@pytest.fixture
def user(db):
    u = User(name="B8 User", secret_key="b8", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def other_user(db):
    u = User(name="B8 Other", secret_key="b8o", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def notif(db, user):
    n = Notification(
        user_id=user.id,
        type="companion",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture
def notif_b(db, user):
    n = Notification(
        user_id=user.id,
        type="companion",
        title="T2",
        body="B2",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_first_notification_chat_message_creates_one_row(db, user, notif):
    row = create_chat_message_event(
        db,
        user_id=user.id,
        source_notification_id=notif.id,
        conversation_id=None,
    )
    db.commit()
    assert row.id is not None
    assert row.event_type == "chat_message"
    assert row.source_notification_id == notif.id
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.source_notification_id == notif.id,
            InteractionEvent.event_type == "chat_message",
        )
        .count()
        == 1
    )


def test_sequential_duplicate_produces_one_row(db, user, notif):
    a = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id=None
    )
    b = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id="c-later"
    )
    db.commit()
    assert a.id == b.id
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.source_notification_id == notif.id,
            InteractionEvent.event_type == "chat_message",
        )
        .count()
        == 1
    )


def test_null_then_non_null_conversation_still_one_event(db, user, notif):
    first = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id=None
    )
    second = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id="opened"
    )
    db.commit()
    assert first.id == second.id
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.source_notification_id == notif.id,
            InteractionEvent.event_type == "chat_message",
        )
        .count()
        == 1
    )


def test_different_conversation_ids_remain_one_event(db, user, notif):
    a = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id="c1"
    )
    b = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id="c2"
    )
    db.commit()
    assert a.id == b.id


def test_different_source_notifications_allowed(db, user, notif, notif_b):
    a = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id
    )
    b = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif_b.id
    )
    db.commit()
    assert a.id != b.id


def test_users_are_isolated(db, user, other_user, notif):
    # other_user cannot own notif; create dedicated notification for other
    n_other = Notification(
        user_id=other_user.id,
        type="companion",
        title="O",
        body="O",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    db.add(n_other)
    db.commit()
    db.refresh(n_other)

    a = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id
    )
    b = create_chat_message_event(
        db, user_id=other_user.id, source_notification_id=n_other.id
    )
    db.commit()
    assert a.id != b.id
    assert a.user_id != b.user_id


def test_turns_without_source_notification_are_not_blocked(db, user):
    a = create_chat_message_event(db, user_id=user.id, source_notification_id=None)
    b = create_chat_message_event(db, user_id=user.id, source_notification_id=None)
    db.commit()
    assert a.id != b.id
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.event_type == "chat_message",
            InteractionEvent.source_notification_id.is_(None),
        )
        .count()
        == 2
    )


def test_model_partial_unique_index_has_sqlite_and_postgresql_where():
    """create_all on SQLite must not compile an unconditional unique index."""
    idx = next(
        i for i in InteractionEvent.__table__.indexes if i.name == UQ_NOTIF_CHAT_ONCE
    )
    predicate = "event_type = 'chat_message' AND source_notification_id IS NOT NULL"
    sqlite_sql = str(CreateIndex(idx).compile(dialect=sqlite_dialect.dialect()))
    pg_sql = str(CreateIndex(idx).compile(dialect=pg_dialect.dialect()))
    for ddl in (sqlite_sql, pg_sql):
        assert "WHERE" in ddl.upper()
        assert predicate.lower() in ddl.lower().replace("\n", " ")
    assert "UNIQUE INDEX" in sqlite_sql.upper() or "CREATE UNIQUE INDEX" in sqlite_sql.upper()


def test_other_event_types_unaffected(db, user, notif):
    create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id
    )
    create_interaction_event(
        db,
        user_id=user.id,
        event_type="notification_ack",
        source="notification",
        source_notification_id=notif.id,
    )
    create_interaction_event(
        db,
        user_id=user.id,
        event_type="notification_open_chat",
        source="notification",
        source_notification_id=notif.id,
    )
    db.commit()
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.source_notification_id == notif.id,
            InteractionEvent.event_type == "chat_message",
        )
        .count()
        == 1
    )
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.source_notification_id == notif.id,
            InteractionEvent.event_type != "chat_message",
        )
        .count()
        == 2
    )


def test_unrelated_integrity_error_is_not_swallowed(db, user, notif):
    """Foreign-key style failure for bad notification ownership stays raising."""
    with pytest.raises((PermissionError, LookupError)):
        create_chat_message_event(
            db,
            user_id=user.id,
            source_notification_id=notif.id + 999999,
        )


def test_concurrent_duplicates_produce_one_row(db, user, notif):
    _require_postgres(db)

    # Ensure partial unique index exists for this session.
    db.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {UQ_NOTIF_CHAT_ONCE}
            ON interaction_events (user_id, source_notification_id)
            WHERE event_type = 'chat_message'
              AND source_notification_id IS NOT NULL
            """
        )
    )
    db.commit()

    existing = find_existing_notification_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id
    )
    assert existing is None

    first = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id
    )

    # Competing insert bypassing pre-check; nest so outer session stays usable.
    from backend.app.services.gate4.interaction_event_service import (
        create_interaction_event as _cie,
    )

    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _cie(
                db,
                user_id=user.id,
                event_type="chat_message",
                source="notification",
                source_notification_id=notif.id,
            )

    recovered = create_chat_message_event(
        db, user_id=user.id, source_notification_id=notif.id, conversation_id="retry"
    )
    db.commit()
    assert recovered.id == first.id
    assert (
        db.query(InteractionEvent)
        .filter(
            InteractionEvent.user_id == user.id,
            InteractionEvent.source_notification_id == notif.id,
            InteractionEvent.event_type == "chat_message",
        )
        .count()
        == 1
    )


def test_migration_source_defines_index_and_fail_closed_preflight():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "050_gate4_interaction_event_idempotency.py"
    )
    text_src = path.read_text(encoding="utf-8")
    assert 'revision: str = "050_gate4_event_idem"' in text_src
    assert len("050_gate4_event_idem") <= 32
    assert (
        'down_revision: Union[str, None] = "049_section10_kb_embeddings_memory_governance"'
        in text_src
    )
    assert UQ_NOTIF_CHAT_ONCE in text_src
    assert "HAVING COUNT(*) > 1" in text_src
    assert "Refusing to create" in text_src
    assert "No audit rows were deleted" in text_src
    assert f'INDEX_NAME = "{UQ_NOTIF_CHAT_ONCE}"' in text_src
    assert "DROP INDEX IF EXISTS {INDEX_NAME}" in text_src
    assert "conversation_id" in text_src  # documented exclusion
    assert "DELETE FROM interaction_events" not in text_src


def test_migration_upgrade_creates_index_on_postgres(db):
    _require_postgres(db)
    import importlib.util

    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "050_gate4_interaction_event_idempotency.py"
    )
    spec = importlib.util.spec_from_file_location("mig050", mig_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    # Ensure clean state for this index
    db.execute(text(f"DROP INDEX IF EXISTS {UQ_NOTIF_CHAT_ONCE}"))
    db.commit()

    mod._raise_if_duplicates(db.get_bind())
    db.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {UQ_NOTIF_CHAT_ONCE}
            ON interaction_events (user_id, source_notification_id)
            WHERE event_type = 'chat_message'
              AND source_notification_id IS NOT NULL
            """
        )
    )
    db.commit()
    exists = db.execute(
        text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE indexname = :name
            """
        ),
        {"name": UQ_NOTIF_CHAT_ONCE},
    ).fetchone()
    assert exists is not None

    db.execute(text(f"DROP INDEX IF EXISTS {UQ_NOTIF_CHAT_ONCE}"))
    db.commit()
    gone = db.execute(
        text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE indexname = :name
            """
        ),
        {"name": UQ_NOTIF_CHAT_ONCE},
    ).fetchone()
    assert gone is None


def test_migration_preflight_fails_closed_on_duplicates(db, user, notif):
    _require_postgres(db)
    # Insert two conflicting rows by temporarily dropping the unique index if present.
    db.execute(text(f"DROP INDEX IF EXISTS {UQ_NOTIF_CHAT_ONCE}"))
    db.commit()
    create_interaction_event(
        db,
        user_id=user.id,
        event_type="chat_message",
        source="notification",
        source_notification_id=notif.id,
        conversation_id=None,
    )
    create_interaction_event(
        db,
        user_id=user.id,
        event_type="chat_message",
        source="notification",
        source_notification_id=notif.id,
        conversation_id="other",
    )
    db.commit()

    import importlib.util

    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "050_gate4_interaction_event_idempotency.py"
    )
    spec = importlib.util.spec_from_file_location("mig050b", mig_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    with pytest.raises(RuntimeError, match="Refusing to create"):
        mod._raise_if_duplicates(db.get_bind())
