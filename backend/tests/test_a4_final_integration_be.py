"""A4 final BE integration — canonical daily copy, AI gate, producer, A3 opener."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.a3_session_open import build_notification_origin_opener
from backend.app.services.i10.daily_wellness_digest import (
    DailySmartContentFamily,
    _GENERAL_CHECKIN_BODIES,
    _GENERAL_CHECKIN_TITLES,
    assemble_daily_wellness_digest_facts,
    build_daily_wellness_digest_payload,
    render_digest_body,
    render_digest_title,
)
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.notification_engine import DecisionEngine
from backend.app.services.notification_runtime.ai_enhancer import (
    enhance_with_ai,
    _is_canonical_v1_push,
)
from backend.app.services.notification_runtime.renderer import render
from backend.app.schemas.notification import NotificationPayload


def _user(db, name: str, lang: str = "fa") -> models.User:
    u = models.User(name=name, secret_key=f"sk-{name}", preferred_language=lang)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(models.UserProfileCore(user_id=u.id, timezone="Asia/Tehran"))
    db.commit()
    return u


def test_exact_approved_fa_daily_general_copy(db):
    user = _user(db, "fa-copy", lang="fa")
    facts = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    assert facts.content_family == DailySmartContentFamily.GENERAL_CHECKIN
    assert render_digest_title(facts, "fa") == "پیگیری روزانه صدی"
    assert (
        render_digest_body(facts, "fa")
        == "یک لمس آرام برای امروز. هر وقت آماده بودی با صدی ادامه بده."
    )
    payload = build_daily_wellness_digest_payload(
        facts, occurrence_key="k-fa", language="fa"
    )
    assert payload.title == "پیگیری روزانه صدی"
    assert payload.body == _GENERAL_CHECKIN_BODIES["fa"]


def test_deterministic_en_ar_general_equivalents(db):
    user = _user(db, "en-ar", lang="en")
    facts = assemble_daily_wellness_digest_facts(
        db, user_id=user.id, when=datetime(2026, 9, 9, 9, 0, 0)
    )
    assert render_digest_title(facts, "en") == _GENERAL_CHECKIN_TITLES["en"]
    assert render_digest_body(facts, "en") == _GENERAL_CHECKIN_BODIES["en"]
    assert render_digest_title(facts, "ar") == _GENERAL_CHECKIN_TITLES["ar"]
    assert render_digest_body(facts, "ar") == _GENERAL_CHECKIN_BODIES["ar"]
    # Stable across re-render
    assert render_digest_body(facts, "en") == render_digest_body(facts, "en")


def test_no_old_pet_name_closeness_emoji_in_active_v1_paths():
    from backend.app.services.notification_runtime import renderer as rend
    from backend.app.services.notification_runtime import fallback_generator as fb
    from backend.app.services.i10 import daily_wellness_digest as dig

    forbidden = ("عزیزم", "dear", "عزيزي", "🌅", "🌿", "💚", "دلم برات تنگ", "thinking of you")
    blobs = [
        inspect.getsource(rend._engagement_short),
        inspect.getsource(rend._engagement_with_topic),
        inspect.getsource(rend._morning_greeting),
        inspect.getsource(fb._generate_connection_ping),
        dig._GENERAL_CHECKIN_TITLES["fa"] + dig._GENERAL_CHECKIN_BODIES["fa"],
        dig._GENERAL_CHECKIN_TITLES["en"] + dig._GENERAL_CHECKIN_BODIES["en"],
    ]
    for blob in blobs:
        for bad in forbidden:
            assert bad not in blob, bad

    rendered = render("engagement", "fa", {"name": None}, "low")
    for bad in ("عزیزم", "🌿", "🌅"):
        assert bad not in rendered["title"]
        assert bad not in rendered["body"]


def test_freeform_ai_disabled_for_canonical_v1_even_if_env_true(monkeypatch):
    monkeypatch.setenv("NOTIF_AI_ENHANCE", "true")
    import importlib
    import backend.app.services.notification_runtime.ai_enhancer as ai

    importlib.reload(ai)
    assert ai.NOTIF_AI_ENHANCE is True

    payload = NotificationPayload(
        user_id=1,
        type="connection_ping",
        title="Hello from Sedi",
        body="How are you?",
        priority="low",
        metadata={"language": "en"},
    )
    assert ai._is_canonical_v1_push(payload) is True

    with patch(
        "backend.app.core.ai_text_engine.generate_notification_text",
        return_value="AI REWRITE SHOULD NOT APPLY 🌿 عزیزم",
    ) as mock_gen:
        out = ai.enhance_with_ai(payload)
        mock_gen.assert_not_called()
    assert out.body == "How are you?"
    assert out.title == "Hello from Sedi"

    digest = NotificationPayload(
        user_id=1,
        type="health_alert",
        title="Daily Sedi check-in",
        body=_GENERAL_CHECKIN_BODIES["en"],
        priority="normal",
        metadata={"language": "en", "alert_code": "daily_wellness_digest"},
        template_key="daily_wellness_digest",
    )
    assert ai._is_canonical_v1_push(digest) is True
    with patch(
        "backend.app.core.ai_text_engine.generate_notification_text",
        return_value="SHOULD NOT",
    ) as mock_gen:
        out2 = ai.enhance_with_ai(digest)
        mock_gen.assert_not_called()
    assert out2.body == _GENERAL_CHECKIN_BODIES["en"]

    # Restore module defaults for other tests
    monkeypatch.setenv("NOTIF_AI_ENHANCE", "false")
    importlib.reload(ai)


def test_daily_scheduler_only_digest_not_legacy_morning():
    from backend.app.core import scheduler as sched

    src = inspect.getsource(sched.run_morning_notifications)
    assert "create_daily_wellness_digest" in src
    assert "create_morning_brief" not in src
    start = inspect.getsource(sched.start_scheduler)
    assert 'id="engagement_nudge"' not in start or "remove_job" in start
    assert "add_job(\n            run_engagement_nudge" not in start


def test_daily_once_per_local_day_and_reengagement_contract(db):
    user = _user(db, "once-day", lang="en")
    when = datetime(2026, 9, 9, 5, 30, 0)  # ~09:00 Asia/Tehran
    eng = DecisionEngine(db)
    n1 = eng.create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert n1 is not None
    n2 = eng.create_daily_wellness_digest(user_id=user.id, scheduled_for=when)
    assert n2 is None  # occurrence / intake dedupe

    # Reengagement: need chat baseline idle >=4h
    now = datetime(2026, 9, 9, 16, 0, 0)
    db.add(
        models.Memory(
            user_id=user.id,
            user_message="hi",
            sedi_response="hello",
            language="en",
            created_at=now - timedelta(hours=5),
        )
    )
    db.commit()
    p1 = eng.create_connection_ping(user_id=user.id, scheduled_for=now)
    assert p1 is not None
    # Within 6h sibling cooldown
    assert eng.create_connection_ping(user_id=user.id, scheduled_for=now + timedelta(hours=3)) is None


def test_a3_daily_opener_safe_no_raw_body(db):
    user = _user(db, "opener", lang="fa")
    notif = models.Notification(
        user_id=user.id,
        type="health_alert",
        title="پیگیری روزانه صدی",
        body="RAW BODY MUST NOT APPEAR IN OPENER",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
        semantic_family=I10SemanticFamily.DAILY_WELLNESS_DIGEST.value,
        template_key="daily_wellness_digest",
        context_json='{"secret":"no-inject"}',
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    opener = build_notification_origin_opener(
        db, user, notif, language="fa", preferred_name=None
    )
    assert "پیگیری روزانه صدی" in opener or "آماده‌ای" in opener
    assert "RAW BODY" not in opener
    assert "no-inject" not in opener
    assert "عزیزم" not in opener
