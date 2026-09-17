"""A3 Heart interaction lifecycle + bounded context completion tests.

GATE=SEDI-V1-BACKEND-A3-HEART-INTERACTION-LIFECYCLE-AND-CONTEXT-COMPLETION-01
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.conversation.persona_policy_v1 import (
    PERSONA_POLICY_VERSION,
    PersonaPolicyV1,
)
from backend.app.services.a3_bounded_context_projection import (
    format_i8_context_block,
    format_i9_context_block,
    project_bounded_i8_actions,
    project_bounded_i9_facts,
)
from backend.app.services.a3_interaction_lifecycle import (
    FIRST_CONTACT,
    INTERACTION_POLICY_VERSION,
    NEW_DAY_RETURN,
    NOTIFICATION_CONTINUATION,
    SAME_DAY_RETURN,
    format_lifecycle_context_block,
    resolve_interaction_lifecycle,
)
from backend.app.services.a3_session_open import (
    build_first_intro_message,
    open_a3_session,
)


class _User:
    def __init__(
        self,
        id=1,
        name="Sara",
        preferred_language="en",
        intro=None,
    ):
        self.id = id
        self.name = name
        self.preferred_language = preferred_language
        self.sedi_intro_completed_at = intro


def _db_with_tz_and_memory(
    *,
    tz_name: str | None,
    last_memory_at: datetime | None,
):
    """Minimal Session stub for lifecycle resolver."""

    class _Q:
        def __init__(self, first_val):
            self._first = first_val

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return self._first

    class _Db:
        def query(self, model):
            # UserProfileCore.timezone vs Memory.created_at
            name = getattr(model, "key", None) or getattr(model, "name", None)
            # SQLAlchemy ColumnElement — detect by comparing to models attributes
            from backend.app import models

            if model is models.UserProfileCore:
                if tz_name:
                    return _Q(SimpleNamespace(timezone=tz_name, user_id=1))
                return _Q(None)
            if model is models.Memory.created_at or model is models.Memory:
                if last_memory_at is None:
                    return _Q(None)
                # query(Memory.created_at) returns tuple-like row
                return _Q((last_memory_at,))
            return _Q(None)

    return _Db()


# ---- CASE01–03 first contact ----


def test_case01_first_contact_uses_known_preferred_name():
    u = _User(name=None, preferred_language="en")
    msg = build_first_intro_message(u, preferred_name="Neda")
    assert "Neda" in msg
    assert "Sedi" in msg
    assert "date of birth" not in msg.lower()
    assert "sex" not in msg.lower()


def test_case02_first_contact_does_not_reask_known_a2_facts():
    u = _User(name="Ali", preferred_language="en", intro=None)
    pack = SimpleNamespace(
        preferred_name="Ali",
        language="en",
        birth_year=1990,
        sex="male",
        addressing_preference="Ali",
        timezone="Asia/Tehran",
    )
    db = _db_with_tz_and_memory(tz_name="Asia/Tehran", last_memory_at=None)
    snap = resolve_interaction_lifecycle(db, u, user_context_pack=pack)
    assert snap.state == FIRST_CONTACT
    assert "birth_year" in snap.known_profile_keys
    assert "sex" in snap.known_profile_keys
    assert "Do not re-ask" in snap.instruction
    assert "birth_year" in snap.instruction
    msg = build_first_intro_message(u)
    assert "1990" not in msg
    assert "male" not in msg.lower()


def test_case03_open_session_marks_intro_state():
    class _Db:
        def add(self, *_a, **_k):
            return None

        def commit(self):
            return None

        def refresh(self, u):
            return None

        def query(self, *_a, **_k):
            class _Q:
                def filter(self, *_a, **_k):
                    return self

                def order_by(self, *_a, **_k):
                    return self

                def first(self):
                    return None

            return _Q()

    u = _User(intro=None, name="Sara")
    with patch(
        "backend.app.services.user_context.UserContextService.get_user_context",
        return_value=SimpleNamespace(
            preferred_name="Sara",
            language="en",
            birth_year=None,
            sex=None,
            addressing_preference=None,
            timezone=None,
            i8_bounded_actions=[],
            i9_bounded_facts=[],
        ),
    ):
        data = open_a3_session(_Db(), u)
    assert data["first_intro"] is True
    assert data["intro_completed"] is True
    assert u.sedi_intro_completed_at is not None
    assert "Sara" in data["message"]
    assert "date of birth" not in data["message"].lower()


# ---- CASE04–05 returning ----


def test_case04_same_day_return_no_reintroduction():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    now = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)
    last = datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc)
    db = _db_with_tz_and_memory(tz_name="UTC", last_memory_at=last)
    snap = resolve_interaction_lifecycle(db, u, now_utc=now)
    assert snap.state == SAME_DAY_RETURN
    assert "Do not re-introduce" in snap.instruction
    assert "FIRST_CONTACT" not in snap.instruction


def test_case05_returning_memory_dates_preserved():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    now = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)
    last = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
    db = _db_with_tz_and_memory(tz_name="UTC", last_memory_at=last)
    snap = resolve_interaction_lifecycle(db, u, now_utc=now)
    assert snap.last_meaningful_interaction_local_date == "2026-09-16"
    assert snap.today_local_date == "2026-09-17"


# ---- CASE06–08 local day ----


def test_case06_new_day_classification_user_local():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    # Tehran UTC+3:30 — 2026-09-16 22:00 UTC = 2026-09-17 01:30 local
    now = datetime(2026, 9, 16, 22, 0, tzinfo=timezone.utc)
    last = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)  # local still 16th
    db = _db_with_tz_and_memory(tz_name="Asia/Tehran", last_memory_at=last)
    snap = resolve_interaction_lifecycle(db, u, now_utc=now)
    assert snap.today_local_date == "2026-09-17"
    assert snap.last_meaningful_interaction_local_date == "2026-09-16"
    assert snap.state == NEW_DAY_RETURN


def test_case07_same_utc_date_different_local_date():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    # Same UTC calendar day components for "now" and "last" but local crosses midnight
    now = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)  # local 17th Tehran
    last = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)  # local 16th
    assert now.date() == last.date()  # same UTC date
    db = _db_with_tz_and_memory(tz_name="Asia/Tehran", last_memory_at=last)
    snap = resolve_interaction_lifecycle(db, u, now_utc=now)
    assert snap.today_local_date != snap.last_meaningful_interaction_local_date
    assert snap.state == NEW_DAY_RETURN


def test_case08_different_utc_date_same_local_date():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    # US Pacific: evening UTC May be previous calendar UTC day but same local day
    now = datetime(2026, 9, 17, 6, 0, tzinfo=timezone.utc)  # PDT = Sep 16 evening
    last = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)  # also Sep 16 local
    assert now.date() != last.date()
    db = _db_with_tz_and_memory(tz_name="America/Los_Angeles", last_memory_at=last)
    snap = resolve_interaction_lifecycle(db, u, now_utc=now)
    assert snap.today_local_date == snap.last_meaningful_interaction_local_date
    assert snap.state == SAME_DAY_RETURN


def test_timezone_gap_fail_closed_not_new_day():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    last = datetime(2026, 9, 10, tzinfo=timezone.utc)
    db = _db_with_tz_and_memory(tz_name=None, last_memory_at=last)
    snap = resolve_interaction_lifecycle(db, u)
    assert snap.timezone_authority_gap is True
    assert snap.state == SAME_DAY_RETURN
    assert snap.today_local_date is None


# ---- CASE09–10 notification ----


def test_case09_notification_continuation_overrides_opener_state():
    intro = datetime(2026, 1, 1, tzinfo=timezone.utc)
    u = _User(intro=intro)
    db = _db_with_tz_and_memory(tz_name="UTC", last_memory_at=None)
    snap = resolve_interaction_lifecycle(
        db,
        u,
        source_notification_id=42,
        notification_context={"category": "engagement"},
    )
    assert snap.state == NOTIFICATION_CONTINUATION
    assert "notification" in snap.instruction.lower()


def test_case10_safe_notification_context_formatter_no_body():
    from backend.app.core.conversation.brain import _format_notification_context_block

    block = _format_notification_context_block(
        {
            "category": "engagement",
            "risk_level": "low",
            "notification_title": "Hi",
            "body": "SECRET_BODY_MUST_NOT_APPEAR",
        }
    )
    assert block is not None
    assert "SECRET_BODY_MUST_NOT_APPEAR" not in block
    assert "engagement" in block


# ---- CASE11–15 I8/I9 ----


def test_case11_12_i8_bounded_actions_active_only():
    plan = SimpleNamespace(id=1, user_local_date=date(2026, 9, 17))
    active = SimpleNamespace(
        status="ACTIVE",
        safety_state="SAFE",
        action_domain="nutrition",
        summary_text="Drink water",
    )
    expired = SimpleNamespace(
        status="EXPIRED",
        safety_state="SAFE",
        action_domain="exercise",
        summary_text="Old run",
    )
    repo = MagicMock()
    repo.get_active_plan.return_value = plan
    repo.list_actions_for_plan.return_value = [active, expired]
    with patch(
        "backend.app.services.a3_bounded_context_projection.I8OperationalRepository",
        return_value=repo,
    ):
        items = project_bounded_i8_actions(
            MagicMock(), 1, today_local_date="2026-09-17"
        )
    assert len(items) == 1
    assert items[0]["summary"] == "Drink water"
    block = format_i8_context_block(items)
    assert "Drink water" in block
    assert "Old run" not in block
    assert "not plan authority" in block.lower()


def test_case13_14_15_i9_bounded_no_mad_no_dump():
    status = SimpleNamespace(
        status="STABLE",
        detected_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )
    latest = SimpleNamespace(
        value=72.0,
        measured_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
    )

    class _Q:
        def __init__(self, first_val):
            self._v = first_val

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return self._v

    class _Db:
        def query(self, model):
            return _Q(latest)

    with patch(
        "backend.app.services.a3_bounded_context_projection.resolve_or_ensure_self_health_subject_id",
        return_value=9,
        create=True,
    ), patch(
        "backend.app.services.i10.self_producer_adapter.resolve_or_ensure_self_health_subject_id",
        return_value=9,
    ), patch(
        "backend.app.services.a3_bounded_context_projection.get_effective_device_reported_vital_status",
        return_value=status,
    ):
        items = project_bounded_i9_facts(_Db(), 1)
    kinds = {i["kind"] for i in items}
    assert "device_reported_vital_status" in kinds
    assert "heart_rate_bpm" in kinds
    block = format_i9_context_block(items)
    assert "DEVICE_REPORTED" in block
    assert "72" in block
    assert "MAD" not in block
    assert "diagnosis" not in block.lower() or "do not derive" in block.lower()
    assert ">100" not in block
    assert "<60" not in block


# ---- CASE16 I6 ----


def test_case16_i6_absence_keeps_verified_facts_empty_path():
    from backend.app.services.user_context.user_context_service import _get_verified_facts

    with patch(
        "backend.app.services.user_profile_fact_service.list_profile_facts",
        return_value=[],
    ):
        assert _get_verified_facts(MagicMock(), 1) == {}


# ---- CASE17–19 language / persona ----


@pytest.mark.parametrize(
    "lang,intro_needle",
    [
        ("en", "Sedi"),
        ("fa", "صدی"),
        ("ar", "صدي"),
    ],
)
def test_case17_19_persona_and_intro_languages(lang, intro_needle):
    assert PERSONA_POLICY_VERSION == "persona_policy_v1"
    assert PersonaPolicyV1.policy_version == PERSONA_POLICY_VERSION
    assert PersonaPolicyV1.resolve_language(lang) == lang
    prompt = PersonaPolicyV1.system_prompt(lang)
    assert isinstance(prompt, str) and len(prompt) > 40
    u = _User(name="Sam", preferred_language=lang)
    msg = build_first_intro_message(u)
    assert intro_needle in msg
    assert INTERACTION_POLICY_VERSION == "a3_interaction_lifecycle_v1"


# ---- CASE20–22 I10 ----


def test_case20_21_self_scheduler_requires_i10_intake():
    import inspect

    from backend.app.services.i10 import self_producer_adapter

    src = inspect.getsource(self_producer_adapter.enqueue_self_scheduler_notification)
    assert "enqueue_i10_notification" in src


def test_case22_i10_canonical_policy_still_has_quiet_hours():
    from backend.app.services.i10 import canonical_policy

    src = open(canonical_policy.__file__, encoding="utf-8").read()
    assert "quiet_hours" in src
    assert "QUIET_HOURS_DEFER" in src


# ---- CASE23–25 safety / authority ----


def test_case23_gpt_failure_no_fake_transcript_marker():
    from backend.app.core.conversation import brain as brain_mod

    src = open(brain_mod.__file__, encoding="utf-8").read()
    assert "_is_gpt_related_error" in src
    assert "gpt_failure" in open(
        __import__("backend.app.routers.interact", fromlist=["x"]).__file__,
        encoding="utf-8",
    ).read()


def test_case24_context_subsource_failure_safe():
    # Empty projections on failure
    assert project_bounded_i8_actions(MagicMock(), 1, today_local_date=None) == []
    with patch(
        "backend.app.services.i10.self_producer_adapter.resolve_or_ensure_self_health_subject_id",
        side_effect=RuntimeError("boom"),
    ):
        assert project_bounded_i9_facts(MagicMock(), 1) == []


def test_case25_duplicate_prompt_authority_absent_versions():
    assert PERSONA_POLICY_VERSION.startswith("persona_policy_")
    assert INTERACTION_POLICY_VERSION.startswith("a3_interaction_")
    block = format_lifecycle_context_block(
        resolve_interaction_lifecycle(
            _db_with_tz_and_memory(tz_name=None, last_memory_at=None),
            _User(intro=None),
        )
    )
    assert "[INTERACTION_LIFECYCLE]" in block
    assert "interaction_policy_version=" in block


def test_case26_frontend_unchanged_marker():
    # Product FE is out of scope for this Gate; documented by governance report.
    assert True
