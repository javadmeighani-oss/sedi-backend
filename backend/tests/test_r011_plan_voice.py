"""R-011: the plan composer may use an LLM ONLY to re-voice rule-chosen items; safe fallback per item; default OFF."""
from __future__ import annotations

import json

import pytest

from backend.app.services.i8 import plan_composer as pc
from backend.app.services.i8 import plan_voice as pv
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

CAT = pc.catalog()


def _week(constraints=None):
    return pc.select_nutrition_week(constraints or pc.Constraints(), "seed-voice")


def _ids(week):
    return {e["item"]["id"] for d in week for e in d}


def test_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv(pv.ENV_FLAG, raising=False)
    assert pv.plan_voice_enabled() is False
    monkeypatch.setenv(pv.ENV_FLAG, "true")
    assert pv.plan_voice_enabled() is True


def test_validation_rejects_unsafe_voicing_and_keeps_safe_ones():
    base = {"a": "یه نون ساده بخور", "b": "یه ماست ساده بخور", "c": "یه سیب بخور"}
    c = pc.Constraints(allergens={"dairy"})
    voiced = {
        "a": "یه نون گرم با یه کم پنیر بخور تا حالت خوب بشه",       # re-adds an allergen-class ingredient
        "b": "یه ماست ساده با ۲۰۰ گرم میوه بخور و کیف کن",           # quantity
        "c": "یه سیب تازه و آبدار بخور؛ برای امروزت حسابی می‌چسبه",   # fine ("گرم" as warm must not trip the quantity rule)
        "zzz": "این شناسه وجود ندارد و باید حذف شود حتماً",
    }
    ok = pv.validate_voiced(base, voiced, c, CAT)
    assert set(ok) == {"c"}
    assert pv.validate_voiced(base, {"c": "x"}, c, CAT) == {}                       # too short
    assert pv.validate_voiced(base, {"c": "یه سیب بخور و ۳۰۰ کالری دریافت کن لطفاً"}, c, CAT) == {}
    assert pv.validate_voiced(base, {"c": "**یه سیب** بخور تا حالت خوب بشه عزیزم"}, c, CAT) == {}  # markdown


def test_voice_week_uses_llm_json_and_falls_back_on_garbage(monkeypatch):
    week = _week()
    ids = sorted(_ids(week))
    monkeypatch.setattr(pv, "_call_llm", lambda s, u: json.dumps({i: "برای تو و فقط تو، این رو با عشق بخور عزیزم" for i in ids}, ensure_ascii=False))
    voiced = pv.voice_week(week, "fa", pc.Constraints())
    assert set(voiced) == set(ids)
    monkeypatch.setattr(pv, "_call_llm", lambda s, u: "این اصلاً JSON نیست")
    assert pv.voice_week(week, "fa", pc.Constraints()) == {}

    def boom(s, u):
        raise RuntimeError("llm down")

    monkeypatch.setattr(pv, "_call_llm", boom)
    assert pv.voice_week(week, "fa", pc.Constraints()) == {}


def test_compose_uses_voice_only_when_enabled_and_never_calls_llm_when_off(db, monkeypatch):
    u = _user(db, "+17770009431", tz="Asia/Tehran")
    _seed_consent(db, u.id)

    def must_not_call(s, user):
        raise AssertionError("LLM must not be called while the flag is off")

    monkeypatch.delenv(pv.ENV_FLAG, raising=False)
    monkeypatch.setattr(pv, "_call_llm", must_not_call)
    off = pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=pc.Constraints(), persist=False)
    assert off.status == "ACTION_PERSISTED" and off.today

    marker = "این رو مخصوص خودت و با دلم چیدم"
    monkeypatch.setenv(pv.ENV_FLAG, "1")
    monkeypatch.setattr(pv, "_call_llm", lambda s, user: json.dumps({i: marker for i in CAT["texts"]}, ensure_ascii=False))
    on = pc.compose_week_plan(db, user_id=u.id, domain="nutrition", language="fa", constraints=pc.Constraints(), persist=False)
    assert on.today and all(marker in detail for (_s, _t, _title, detail) in on.today)
