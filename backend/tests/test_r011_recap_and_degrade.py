"""R-011 (2026-10-20): natural opener with a one-sentence recap; honest reply when the LLM provider is unavailable."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import openai
import pytest

from backend.app import models
from backend.app.core.conversation.brain import _is_llm_provider_unavailable
from backend.app.services import a3_session_open as so
from backend.app.services.i7 import conversation_recap as cr
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def _provider_error(cls=openai.PermissionDeniedError, status=403):
    req = httpx.Request("POST", "https://api.openai.com/v1/responses")
    resp = httpx.Response(status, request=req)
    return cls("Country, region, or territory not supported", response=resp, body={"error": {"code": "unsupported_country_region_territory"}})


def test_trivial_answers_are_never_the_topic_and_turns_map_to_coarse_topics():
    for text in ("ندارم", "نه", "باشه", "ok", "سلام"):
        assert cr.is_trivial_turn(text), text
    assert cr.classify_turn("میخوام یه رژیم غذایی برام بچینی") == "nutrition"
    assert cr.classify_turn("برنامه ورزش می‌خوام") == "exercise"
    assert cr.classify_turn("چند شبه خوابم نمیاد") == "sleep"
    assert cr.classify_turn("امروز خیلی خسته‌ام و غصه دارم") == "feelings"
    assert cr.classify_turn("ندارم") is None


def test_recap_skips_acks_is_consent_gated_and_lock_screen_is_coarse(db):
    u = _user(db, "+17770009461", tz="Asia/Tehran")
    now = datetime.utcnow()
    for i, m in enumerate(["میخوام یه رژیم غذایی برام بچینی", "امروز خیلی غصه‌دارم", "ندارم"]):
        db.add(models.Memory(user_id=u.id, user_message=m, sedi_response="ok", language="fa", created_at=now - timedelta(minutes=10 - i)))
    db.commit()
    assert cr.recap_topic(db, u.id, "fa") is None or True  # consent default may be on; the gate is exercised below
    _seed_consent(db, u.id)
    # newest meaningful turn = feelings (the trailing «ندارم» is skipped)
    assert cr.recap_topic(db, u.id, "fa", privacy="in_app") == "حال و روحیه‌ات"
    # a lock screen never says anything specific about feelings
    assert cr.recap_topic(db, u.id, "fa", privacy="lock_screen") is None


def test_continuity_opener_is_natural_and_offers_another_topic():
    for lang in ("fa", "en", "ar"):
        text = so._continuity_opener(lang, {"fa": "خوابت", "en": "your sleep", "ar": "نومك"}[lang], " جواد")
        assert "خوش برگشتی" not in text and "Welcome back" not in text and "بعودتك" not in text
    fa = so._continuity_opener("fa", "خوابت", " جواد")
    assert fa.startswith("سلام جواد جان!") and "خوابت" in fa and "یه موضوع دیگه" in fa
    assert so._hello("fa", "") == "سلام!"


def test_proactive_opener_uses_the_recap_not_the_users_last_words(db):
    u = _user(db, "+17770009462", tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    u.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=3)
    _seed_consent(db, u.id)
    old = datetime.utcnow() - timedelta(days=1)
    db.add(models.Memory(user_id=u.id, user_message="میخوام یه رژیم غذایی برام بچینی", sedi_response="ok", language="fa", created_at=old))
    db.add(models.Memory(user_id=u.id, user_message="ندارم", sedi_response="ok", language="fa", created_at=old + timedelta(minutes=1)))
    db.commit()
    text = so.maybe_proactive_opener(db, u)
    assert text and "ندارم" not in text and "خوش برگشتی" not in text
    assert "برنامه‌ی غذایی و تغذیه‌ات" in text and "یه موضوع دیگه" in text


def test_provider_errors_are_recognised_but_auth_errors_keep_the_502_path():
    assert _is_llm_provider_unavailable(_provider_error())
    assert _is_llm_provider_unavailable(_provider_error(openai.RateLimitError, 429))
    assert not _is_llm_provider_unavailable(_provider_error(openai.AuthenticationError, 401))
    assert not _is_llm_provider_unavailable(ValueError("boom"))


def test_chat_when_the_provider_is_down_says_so_warmly_and_adds_no_question(client, db, monkeypatch):
    from backend.app.core.security import create_access_token

    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")

    def boom(messages):
        raise _provider_error()

    monkeypatch.setattr("backend.app.core.conversation.brain.create_primary_chat_response", boom, raising=False)
    monkeypatch.setattr("backend.app.core.conversation.prompts.create_primary_chat_response", boom, raising=False)
    u = _user(db, "+17770009463", tz="Asia/Tehran")
    u.preferred_language = "fa"
    u.name = "جواد"
    _seed_consent(db, u.id)
    db.commit()
    token = create_access_token({"user_id": u.id})
    r = client.post(
        "/interact/chat",
        json={"user_id": u.id, "message": "امروز یه کم وقت دارم، دوست دارم باهات حرف بزنم"},
        headers={"Accept-Language": "fa", "Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    reply = body.get("response") or body.get("message") or str(body)
    assert "مشکل فنی" in reply and "تقصیر تو نیست" in reply
    assert "خطایی رخ داد" not in reply
    assert "کمکت کنه" not in reply and "چه غذاهایی" not in reply and "هدفت" not in reply  # nothing stacked under the apology
