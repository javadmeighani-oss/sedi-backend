"""I6 product-default memory: create only when no prior decision exists."""

from __future__ import annotations

pytest_plugins = ["backend.tests.section42_sqlite_harness"]

from datetime import datetime, timedelta, timezone

from backend.app import models
from backend.app.services.a3_session_open import open_a3_session
from backend.app.services.i6.consent_service import (
    DEFAULT_MEMORY_POLICY_VERSION,
    DEFAULT_MEMORY_PROVENANCE,
    DEFAULT_MEMORY_SOURCE,
    PERM_FORGET,
    PERM_READ,
    PERM_WRITE,
    ensure_default_memory_enabled,
    get_memory_consent_status,
    grant_memory_consent,
    has_permission,
    revoke_memory_consent,
)


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key="i6-default-test", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _matching(db, user_id: int):
    return (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.consent_type == "MEMORY",
            models.UserConsent.purpose == "PERSONAL_LONG_TERM_MEMORY",
        )
        .all()
    )


def test_default_memory_created_only_with_no_prior_decision(db):
    user = _user(db, "i6-default-new")
    assert _matching(db, user.id) == []
    created = ensure_default_memory_enabled(db, user.id, commit=True)
    assert created is not None
    assert created.status == "active"
    assert created.source == DEFAULT_MEMORY_SOURCE
    assert created.provenance == DEFAULT_MEMORY_PROVENANCE
    assert created.policy_version == DEFAULT_MEMORY_POLICY_VERSION
    assert created.source != "user_granted"
    assert created.provenance != "user_granted"
    assert has_permission(db, user.id, PERM_WRITE) is True
    assert has_permission(db, user.id, PERM_READ) is True
    assert has_permission(db, user.id, PERM_FORGET) is True

    again = ensure_default_memory_enabled(db, user.id, commit=True)
    assert again is not None
    assert again.id == created.id
    assert again.source == DEFAULT_MEMORY_SOURCE
    assert len(_matching(db, user.id)) == 1


def _consent_metadata(row: models.UserConsent) -> tuple:
    return (
        row.id,
        row.status,
        row.source,
        row.provenance,
        row.policy_version,
        row.scope_summary,
        row.grantee_type,
        row.grantee_id,
        row.granted_at,
        row.effective_from,
        row.effective_until,
        row.revoked_at,
        row.revocation_reason,
        row.updated_at,
    )


def _scope_rows(db, consent_id: int) -> list[tuple]:
    rows = (
        db.query(models.UserConsentScope)
        .filter(models.UserConsentScope.consent_id == consent_id)
        .order_by(models.UserConsentScope.id)
        .all()
    )
    return [(row.id, row.permission_key, row.allowed, row.metadata_json) for row in rows]


def test_existing_active_consent_scopes_are_preserved_exactly(db):
    user = _user(db, "i6-default-active-preserve")
    consent = grant_memory_consent(db, user.id, commit=True)
    write_scope = (
        db.query(models.UserConsentScope)
        .filter_by(consent_id=consent.id, permission_key=PERM_WRITE)
        .one()
    )
    write_scope.allowed = False
    forget_scope = (
        db.query(models.UserConsentScope)
        .filter_by(consent_id=consent.id, permission_key=PERM_FORGET)
        .one()
    )
    db.delete(forget_scope)
    db.commit()
    db.refresh(consent)

    before_meta = _consent_metadata(consent)
    before_scopes = _scope_rows(db, consent.id)
    assert {key for _, key, _, _ in before_scopes} == {PERM_READ, PERM_WRITE}
    assert (PERM_WRITE, False) in {(key, allowed) for _, key, allowed, _ in before_scopes}
    assert (PERM_READ, True) in {(key, allowed) for _, key, allowed, _ in before_scopes}

    result = ensure_default_memory_enabled(db, user.id, commit=True)
    db.refresh(consent)

    assert result is not None
    assert result.id == consent.id
    assert _consent_metadata(result) == before_meta
    assert _scope_rows(db, consent.id) == before_scopes
    assert has_permission(db, user.id, PERM_READ) is True
    assert has_permission(db, user.id, PERM_WRITE) is False
    assert has_permission(db, user.id, PERM_FORGET) is False


