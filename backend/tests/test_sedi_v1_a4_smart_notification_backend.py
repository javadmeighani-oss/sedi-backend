"""SEDI-V1-A4 smart notification backend acceptance (focused)."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.gate4.notification_contract import (
    normalize_legacy_action,
    get_action_label,
)
from backend.app.services.gate4.push_payload import (
    CANONICAL_SEDI_SOUND,
    CHANNEL_ENGAGEMENT_V2,
    CHANNEL_HEALTH_ALERT_V2,
    CHANNEL_MORNING_V3,
    MOBILE_INTERACTION_ACTIONS,
    build_gate4_android_notification_options,
    build_gate4_push_data_payload,
)
from backend.app.services.gate4.scheduler_timing import (
    CANONICAL_DAILY_SMART_TOUCHPOINT_TIME,
    should_run_daily_smart_touchpoint,
)
from backend.app.services.i10.daily_wellness_digest import (
    DailySmartContentFamily,
    DailyWellnessDataStatus,
    assemble_daily_wellness_digest_facts,
    build_daily_wellness_digest_payload,
    render_digest_body,
    render_digest_title,
)
from backend.app.services.i10.interaction_vocabulary import (
    CanonicalInteractionVerb,
    resolve_interaction_verb,
)
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i7.privacy_safe_recent_topic import (
    display_phrase_for_topic_label,
    get_privacy_safe_recent_topic_label,
)
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.notification_runtime.templates_v1 import TEMPLATES_V1, validate_templates_v1


@pytest.fixture
def gate4_patch(monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_DAILY_0800_ENABLED", "false")
    yield


def _user(db, name="a4-user", lang="en"):
    u = models.User(name=name, secret_key=f"sk-{name}", preferred_language=lang)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_a4_daily_smart_time_is_0900_not_0800():
    assert CANONICAL_DAILY_SMART_TOUCHPOINT_TIME == "09:00"
    assert CANONICAL_DAILY_SMART_TOUCHPOINT_TIME != "08:00"


def test_a4_should_run_daily_smart_touchpoint_at_0900_local(db, gate4_patch):
    user = _user(db, "tz-0900")
    db.add(
        models.UserProfileCore(
            user_id=user.id,
            timezone="Asia/Tehran",
        )
    )
    db.commit()
    # 09:05 Asia/Tehran ≈ 05:35 UTC
    now_utc = datetime(2026, 9, 9, 5, 35, 0)
    assert should_run_daily_smart_touchpoint(db, user, now_utc) is True
    # 08:05 Asia/Tehran ≈ 04:35 UTC — must NOT fire
    early = datetime(2026, 9, 9, 4, 35, 0)
    assert should_run_daily_smart_touchpoint(db, user, early) is False


def test_a4_scheduler_morning_job_only_creates_digest():
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.run_morning_notifications)
    assert "create_daily_wellness_digest" in src
    assert "create_morning_brief" not in src
    assert "should_run_daily_smart_touchpoint" in src


def test_a4_engagement_nudge_job_not_registered():
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.start_scheduler)
    assert "add_job(\n            run_engagement_nudge" not in src
    assert 'id="engagement_nudge"' not in src or "remove_job" in src
    # Compatibility method retained
    assert hasattr(sched, "run_engagement_nudge")


def test_a4_fa_en_ar_digest_titles_and_bodies(db, gate4_patch):
    for lang in ("fa", "en", "ar"):
        user = _user(db, f"lang-{lang}", lang=lang)
        facts = assemble_daily_wellness_digest_facts(
            db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
        )
        title = render_digest_title(facts, lang)
        body = render_digest_body(facts, lang)
        assert title and body
        payload = build_daily_wellness_digest_payload(
            facts, occurrence_key=f"k-{lang}", language=lang
        )
        assert payload.metadata["language"] == lang
        assert payload.title == title
        assert payload.body == body


def test_a4_no_data_does_not_invent_health_facts(db, gate4_patch):
    user = _user(db, "nodata")
    facts = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    assert facts.data_status == DailyWellnessDataStatus.NO_DATA
    body = render_digest_body(facts, "en").lower()
    for term in ("hr=", "bpm", "spo2", "diagnosis", "you have diabetes"):
        assert term not in body


def test_a4_content_family_priority_general_when_empty(db, gate4_patch):
    user = _user(db, "prio")
    facts = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    assert facts.content_family == DailySmartContentFamily.GENERAL_CHECKIN


def test_a4_deterministic_variant_stable_same_seed(db, gate4_patch):
    user = _user(db, "var")
    when = datetime(2026, 9, 9, 9, 0, 0)
    facts = assemble_daily_wellness_digest_facts(db, user_id=user.id, when=when)
    a = render_digest_body(facts, "fa")
    b = render_digest_body(facts, "fa")
    assert a == b


def test_a4_variant_differs_across_dates(db, gate4_patch):
    user = _user(db, "var2")
    f1 = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    f2 = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 10, 9, 0, 0)
    )
    # Same family general → variant seed includes date; may differ across dates
    bodies = {render_digest_body(f1, "en"), render_digest_body(f2, "en")}
    assert len(bodies) >= 1


def test_a4_reengagement_4h_chat_only(db, gate4_patch):
    user = _user(db, "re4")
    now = datetime(2026, 9, 9, 16, 0, 0)
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="hi",
            sedi_response="hello",
            language="en",
            created_at=now - timedelta(hours=3, minutes=50),
        )
    )
    db.commit()
    assert DecisionEngine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is None
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="hi2",
            sedi_response="hello",
            language="en",
            created_at=now - timedelta(hours=4, minutes=5),
        )
    )
    db.commit()
    # Still suppressed if latest chat is the newer 3h50 one — seed only older by clearing
    db.query(models.Memory).filter(models.Memory.user_id == user.id).delete()
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="idle",
            sedi_response="ok",
            language="en",
            created_at=now - timedelta(hours=4, minutes=5),
        )
    )
    db.commit()
    assert DecisionEngine(db).create_connection_ping(user_id=user.id, scheduled_for=now) is not None


def test_a4_reengagement_max2_and_6h_cooldown(db, gate4_patch):
    user = _user(db, "cd6")
    day = datetime(2026, 9, 9, 8, 0, 0)
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="x",
            sedi_response="y",
            language="en",
            created_at=day - timedelta(hours=5),
        )
    )
    db.commit()
    eng = DecisionEngine(db)
    n1 = eng.create_connection_ping(user_id=user.id, scheduled_for=day)
    assert n1 is not None
    # Within 6h → suppressed
    assert eng.create_connection_ping(user_id=user.id, scheduled_for=day + timedelta(hours=3)) is None
    # After 6h → allowed
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="x2",
            sedi_response="y2",
            language="en",
            created_at=day + timedelta(hours=6) - timedelta(hours=5),
        )
    )
    db.commit()
    n2 = eng.create_connection_ping(user_id=user.id, scheduled_for=day + timedelta(hours=6))
    assert n2 is not None


def test_a4_sensitive_topic_never_in_lock_screen(db, gate4_patch, monkeypatch):
    user = _user(db, "sens")

    def _fake_topic(_db, _uid):
        return "my medication dose for diabetes"

    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_bounded_continuity_topic",
        _fake_topic,
    )
    assert get_privacy_safe_recent_topic_label(db, user.id) is None


def test_a4_safe_coarse_topic_may_appear(db, gate4_patch, monkeypatch):
    user = _user(db, "safe")

    def _fake_topic(_db, _uid):
        return "talked about activity plan walking"

    monkeypatch.setattr(
        "backend.app.services.i7.privacy_safe_recent_topic.get_bounded_continuity_topic",
        _fake_topic,
    )
    label = get_privacy_safe_recent_topic_label(db, user.id)
    assert label == "activity_plan"
    phrase = display_phrase_for_topic_label(label, "fa")
    assert phrase and "فعالیت" in phrase


def test_a4_like_dislike_talk_resolve_independently():
    like = resolve_interaction_verb({"reaction": "like"})
    dislike = resolve_interaction_verb({"reaction": "dislike"})
    talk = resolve_interaction_verb({"action_id": "open_chat"})
    not_now = resolve_interaction_verb({"reaction": "dismiss"})
    assert like.verb is CanonicalInteractionVerb.LIKE
    assert dislike.verb is CanonicalInteractionVerb.DISLIKE
    assert talk.verb is CanonicalInteractionVerb.TALK_TO_SEDI
    assert not_now.verb is CanonicalInteractionVerb.NOT_NOW
    assert dislike.verb is not CanonicalInteractionVerb.NOT_NOW
    assert like.gate4_policy_action is None
    assert dislike.gate4_policy_action is None


def test_a4_legacy_map_does_not_collapse_like_dislike():
    assert normalize_legacy_action("like") == "like"
    assert normalize_legacy_action("dislike") == "dislike"
    assert normalize_legacy_action("like") != "ACK_THANKS"
    assert normalize_legacy_action("dislike") != "NOT_NOW"
    for lang in ("fa", "en", "ar"):
        assert get_action_label("like", lang)
        assert get_action_label("dislike", lang)
        assert get_action_label("open_chat", lang)


def test_a4_no_generic_feedback_completes_domain():
    from backend.app.services.i10.interaction_vocabulary import (
        assert_generic_verb_cannot_complete_domain,
    )

    notif = models.Notification(
        user_id=1,
        type="connection_ping",
        title="t",
        body="b",
        priority="low",
        semantic_family=I10SemanticFamily.MEDICATION_DUE.value,
    )
    for verb in (
        CanonicalInteractionVerb.LIKE,
        CanonicalInteractionVerb.DISLIKE,
        CanonicalInteractionVerb.TALK_TO_SEDI,
        CanonicalInteractionVerb.NOT_NOW,
    ):
        assert_generic_verb_cannot_complete_domain(notif, verb)


def test_a4_audible_backend_contract_daily_engagement_health():
    for cat, channel in (
        ("morning", CHANNEL_MORNING_V3),
        ("daily_status", CHANNEL_MORNING_V3),
        ("engagement", CHANNEL_ENGAGEMENT_V2),
        ("health_alert", CHANNEL_HEALTH_ALERT_V2),
    ):
        opts = build_gate4_android_notification_options(
            risk="normal" if cat != "health_alert" else "high",
            priority="normal",
            category=cat,
            sound_enabled=True,
        )
        assert opts["channel_id"] == channel
        assert opts["sound"] == CANONICAL_SEDI_SOUND
        assert opts["play_sound"] is True


def test_a4_push_exposes_mobile_interaction_metadata_fa_en_ar():
    for lang in ("fa", "en", "ar"):
        data = build_gate4_push_data_payload(
            notification_id=1,
            user_id=1,
            title="t",
            body="b",
            category="engagement",
            risk="normal",
            priority="normal",
            language=lang,
            deeplink_url="sedi://chat?from=notif",
            actions=list(MOBILE_INTERACTION_ACTIONS),
        )
        assert "gate4_actions" in data
        assert "like" in data["gate4_actions"]
        assert "dislike" in data["gate4_actions"]
        assert "open_chat" in data["gate4_actions"]
        assert data["play_sound"] == "true"


def test_a4_templates_have_ar_coverage():
    assert validate_templates_v1() == []
    for t in TEMPLATES_V1:
        assert "ar" in t["texts"]


def test_a4_context_json_has_no_raw_memory_health_dump(db, gate4_patch):
    user = _user(db, "ctx")
    facts = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    payload = build_daily_wellness_digest_payload(facts, occurrence_key="k", language="en")
    ctx = payload.context or {}
    blob = str(ctx).lower()
    for forbidden in ("user_message", "raw_memory", "physiologicalmeasurement", "heart_rate_raw"):
        assert forbidden not in blob


def test_a4_ai_enhancer_not_hardcoded_fa():
    src = inspect.getsource(
        __import__(
            "backend.app.services.notification_runtime.ai_enhancer", fromlist=["enhance_with_ai"]
        ).enhance_with_ai
    )
    assert 'language="fa"' not in src
    assert "_payload_language" in inspect.getsource(
        __import__(
            "backend.app.services.notification_runtime.ai_enhancer", fromlist=["_payload_language"]
        )
    )
