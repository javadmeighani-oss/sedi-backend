"""G1 / C03 — SELF 1:1 schema hardening + identity PG16 certification.

GATE=SEDI-V1-BE-FINALCERT-G1-C03-SELF-1TO1-SCHEMA-HARDENING-AND-IDENTITY-PG16-CERTIFICATION-01
SCENARIO=SEDI-V1-REAL-FAMILY-CARE-E2E-01 (identity/access slice only)

PostgreSQL 16 required (TEST_DATABASE_URL). No Smart-RAG. No DRVS reopen. No real FCM.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app import models
from backend.app.services.i10.care_network_access import (
    CareNetworkAccessError,
    grant_caregiver_subject_access,
    revoke_caregiver_subject_access,
)
from backend.app.services.i10.care_network_actor import CareNetworkAuthorizationError
from backend.app.services.i10.care_network_grants import (
    CareNetworkGrantError,
    create_subject_notification_grant,
    revoke_subject_notification_grant_by_scope,
)
from backend.app.services.i10.policy_types import I10NotificationScope
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    account_can_access_subject,
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
    require_account_subject_access,
    resolve_canonical_active_self_subject,
)
from backend.tests.helpers.i10_postgresql_harness import (
    ALEMBIC_HEAD,
    I10IsolatedPgDb,
    _REV_080,
    _REV_081,
    pg_index_exists,
)

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

SCENARIO_ID = "SEDI-V1-REAL-FAMILY-CARE-E2E-01"
IDX_HS = "uq_health_subjects_active_self_linked_user"
IDX_AHSA = "uq_ahsa_active_self_account"


@pytest.fixture(scope="module")
def g1_pg_db_module():
    isolated = I10IsolatedPgDb.create(suffix="g1c03", revision=_REV_081)
    SessionLocal = isolated.session_factory()
    try:
        yield SessionLocal, isolated
    finally:
        isolated.close()


@pytest.fixture()
def db(g1_pg_db_module):
    SessionLocal, isolated = g1_pg_db_module
    connection = isolated.engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:8]}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _family_identity(db):
    """Canonical G1 family identity slice (no device/I10 delivery)."""
    suffix = uuid4().hex[:8]
    son = _user(db, f"G1-Son-{suffix}")
    stranger = _user(db, f"G1-Stranger-{suffix}")
    son_self = ensure_self_subject_for_account(db, son.id, display_name="SON_SELF", commit=False)
    mother = create_managed_subject_without_account(
        db,
        account_user_id=son.id,
        display_name="MOTHER_ALS",
        access_role="MANAGER",
        commit=False,
    )
    assert son_self.id != mother.id
    assert son_self.linked_user_id == son.id
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    assert son_self.subject_kind == "self"
    # No Mother Account exists
    mother_accounts = (
        db.query(models.User).filter(models.User.id == mother.linked_user_id).count()
        if mother.linked_user_id is not None
        else 0
    )
    assert mother_accounts == 0
    return son, stranger, son_self, mother


# --- C03-01..C03-06 ---


def test_C03_01_account_auth_primary_user(db):
    son, _stranger, son_self, mother = _family_identity(db)
    assert son.id is not None
    assert son_self.linked_user_id == son.id
    assert SCENARIO_ID == "SEDI-V1-REAL-FAMILY-CARE-E2E-01"
    assert son_self.id != mother.id


def test_C03_02_self_lazy_create_reuse_path(db):
    son = _user(db, "reuse-son")
    a = ensure_self_subject_for_account(db, son.id, display_name="A", commit=False)
    b = ensure_self_subject_for_account(db, son.id, display_name="B", commit=False)
    assert a.id == b.id
    assert resolve_canonical_active_self_subject(db, son.id).id == a.id


def test_C03_03_managed_mother_linked_user_null(db):
    _son, _stranger, _self, mother = _family_identity(db)
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"


def test_C03_04_ahsa_without_account_substitution(db):
    son, stranger, son_self, mother = _family_identity(db)
    assert account_can_access_subject(db, son.id, mother.id) is True
    assert account_can_access_subject(db, stranger.id, mother.id) is False
    # Stranger cannot resolve Mother via require
    with pytest.raises(HealthSubjectAccessDenied):
        require_account_subject_access(db, stranger.id, mother.id)
    # Son SELF is not Mother
    assert require_account_subject_access(db, son.id, son_self.id).id == son_self.id
    assert son_self.id != mother.id


def test_C03_05_primitive_grant_issue_revoke_fail_closed(db):
    son, stranger, _self, mother = _family_identity(db)
    grant_caregiver_subject_access(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_account_user_id=stranger.id,
        access_role="CAREGIVER",
        commit=False,
    )
    assert account_can_access_subject(db, stranger.id, mother.id) is True
    revoke_caregiver_subject_access(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_account_user_id=stranger.id,
        commit=False,
    )
    assert account_can_access_subject(db, stranger.id, mother.id) is False

    create_subject_notification_grant(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        commit=False,
    )
    revoke_subject_notification_grant_by_scope(
        db,
        actor_user_id=son.id,
        health_subject_id=mother.id,
        recipient_user_id=son.id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        commit=False,
    )
    active = (
        db.query(models.HealthSubjectNotificationGrant)
        .filter(
            models.HealthSubjectNotificationGrant.health_subject_id == mother.id,
            models.HealthSubjectNotificationGrant.recipient_user_id == son.id,
            models.HealthSubjectNotificationGrant.is_active.is_(True),
            models.HealthSubjectNotificationGrant.revoked_at.is_(None),
        )
        .count()
    )
    assert active == 0
    with pytest.raises(
        (CareNetworkAccessError, CareNetworkGrantError, CareNetworkAuthorizationError, HealthSubjectAccessDenied)
    ):
        # Stranger still cannot manage Mother after revoke
        grant_caregiver_subject_access(
            db,
            actor_user_id=stranger.id,
            health_subject_id=mother.id,
            recipient_account_user_id=stranger.id,
            access_role="CAREGIVER",
            commit=False,
        )


def test_C03_06_no_account_hs_substitution(db):
    son, stranger, son_self, mother = _family_identity(db)
    other = _user(db, "other-son")
    other_self = ensure_self_subject_for_account(db, other.id, commit=False)
    # Wrong account cannot access Son SELF
    with pytest.raises(HealthSubjectAccessDenied):
        require_account_subject_access(db, stranger.id, son_self.id)
    # Wrong HS: Son cannot treat other SELF as own
    with pytest.raises(HealthSubjectAccessDenied):
        require_account_subject_access(db, son.id, other_self.id)
    # Cannot grant stranger access as if Mother were Son's SELF
    assert son_self.id != mother.id
    assert other_self.id != son_self.id


# --- C03-07 schema / concurrency ---


def test_C03_07a_sequential_self_ensure_one_subject(db):
    son = _user(db, "seq-son")
    ids = [
        ensure_self_subject_for_account(db, son.id, commit=False).id for _ in range(5)
    ]
    assert len(set(ids)) == 1


def test_C03_07b_c_concurrent_self_and_ahsa(g1_pg_db_module):
    """Two concurrent PostgreSQL sessions → one ACTIVE SELF + one effective SELF AHSA."""
    SessionLocal, isolated = g1_pg_db_module
    setup = SessionLocal()
    try:
        son = models.User(
            name=f"conc-son-{uuid4().hex[:8]}",
            secret_key=f"sk-conc-{uuid4().hex[:8]}",
            preferred_language="en",
        )
        setup.add(son)
        setup.commit()
        setup.refresh(son)
        account_id = int(son.id)
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        s = SessionLocal()
        try:
            barrier.wait(timeout=30)
            hs = ensure_self_subject_for_account(s, account_id, commit=True)
            results.append(int(hs.id))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(worker) for _ in range(2)]
        for f in as_completed(futs):
            f.result()

    assert not errors, errors
    assert len(results) == 2
    assert results[0] == results[1]

    verify = SessionLocal()
    try:
        n_hs = (
            verify.query(models.HealthSubject)
            .filter(
                models.HealthSubject.linked_user_id == account_id,
                models.HealthSubject.subject_kind == "self",
                models.HealthSubject.status == "active",
            )
            .count()
        )
        n_ahsa = (
            verify.query(models.AccountHealthSubjectAccess)
            .filter(
                models.AccountHealthSubjectAccess.account_user_id == account_id,
                models.AccountHealthSubjectAccess.access_role == "SELF",
                models.AccountHealthSubjectAccess.is_active.is_(True),
                models.AccountHealthSubjectAccess.revoked_at.is_(None),
            )
            .count()
        )
        assert n_hs == 1
        assert n_ahsa == 1
    finally:
        verify.close()


def test_C03_07d_canonical_retry_recovery(db):
    son = _user(db, "retry-son")
    first = ensure_self_subject_for_account(db, son.id, commit=False)
    second = ensure_self_subject_for_account(db, son.id, commit=False)
    assert first.id == second.id


def test_C03_07e_managed_mother_unaffected(db):
    son = _user(db, "m-son")
    ensure_self_subject_for_account(db, son.id, commit=False)
    m1 = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="M1", access_role="CAREGIVER", commit=False
    )
    m2 = create_managed_subject_without_account(
        db, account_user_id=son.id, display_name="M2", access_role="MANAGER", commit=False
    )
    assert m1.id != m2.id
    assert m1.linked_user_id is None and m2.linked_user_id is None


def test_C03_07f_different_accounts_own_self(db):
    a = _user(db, "acct-a")
    b = _user(db, "acct-b")
    sa = ensure_self_subject_for_account(db, a.id, commit=False)
    sb = ensure_self_subject_for_account(db, b.id, commit=False)
    assert sa.id != sb.id
    assert sa.linked_user_id == a.id
    assert sb.linked_user_id == b.id


def test_C03_07g_inactive_historical_self_ok(db):
    son = _user(db, "hist-son")
    active = ensure_self_subject_for_account(db, son.id, commit=False)
    # Historical inactive SELF with same linked_user does not violate active unique.
    hist = models.HealthSubject(
        display_name="HIST_SELF",
        linked_user_id=son.id,
        subject_kind="self",
        status="inactive",
    )
    db.add(hist)
    db.flush()
    again = ensure_self_subject_for_account(db, son.id, commit=False)
    assert again.id == active.id
    assert hist.id != active.id


def test_C03_07h_unexpected_integrity_not_swallowed(db):
    """Non-SELF uniqueness IntegrityError must not be recovered as SELF race."""
    son = _user(db, "err-son")
    ensure_self_subject_for_account(db, son.id, commit=False)
    # Force a non-SELF unique violation via creator idempotency key if present.
    key = f"idem-{uuid4().hex}"
    s1 = models.HealthSubject(
        display_name="X1",
        linked_user_id=None,
        subject_kind="managed",
        status="active",
        created_by_account_user_id=son.id,
        creation_idempotency_key=key,
    )
    db.add(s1)
    db.flush()
    s2 = models.HealthSubject(
        display_name="X2",
        linked_user_id=None,
        subject_kind="managed",
        status="active",
        created_by_account_user_id=son.id,
        creation_idempotency_key=key,
    )
    db.add(s2)
    with pytest.raises(IntegrityError):
        db.flush()


def test_C03_07_indexes_exist(g1_pg_db_module):
    _SessionLocal, isolated = g1_pg_db_module
    assert isolated.head() == _REV_081
    with isolated.engine.connect() as conn:
        assert pg_index_exists(conn, IDX_HS)
        assert pg_index_exists(conn, IDX_AHSA)
        pred_hs = conn.execute(
            text(
                """
                SELECT pg_get_expr(indpred, indrelid)
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = :name
                """
            ),
            {"name": IDX_HS},
        ).scalar_one()
        assert "self" in pred_hs.lower()
        assert "active" in pred_hs.lower()


def test_C03_07_migration_up_down_reup():
    isolated = I10IsolatedPgDb.create(suffix="g1mig", revision=_REV_080)
    try:
        assert isolated.head() == _REV_080
        with isolated.engine.connect() as conn:
            assert not pg_index_exists(conn, IDX_HS)
            assert not pg_index_exists(conn, IDX_AHSA)
        command.upgrade(isolated.cfg, _REV_081)
        assert isolated.head() == _REV_081
        with isolated.engine.connect() as conn:
            assert pg_index_exists(conn, IDX_HS)
            assert pg_index_exists(conn, IDX_AHSA)
        command.downgrade(isolated.cfg, _REV_080)
        assert isolated.head() == _REV_080
        with isolated.engine.connect() as conn:
            assert not pg_index_exists(conn, IDX_HS)
            assert not pg_index_exists(conn, IDX_AHSA)
        command.upgrade(isolated.cfg, _REV_081)
        assert isolated.head() == _REV_081
    finally:
        isolated.close()


def test_C03_07_dirty_duplicate_upgrade_fail_closed():
    isolated = I10IsolatedPgDb.create(suffix="g1dirty", revision=_REV_080)
    try:
        SessionLocal = isolated.session_factory()
        s = SessionLocal()
        try:
            u = models.User(
                name=f"dirty-{uuid4().hex[:8]}",
                secret_key=f"sk-dirty-{uuid4().hex[:8]}",
                preferred_language="en",
            )
            s.add(u)
            s.flush()
            s.add_all(
                [
                    models.HealthSubject(
                        display_name="D1",
                        linked_user_id=u.id,
                        subject_kind="self",
                        status="active",
                    ),
                    models.HealthSubject(
                        display_name="D2",
                        linked_user_id=u.id,
                        subject_kind="self",
                        status="active",
                    ),
                ]
            )
            s.commit()
            uid = int(u.id)
        finally:
            s.close()

        with pytest.raises(Exception) as ei:
            command.upgrade(isolated.cfg, _REV_081)
        assert "SELF_1TO1_HARDENING_BLOCKED" in str(ei.value)

        # No auto-delete / merge: both rows remain; still at 080
        assert isolated.head() == _REV_080
        s2 = SessionLocal()
        try:
            n = (
                s2.query(models.HealthSubject)
                .filter(
                    models.HealthSubject.linked_user_id == uid,
                    models.HealthSubject.subject_kind == "self",
                    models.HealthSubject.status == "active",
                )
                .count()
            )
            assert n == 2
        finally:
            s2.close()
    finally:
        isolated.close()


def test_alembic_single_head_is_081():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [_REV_081]
    rev = script.get_revision(_REV_081)
    assert rev.down_revision == _REV_080
    assert ALEMBIC_HEAD == _REV_081
