"""R-054 / R-072: the raw text of every governed chat turn stays PERMANENTLY; smart recall only finds words and concepts in it.

Matrix: row states (governed / ineligible / legacy-expired), languages (recall), consent, ownership, ranking, limits, wiring.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app import models
from backend.app.services.i6.consent_service import revoke_memory_consent
from backend.app.services.i7 import recall
from backend.app.services.i7.governed_raw import try_durable_raw_write
from backend.app.services.i7.retention import RAW_VISIBLE_DAYS, is_raw_visible, query_eligible_raw
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

_NOW = datetime.now(timezone.utc)


def _turn(db, uid, days_ago, text, *, durable=True, retain_days=36500, minutes=0):
    at = _NOW - timedelta(days=days_ago, minutes=minutes)
    row = models.Memory(
        user_id=uid, user_message=text, sedi_response="باشه", language="fa", created_at=at.replace(tzinfo=None),
        retain_until=at + timedelta(days=retain_days), durable_write=durable,
    )
    db.add(row)
    db.commit()
    return row


def _filler(db, uid, n=12):
    """The latest turns are skipped by the recall (they already reach the model as history)."""
    for i in range(n):
        _turn(db, uid, 0, f"روز عادی شماره {i}", minutes=i + 1)


def _user_in(db, phone):
    u = _user(db, phone, tz="Asia/Tehran")
    _seed_consent(db, u.id)
    return u


# ---- permanence ---------------------------------------------------------------------------------------------------------
def test_a_governed_write_is_kept_for_about_a_hundred_years(db):
    u = _user_in(db, "+17770300001")
    res = try_durable_raw_write(db, user_id=u.id, user_message="سلام", sedi_response="سلام", actor_user_id=u.id, commit=True)
    assert RAW_VISIBLE_DAYS == 36500
    assert res.memory.retain_until.astimezone(timezone.utc) > _NOW + timedelta(days=36000)


@pytest.mark.parametrize("days_ago", [10, 45, 400, 2000])
def test_an_old_governed_turn_is_still_visible_even_when_its_retain_until_has_passed(db, days_ago):
    u = _user_in(db, f"+177703001{days_ago:04d}"[:13])
    row = _turn(db, u.id, days_ago, "قدیمی ولی ثبت‌شده", retain_days=30)  # the OLD 30-day stamp
    assert is_raw_visible(row) is True
    assert [r.id for r in query_eligible_raw(db, u.id)] == [row.id]


def test_ineligible_and_legacy_expired_rows_stay_hidden(db):
    u = _user_in(db, "+17770300002")
    _turn(db, u.id, 5, "نامعتبر", durable=False, retain_days=-1)  # marked ineligible
    _turn(db, u.id, 50, "قدیمی بدون حاکمیت", durable=False, retain_days=30)  # legacy ungoverned row, bound expired
    legacy_live = _turn(db, u.id, 1, "قدیمی ولی هنوز در بازه", durable=False, retain_days=30)
    assert [r.id for r in query_eligible_raw(db, u.id)] == [legacy_live.id]


# ---- recall -------------------------------------------------------------------------------------------------------------
_CASES = [
    ("fa", "من از ماه پیش بی‌خوابی دارم و قرص خواب نمی‌خورم", "درباره‌ی بی‌خوابی‌ام امشب دوباره حرف بزنیم"),
    ("en", "My knee hurts every time I climb the stairs at work", "my knee again today after the stairs"),
    ("ar", "أعاني من صداع نصفي كل أسبوع تقريبا", "الصداع النصفي عاد اليوم"),
]


@pytest.mark.parametrize("lang,old,query", _CASES)
def test_the_day_the_user_said_it_is_recalled_by_its_words_in_every_language(db, lang, old, query):
    u = _user_in(db, f"+17770301{_CASES.index((lang, old, query))}00")
    _turn(db, u.id, 40, old)
    _turn(db, u.id, 33, "امروز هوا خوب بود و قدم زدم")
    _turn(db, u.id, 20, "درباره‌ی یک فیلم صحبت کردیم")
    _filler(db, u.id)
    found = recall.recall_snippets(db, u.id, query)
    assert found and found[0]["text"] == old
    assert found[0]["day"]  # the user's local day of that turn
    block = recall.build_recall_block(db, u.id, query, lang)
    assert block.startswith("[MEMORY_RECALL]") and old in block


def test_the_rarer_the_shared_word_the_better_the_match(db):
    u = _user_in(db, "+17770302001")
    _turn(db, u.id, 30, "قرص فشار خونم را سر وقت می‌خورم")
    _turn(db, u.id, 29, "قرص ویتامین هم می‌خورم")
    _turn(db, u.id, 28, "قرص آهن هم گاهی می‌خورم")
    _filler(db, u.id)
    found = recall.recall_snippets(db, u.id, "فشار خونم امروز بالا بود")
    assert found and "فشار" in found[0]["text"]


def test_a_single_common_word_is_not_a_memory(db):
    u = _user_in(db, "+17770302002")
    for d in range(30, 20, -1):
        _turn(db, u.id, d, f"امروز {d} با دوستم رفتم بیرون")
    _filler(db, u.id)
    assert recall.recall_snippets(db, u.id, "بیرون") == []  # one word shared by many days says nothing


def test_one_rare_long_word_is_enough(db):
    u = _user_in(db, "+17770302003")
    _turn(db, u.id, 25, "پزشکم گفت گواتر دارم")
    for d in range(24, 14, -1):
        _turn(db, u.id, d, f"روز عادی {d}")
    _filler(db, u.id)
    found = recall.recall_snippets(db, u.id, "گواتر")
    assert found and "گواتر" in found[0]["text"]


def test_the_latest_turns_are_never_recalled_they_are_already_history(db):
    u = _user_in(db, "+17770302004")
    for i in range(6):
        _turn(db, u.id, 0, f"دیابت مادرم نگرانم می‌کند {i}", minutes=i + 1)
    assert recall.recall_snippets(db, u.id, "دیابت مادرم") == []


def test_no_content_word_means_no_recall(db):
    u = _user_in(db, "+17770302005")
    _turn(db, u.id, 30, "دیابت دارم")
    _filler(db, u.id)
    for message in ("", "سلام", "?", "و در به", "the and of"):
        assert recall.recall_snippets(db, u.id, message) == []


def test_at_most_three_snippets_and_never_the_same_text_twice(db):
    u = _user_in(db, "+17770302006")
    for d in range(30, 20, -1):
        _turn(db, u.id, d, "دیابت مادرم و نگرانی من از آینده")
    for d in (19, 18, 17, 16):
        _turn(db, u.id, d, f"دیابت مادرم در روز {d} بهتر شد و خوشحال شدم")
    _filler(db, u.id)
    found = recall.recall_snippets(db, u.id, "دیابت مادرم چطور بود")
    assert len(found) == 3 and len({f["text"] for f in found}) == 3


def test_a_long_turn_is_cut_to_a_short_snippet(db):
    u = _user_in(db, "+17770302007")
    _turn(db, u.id, 30, "دیابت مادرم " + "و خیلی چیزهای دیگر " * 40)
    _filler(db, u.id)
    found = recall.recall_snippets(db, u.id, "دیابت مادرم")
    assert found and len(found[0]["text"]) <= recall.MAX_SNIPPET_CHARS


def test_nobody_elses_words_are_ever_recalled(db):
    mine = _user_in(db, "+17770303001")
    other = _user_in(db, "+17770303002")
    _turn(db, other.id, 30, "راز دیگری درباره‌ی دیابت مادرم")
    _filler(db, mine.id)
    _filler(db, other.id)
    assert recall.recall_snippets(db, mine.id, "دیابت مادرم") == []


def test_without_memory_read_permission_nothing_is_recalled(db):
    u = _user_in(db, "+17770303003")
    _turn(db, u.id, 30, "دیابت مادرم نگرانم می‌کند")
    _filler(db, u.id)
    assert recall.recall_snippets(db, u.id, "دیابت مادرم")
    revoke_memory_consent(db, u.id, commit=True)
    assert recall.recall_snippets(db, u.id, "دیابت مادرم") == [] and recall.build_recall_block(db, u.id, "دیابت مادرم") is None


def test_an_ineligible_turn_is_never_recalled(db):
    u = _user_in(db, "+17770303004")
    _turn(db, u.id, 30, "دیابت مادرم نگرانم می‌کند", durable=False, retain_days=-1)
    _filler(db, u.id)
    assert recall.recall_snippets(db, u.id, "دیابت مادرم") == []


def test_a_failure_inside_the_recall_is_swallowed(db, monkeypatch):
    u = _user_in(db, "+17770303005")

    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr("backend.app.services.i7.retention.query_eligible_raw", boom)
    assert recall.recall_snippets(db, u.id, "دیابت مادرم نگرانم") == []


# ---- wiring -------------------------------------------------------------------------------------------------------------
def test_the_brain_adds_the_recall_block_before_the_history():
    brain = (Path(__file__).resolve().parents[1] / "app" / "core" / "conversation" / "brain.py").read_text(encoding="utf-8")
    assert "build_recall_block(self.db, user_id, user_message, lang)" in brain
    assert brain.index("build_recall_block(") < brain.index("_append_recent_history(messages, self.memory, user_id, limit=8)")
