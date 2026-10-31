"""R-044 principle 1: the serving text guard keeps junk out of what the chat receives (pure unit tests)."""

from __future__ import annotations

import pytest

from backend.app.services.scis.serving_text_guard import (
    is_internal_tag,
    is_servable_text,
    looks_like_navigation,
    pick_servable_statement,
)

# Real samples from the 2026-10-31 production audit (public official text only).
NAV_DEPRESSION = (
    "depression in adults diagnosis - depression in adults treatment - depression in adults living with - "
    "depression in adults causes - depression in adults symptoms"
)
NAV_DENTAL = (
    "Oral Hygiene: Overview Helpful Tips Additional Resources Related Publications On this page "
    "1 - Overview 2 - Helpful Tips"
)
GOOD_PANIC = (
    "Panic disorder — What to do during a panic attack: The next time you feel a panic attack coming, try to "
    "breathe slowly and tell yourself it will pass."
)
GOOD_BREATHING = (
    "Breathing exercises for stress: This calming breathing technique for stress, anxiety and panic can be done "
    "anywhere, sitting or standing. Breathe in gently through your nose for five seconds."
)
GOOD_WITH_DASH = (
    "Cognitive behavioural therapy (CBT) is a type of talking therapy - it helps you manage problems by changing "
    "the way you think and behave. It is most commonly used to treat anxiety and depression."
)


@pytest.mark.parametrize(
    "text",
    [
        "candidate_only_not_approved_knowledge",
        "  Candidate_Only_Not_Approved_Knowledge  ",
        "candidate_only_not_approved_knowledge, section",
        "some_internal_tag_name",
    ],
)
def test_internal_tags_are_never_served(text):
    assert is_internal_tag(text)
    assert not is_servable_text(text)


@pytest.mark.parametrize("text", [NAV_DEPRESSION, NAV_DENTAL])
def test_navigation_lists_are_never_served(text):
    assert looks_like_navigation(text)
    assert not is_servable_text(text)


@pytest.mark.parametrize("text", ["", "   ", None, "Stress", "Panic disorder", "Causes of stress"])
def test_empty_and_heading_only_texts_are_not_served(text):
    assert not is_servable_text(text)


@pytest.mark.parametrize("text", [GOOD_PANIC, GOOD_BREATHING, GOOD_WITH_DASH])
def test_real_knowledge_is_kept(text):
    assert is_servable_text(text)
    assert not looks_like_navigation(text)
    assert not is_internal_tag(text)


def test_a_single_dash_in_prose_is_not_navigation():
    assert not looks_like_navigation(GOOD_WITH_DASH)


def test_persian_and_arabic_prose_is_kept():
    assert is_servable_text("برای کاهش استرس هر روز چند دقیقه تنفس آرام تمرین کنید. این کار به آرام شدن کمک می‌کند.")
    assert is_servable_text("يساعد التنفس البطيء على تهدئة الجسم عند التوتر. جرّب ذلك لبضع دقائق كل يوم.")


def test_pick_prefers_the_chunk_then_falls_back_to_the_unit_statement():
    assert pick_servable_statement(GOOD_PANIC, GOOD_BREATHING) == GOOD_PANIC
    assert pick_servable_statement("candidate_only_not_approved_knowledge", GOOD_BREATHING) == GOOD_BREATHING
    assert pick_servable_statement(NAV_DEPRESSION, None, GOOD_PANIC) == GOOD_PANIC


def test_pick_returns_none_when_nothing_is_fit():
    assert pick_servable_statement("candidate_only_not_approved_knowledge", NAV_DEPRESSION, "Stress") is None
    assert pick_servable_statement() is None
