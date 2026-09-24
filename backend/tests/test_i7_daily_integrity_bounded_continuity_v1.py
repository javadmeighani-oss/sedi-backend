"""I7 DAILY integrity: bounded_continuity must hash the stored final JSON."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent, revoke_memory_consent
from backend.app.services.i7.derived_continuity import (
    get_bounded_continuity_topic,
    parse_bounded_continuity,
    refresh_bounded_continuity,
)
from backend.app.services.i7.governed_raw import try_durable_raw_write
from backend.app.services.i7.hierarchy import build_daily_from_raw, get_canonical_daily
from backend.app.services.i7.retention import RAW_VISIBLE_DAYS
from backend.app.services.intelligence.adapters import CurrentMemoryContextAdapter

WALK = "I want to start walking 30 minutes every evening."
BREAKFAST = "What is a healthy breakfast?"


def _hash(blob: str) -> str:
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _user(db, name: str, phone: str) -> models.User:
    row = models.User(name=name, secret_key="i7-int", preferred_language="en", phone=phone)
    db.add(row)
    db.flush()
    return row


def _assert_integrity(row: models.UserPeriodSummary) -> None:
    assert row.structured_summary_json
    assert row.integrity_sha256 == _hash(row.structured_summary_json)
    payload = json.loads(row.structured_summary_json)
    assert payload.get("bounded_continuity", {}).get("topic")


def test_raw_retention_days_unchanged():
    assert RAW_VISIBLE_DAYS == 30


def test_fresh_daily_bounded_continuity_matches_integrity(db):
    user = _user(db, "i7-fresh", "+989160030001")
    grant_memory_consent(db, user.id, commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    assert written.durable is True
    row = get_canonical_daily(db, user.id)
    assert row is not None
    assert row.status == "active"
    _assert_integrity(row)
    assert get_bounded_continuity_topic(db, user.id)
    assert "walking" in get_bounded_continuity_topic(db, user.id).lower()


def test_rebuild_preserves_continuity_and_matching_integrity(db):
    user = _user(db, "i7-rebuild", "+989160030002")
    grant_memory_consent(db, user.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    rebuilt = build_daily_from_raw(db, user.id, finalize=False, commit=True)
    _assert_integrity(rebuilt)
    bc = parse_bounded_continuity(rebuilt)
    assert "walking" in str(bc.get("topic") or "").lower()
    again = build_daily_from_raw(db, user.id, finalize=False, commit=True)
    assert again.id == rebuilt.id
    assert again.version == rebuilt.version
    _assert_integrity(again)
    assert parse_bounded_continuity(again).get("topic") == bc.get("topic")


def test_finalized_historical_row_not_silently_mutated(db):
    user = _user(db, "i7-final", "+989160030003")
    grant_memory_consent(db, user.id, commit=True)
    first = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    finalized = build_daily_from_raw(db, user.id, finalize=True, commit=True)
    assert finalized.finalized_at is not None
    frozen_id = finalized.id
    frozen_json = finalized.structured_summary_json
    frozen_hash = finalized.integrity_sha256
    frozen_version = finalized.version
    _assert_integrity(finalized)

    same = refresh_bounded_continuity(db, user_id=user.id, memory=first.memory)
    db.commit()
    db.refresh(finalized)
    assert same.id == frozen_id
    assert finalized.structured_summary_json == frozen_json
    assert finalized.integrity_sha256 == frozen_hash
    assert finalized.version == frozen_version
    assert finalized.finalized_at is not None

    second = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=BREAKFAST,
        sedi_response="Oats.",
        actor_user_id=user.id,
        commit=True,
    )
    assert second.durable is True
    db.refresh(finalized)
    assert finalized.id == frozen_id
    assert finalized.structured_summary_json == frozen_json
    assert finalized.integrity_sha256 == frozen_hash
    assert finalized.status == "superseded"
    active = get_canonical_daily(db, user.id)
    assert active.id != frozen_id
    assert active.version == frozen_version + 1
    _assert_integrity(active)
    assert "breakfast" in (parse_bounded_continuity(active).get("topic") or "").lower()


def test_same_content_rebuild_is_idempotent(db):
    user = _user(db, "i7-idem", "+989160030004")
    grant_memory_consent(db, user.id, commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    row = get_canonical_daily(db, user.id)
    again = refresh_bounded_continuity(db, user_id=user.id, memory=written.memory)
    db.commit()
    assert again.id == row.id
    assert again.version == row.version
    daily = build_daily_from_raw(db, user.id, finalize=False, commit=True)
    same = build_daily_from_raw(db, user.id, finalize=False, commit=True)
    assert same.id == daily.id
    assert same.version == daily.version
    _assert_integrity(same)


def test_revoke_blocks_projection_without_corrupting_stored_daily(db):
    user = _user(db, "i7-rev", "+989160030005")
    grant_memory_consent(db, user.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    row = get_canonical_daily(db, user.id)
    stored_json = row.structured_summary_json
    stored_hash = row.integrity_sha256
    revoke_memory_consent(db, user.id, commit=True)
    assert get_bounded_continuity_topic(db, user.id) is None
    assert CurrentMemoryContextAdapter().load(db, authenticated_user_id=user.id) == []
    db.refresh(row)
    assert row.structured_summary_json == stored_json
    assert row.integrity_sha256 == stored_hash
    assert row.integrity_sha256 == _hash(row.structured_summary_json)


def test_cross_user_daily_isolation(db):
    a = _user(db, "i7-iso-a", "+989160030006")
    b = _user(db, "i7-iso-b", "+989160030007")
    grant_memory_consent(db, a.id, commit=True)
    grant_memory_consent(db, b.id, commit=True)
    try_durable_raw_write(
        db,
        user_id=a.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=a.id,
        commit=True,
    )
    assert get_bounded_continuity_topic(db, a.id)
    assert get_bounded_continuity_topic(db, b.id) is None
    assert get_canonical_daily(db, b.id) is None
    a_row = get_canonical_daily(db, a.id)
    _assert_integrity(a_row)
    items = CurrentMemoryContextAdapter().load(db, authenticated_user_id=b.id)
    text = " ".join(str(getattr(i, "structured_value", "")) for i in items)
    assert WALK not in text
    assert "walking" not in text.lower()


def test_raw_expiry_leaves_derived_daily_integrity_intact(db):
    user = _user(db, "i7-exp", "+989160030008")
    grant_memory_consent(db, user.id, commit=True)
    written = try_durable_raw_write(
        db,
        user_id=user.id,
        user_message=WALK,
        sedi_response="Noted.",
        actor_user_id=user.id,
        commit=True,
    )
    mem = written.memory
    mem.retain_until = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    row = get_canonical_daily(db, user.id)
    _assert_integrity(row)
    assert get_bounded_continuity_topic(db, user.id)
    assert RAW_VISIBLE_DAYS == 30
