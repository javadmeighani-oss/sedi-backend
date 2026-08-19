"""Timezone-safe GET /memory/history grouping and response contract (Section 14-A1)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import Memory, User, UserMemoryFact, UserProfileCore
from backend.app.services.i6.consent_service import grant_memory_consent


def _auth_header(user_id: int) -> dict[str, str]:
    token = create_access_token({"user_id": user_id})
    return {"Authorization": f"Bearer {token}"}


def _create_user(db, name: str) -> User:
    u = User(name=name, secret_key="test", preferred_language="en")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _set_profile_timezone(db, user_id: int, tz: str) -> None:
    profile = UserProfileCore(user_id=user_id, timezone=tz)
    db.add(profile)
    db.commit()


def _set_memory_timezone(db, user_id: int, tz: str) -> None:
    """Leftover I6 timezone row (compatibility read). New I6 timezone writes are blocked."""
    import json

    grant_memory_consent(db, user_id, commit=True)
    db.add(
        UserMemoryFact(
            user_id=user_id,
            domain="preferences",
            key="timezone",
            value_json=json.dumps({"tz": tz}),
            confidence=1.0,
            source="test",
        )
    )
    db.commit()


def test_history_includes_timezone_and_current_group_key_daily(client, db):
    u = _create_user(db, "TzMetaUser")
    _set_profile_timezone(db, u.id, "Asia/Tehran")
    fixed_now = datetime(2026, 3, 15, 20, 30, 0, tzinfo=timezone.utc)

    with patch("backend.app.routers.memory.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        response = client.get(
            "/memory/history?group=daily&limit=10",
            headers=_auth_header(u.id),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Asia/Tehran"
    assert body["current_group_key"] == "2026-03-16"


@pytest.mark.parametrize(
    ("group", "expected_key"),
    [
        ("daily", "2026-06-10"),
        ("weekly", "2026-W24"),
        ("monthly", "2026-06"),
        ("yearly", "2026"),
    ],
)
def test_current_group_key_for_all_group_kinds(client, db, group, expected_key):
    u = _create_user(db, f"TzGroup_{group}")
    _set_profile_timezone(db, u.id, "UTC")
    fixed_now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)

    with patch("backend.app.routers.memory.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_now
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        response = client.get(
            f"/memory/history?group={group}&limit=10",
            headers=_auth_header(u.id),
        )

    assert response.status_code == 200
    assert response.json()["current_group_key"] == expected_key


def test_same_user_local_day_across_utc_midnight(client, db):
    u = _create_user(db, "TzSameLocalDay")
    _set_profile_timezone(db, u.id, "Asia/Tehran")

    db.add(
        Memory(
            user_id=u.id,
            user_message="just after UTC evening",
            sedi_response="a",
            language="en",
            created_at=datetime(2026, 1, 15, 21, 0, 0),
        )
    )
    db.add(
        Memory(
            user_id=u.id,
            user_message="still same Tehran day",
            sedi_response="b",
            language="en",
            created_at=datetime(2026, 1, 15, 22, 0, 0),
        )
    )
    db.commit()

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["key"] == "2026-01-16"
    assert len(body["items"][0]["turns"]) == 2


def test_same_utc_day_different_user_local_days(client, db):
    u = _create_user(db, "TzDiffLocalDay")
    _set_profile_timezone(db, u.id, "America/Los_Angeles")

    db.add(
        Memory(
            user_id=u.id,
            user_message="still prior local day",
            sedi_response="a",
            language="en",
            created_at=datetime(2026, 1, 15, 7, 0, 0),
        )
    )
    db.add(
        Memory(
            user_id=u.id,
            user_message="next local day",
            sedi_response="b",
            language="en",
            created_at=datetime(2026, 1, 15, 9, 0, 0),
        )
    )
    db.commit()

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["items"]}
    assert keys == {"2026-01-14", "2026-01-15"}


def test_created_at_serializes_with_explicit_utc_offset(client, db):
    u = _create_user(db, "TzUtcOffset")
    db.add(
        Memory(
            user_id=u.id,
            user_message="hello",
            sedi_response="hi",
            language="en",
            created_at=datetime(2026, 2, 1, 10, 15, 30),
        )
    )
    db.commit()

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    created_at = response.json()["items"][0]["turns"][0]["created_at"]
    assert "+00:00" in created_at or created_at.endswith("Z")


def test_invalid_timezone_falls_back_to_default(client, db):
    u = _create_user(db, "TzInvalid")
    _set_profile_timezone(db, u.id, "Not/A_Real_Zone")

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Tehran"


def test_missing_timezone_uses_memory_fact(client, db):
    u = _create_user(db, "TzMemoryFact")
    _set_memory_timezone(db, u.id, "Europe/Berlin")

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Berlin"


def test_memory_history_rejects_legacy_user_id_query(client, db):
    u = _create_user(db, "TzJwtReject")
    response = client.get(
        f"/memory/history?user_id={u.id}&group=daily&limit=10",
        headers=_auth_header(u.id),
    )
    assert response.status_code == 422


def test_memory_history_cross_user_isolation(client, db):
    user_a = _create_user(db, "TzIsoA")
    user_b = _create_user(db, "TzIsoB")
    db.add(
        Memory(
            user_id=user_b.id,
            user_message="secret",
            sedi_response="hidden",
            language="en",
        )
    )
    db.commit()

    response = client.get(
        "/memory/history?group=daily&limit=10",
        headers=_auth_header(user_a.id),
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
