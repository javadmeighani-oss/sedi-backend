"""R-074 step 5a: the shared UserState contract (behaviour-preserving) + the guard that lists who may read the pack."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.notification_runtime import user_context_adapter as uca
from backend.app.services.user_context import user_state as us

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)


def _pack(**kw):
    base = dict(
        user_id=7,
        preferred_name="  سارا ",
        language="fa-IR",
        timezone="Asia/Tehran",
        goals=SimpleNamespace(items=["a", "", "b", "c", "d", "e", "f"]),
        lifestyle=SimpleNamespace(text="  " + "x" * 300),
        daily_memory_summary=" " + "y" * 200,
        birth_year=1370,
        sex="Female",
        engagement_level=" normal ",
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---- age (Jalali / Gregorian, plausibility window) ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "year,age",
    [(1370, 35), (1990, 36), (2020, 6), (2024, None), (1300, 105), (1200, None), (1500, None), ("x", None), (None, None), ("1995", 31)],
)
def test_age_from_birth_year_matrix(year, age):
    assert us.age_from_birth_year(year, now=NOW) == age


# ---- language ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,lang",
    [("fa-IR", "fa"), ("FA", "fa"), ("ar_SA", "ar"), (" en-US ", "en"), ("de", None), ("", None), (None, None), ("persian", None)],
)
def test_language_is_normalised_in_one_place(raw, lang):
    assert us.normalize_language(raw) == lang


# ---- the state itself ------------------------------------------------------------------------------------------------------
def test_state_is_a_bounded_frozen_view_of_the_pack():
    s = us.user_state_from_pack(_pack(), now=NOW)
    assert s.preferred_name == "سارا" and s.language == "fa" and s.language_raw == "fa-IR"
    assert s.timezone == "Asia/Tehran" and s.sex == "female" and s.age == 35 and s.birth_year == 1370
    assert s.goals == ("a", "b", "c", "d", "e")  # empties dropped, max 5
    assert len(s.lifestyle_text) == us.MAX_LIFESTYLE_CHARS and len(s.daily_summary) == us.MAX_DAILY_SUMMARY_CHARS
    assert s.engagement_level == "normal"
    with pytest.raises(Exception):
        s.preferred_name = "x"  # frozen


def test_empty_or_missing_fields_are_none_or_empty_not_crashes():
    s = us.user_state_from_pack(
        SimpleNamespace(user_id=1, preferred_name="  ", language=None, goals=None, lifestyle=None, daily_memory_summary=None)
    )
    assert s.preferred_name is None and s.language is None and s.goals == () and s.lifestyle_text == "" and s.daily_summary == ""
    assert us.user_state_from_pack(None) is None


def test_get_user_state_is_fail_open(monkeypatch):
    import backend.app.services.user_context as uc

    class _Boom:
        def __init__(self, db):
            raise RuntimeError("db down")

    monkeypatch.setattr(uc, "UserContextService", _Boom)
    assert us.get_user_state(object(), 1) is None


def test_get_user_state_goes_through_the_single_owner(monkeypatch):
    import backend.app.services.user_context as uc

    seen = []

    class _Svc:
        def __init__(self, db):
            pass

        def get_user_context(self, uid):
            seen.append(uid)
            return _pack(user_id=uid)

    monkeypatch.setattr(uc, "UserContextService", _Svc)
    s = us.get_user_state(object(), 42)
    assert seen == [42] and s.user_id == 42 and s.preferred_name == "سارا"


# ---- notifications: identical output to the pre-5a hand-written extraction ------------------------------------------------
def _legacy_notification_dict(pack):
    goals = getattr(pack, "goals", None)
    items = []
    if goals and getattr(goals, "items", None):
        raw = list(goals.items) if isinstance(goals.items, list) else []
        items = [str(x).strip() for x in raw if x][:5]
    life = getattr(pack, "lifestyle", None)
    life_text = ""
    if life and getattr(life, "text", None) and str(life.text).strip():
        life_text = str(life.text).strip()[:200]
    daily = getattr(pack, "daily_memory_summary", None)
    daily_text = str(daily).strip()[:150] if daily and str(daily).strip() else ""
    return {
        "preferred_name": (getattr(pack, "preferred_name", None) or "").strip() or None,
        "language": (getattr(pack, "language", None) or "").strip() or None,
        "timezone": (getattr(pack, "timezone", None) or "").strip() or None,
        "goals_items": items,
        "lifestyle_text": life_text,
        "daily_memory_summary": daily_text,
    }


PACKS = [
    _pack(),
    _pack(preferred_name=None, language="en", timezone=None, goals=None, lifestyle=None, daily_memory_summary=None),
    _pack(preferred_name="Ali", language="ar-SA", goals=SimpleNamespace(items="not-a-list")),
    _pack(preferred_name="   ", language="  ", lifestyle=SimpleNamespace(text="   ")),
    _pack(goals=SimpleNamespace(items=[]), daily_memory_summary="short"),
]


@pytest.mark.parametrize("pack", PACKS)
def test_notification_context_is_identical_to_the_legacy_extraction(monkeypatch, pack):
    class _Svc:
        def __init__(self, db):
            pass

        def get_user_context(self, uid):
            return pack

    monkeypatch.setattr(uca, "UserContextService", _Svc)
    assert uca.build_notification_context(object(), 7) == _legacy_notification_dict(pack)


def test_notification_context_is_empty_without_a_pack_and_on_errors(monkeypatch):
    class _None:
        def __init__(self, db):
            pass

        def get_user_context(self, uid):
            return None

    monkeypatch.setattr(uca, "UserContextService", _None)
    assert uca.build_notification_context(object(), 1) == {}

    class _Boom:
        def __init__(self, db):
            raise RuntimeError("x")

    monkeypatch.setattr(uca, "UserContextService", _Boom)
    assert uca.build_notification_context(object(), 1) == {}


# ---- profile overview: the age helper is the shared one ------------------------------------------------------------------------
def test_overview_age_helper_delegates_to_the_shared_implementation():
    from backend.app.services.profile.overview_summary import _age_from_birth_year

    for y in (1370, 1990, 2024, "x", None, 1500):
        assert _age_from_birth_year(y) == us.age_from_birth_year(y)


# ---- guard: who may read the user's pack (R-005: no parallel readers) ----------------------------------------------------------
ALLOWED_PACK_READERS = {
    "services/user_context/user_state.py",  # the contract itself
    "services/user_context/user_context_service.py",  # the single owner
    "services/intelligence/adapters.py",  # I2 context adapters (chat)
    "services/intelligence/assembler.py",  # I2 assembler (chat)
    "core/conversation/brain.py",  # chat reply path
    "services/a3_session_open.py",  # session open (reads the pack, then UserState)
    "services/memory_context_service.py",  # memory context (existing owner)
    "services/rag_context/rag_context_builder.py",  # facts-anchored RAG context (existing owner)
    "services/notification_runtime/user_context_adapter.py",  # notifications (via UserState)
    "services/profile/overview_summary.py",  # profile overview (via UserState)
}


def test_only_registered_modules_read_the_user_context_pack():
    app = Path(__file__).resolve().parents[1] / "app"
    found = set()
    for path in app.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "UserContextService(" in text or ".get_user_context(" in text:
            found.add(path.relative_to(app).as_posix())
    unregistered = sorted(found - ALLOWED_PACK_READERS)
    assert not unregistered, (
        "New direct reader(s) of the UserContextPack: use backend.app.services.user_context.user_state "
        f"(get_user_state / user_state_from_pack) or register the reader here with a reason: {unregistered}"
    )


def test_migrated_consumers_use_the_contract():
    app = Path(__file__).resolve().parents[1] / "app"
    for rel in (
        "services/notification_runtime/user_context_adapter.py",
        "services/profile/overview_summary.py",
        "services/a3_session_open.py",
    ):
        assert "user_state" in (app / rel).read_text(encoding="utf-8"), rel