def test_revoked_memory_is_never_auto_reactivated(db):
    user = _user(db, "i6-default-revoked")
    grant_memory_consent(db, user.id, commit=True)
    assert revoke_memory_consent(db, user.id, commit=True) is True
    assert has_permission(db, user.id, PERM_READ) is False
    result = ensure_default_memory_enabled(db, user.id, commit=True)
    assert result is None
    assert has_permission(db, user.id, PERM_WRITE) is False
    assert has_permission(db, user.id, PERM_READ) is False
    assert get_memory_consent_status(db, user.id)["granted"] is False
    assert all(row.status != "active" for row in _matching(db, user.id))


def test_expired_memory_is_never_auto_reactivated(db):
    user = _user(db, "i6-default-expired")
    consent = grant_memory_consent(db, user.id, commit=True)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    result = ensure_default_memory_enabled(db, user.id, commit=True)
    assert result is None
    assert has_permission(db, user.id, PERM_READ) is False
    rows = _matching(db, user.id)
    assert any(row.status == "expired" for row in rows)
    assert all(row.status != "active" for row in rows)


def test_default_provenance_is_truthful_not_user_granted(db):
    user = _user(db, "i6-default-provenance")
    created = ensure_default_memory_enabled(db, user.id, commit=True)
    assert created.source == "product_default_v1"
    assert created.provenance == "service_default"
    explicit = grant_memory_consent(db, user.id, commit=True)
    assert explicit.id == created.id
    assert explicit.source == "product_default_v1"


def test_explicit_regrant_after_revoke_still_works(db):
    user = _user(db, "i6-default-regrant")
    ensure_default_memory_enabled(db, user.id, commit=True)
    assert revoke_memory_consent(db, user.id, commit=True) is True
    assert ensure_default_memory_enabled(db, user.id, commit=True) is None
    granted = grant_memory_consent(db, user.id, commit=True)
    assert granted.status == "active"
    assert granted.source == "i6_consent_service"
    assert granted.provenance == "user_granted"
    assert has_permission(db, user.id, PERM_WRITE) is True
    assert has_permission(db, user.id, PERM_READ) is True
    assert has_permission(db, user.id, PERM_FORGET) is True


def test_session_open_invokes_default_memory_before_context(db):
    user = _user(db, "i6-default-open")
    db.commit()
    open_a3_session(db, user)
    rows = _matching(db, user.id)
    assert len(rows) == 1
    assert rows[0].status == "active"
    assert rows[0].source == DEFAULT_MEMORY_SOURCE
    assert rows[0].provenance == DEFAULT_MEMORY_PROVENANCE
    assert get_memory_consent_status(db, user.id)["granted"] is True


def test_session_open_does_not_reactivate_revoked_or_expired(db):
    revoked = _user(db, "i6-default-open-revoked")
    grant_memory_consent(db, revoked.id, commit=True)
    revoke_memory_consent(db, revoked.id, commit=True)
    open_a3_session(db, revoked)
    assert get_memory_consent_status(db, revoked.id)["granted"] is False

    expired = _user(db, "i6-default-open-expired")
    consent = grant_memory_consent(db, expired.id, commit=True)
    consent.effective_until = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    open_a3_session(db, expired)
    assert get_memory_consent_status(db, expired.id)["granted"] is False


def test_no_schema_or_public_api_contract_change():
    from pathlib import Path

    router = Path("backend/app/routers/memory.py").read_text(encoding="utf-8")
    assert '@router.get("/consent"' in router
    assert '@router.post("/consent/grant"' in router
    assert '@router.post("/consent/revoke"' in router
    grant_block = router.split("def grant_memory_consent_endpoint")[1].split("def ")[0]
    revoke_block = router.split("def revoke_memory_consent_endpoint")[1].split("def ")[0]
    assert "Body(" not in grant_block
    assert "Body(" not in revoke_block
    assert "/consent/default" not in router
    assert "/memory/consent/default" not in router
    service = Path("backend/app/services/i6/consent_service.py").read_text(encoding="utf-8")
    assert "def ensure_default_memory_enabled(" in service
    session = Path("backend/app/services/a3_session_open.py").read_text(encoding="utf-8")
    assert "def open_a3_session(" in session
    open_fn = session.split("def open_a3_session(", 1)[1]
    helper_idx = open_fn.index(
        "ensure_default_memory_enabled(db, int(user.id), commit=True)"
    )
    ctx_idx = open_fn.index("UserContextService(db).get_user_context")
    opener_idx = open_fn.index("proactive = maybe_proactive_opener(db, user)")
    assert helper_idx < ctx_idx < opener_idx
