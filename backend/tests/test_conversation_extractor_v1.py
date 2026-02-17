"""
Unit tests for Conversation Extraction V1 (knowledge/conversation_extractor_v1).
"""

import pytest

from backend.app.services.knowledge.conversation_extractor_v1 import (
    extract_candidates,
    ExtractedCandidate,
    _normalize_token,
    _unicode_normalize_pass,
)


def test_sleep_quality_poor():
    """خوابم بد بود => sleep_quality poor, conf>=0.85"""
    result = extract_candidates("خوابم بد بود", "fa")
    assert len(result) >= 1
    sleep = next((c for c in result if c.fact_key == "sleep_quality" and c.fact_value == "poor"), None)
    assert sleep is not None
    assert sleep.confidence >= 0.85


def test_daily_walk_half_hour():
    """روزانه نیم ساعت پیاده‌روی می‌کنم => daily_walk_minutes=30, conf>=0.85"""
    result = extract_candidates("روزانه نیم ساعت پیاده‌روی می‌کنم", "fa")
    assert len(result) >= 1
    walk = next((c for c in result if c.fact_key == "daily_walk_minutes"), None)
    assert walk is not None
    assert walk.fact_value == 30
    assert walk.confidence >= 0.85


def test_medications_metformin():
    """دارم متفورمین می‌خورم => medications includes متفورمین, conf>=0.70"""
    result = extract_candidates("دارم متفورمین می‌خورم", "fa")
    assert len(result) >= 1
    med = next((c for c in result if c.fact_key == "medications"), None)
    assert med is not None
    assert "متفورمین" in str(med.fact_value)
    assert med.confidence >= 0.70


def test_stress_high():
    """استرس دارم => stress_level high, conf>=0.80"""
    result = extract_candidates("استرس دارم", "fa")
    assert len(result) >= 1
    stress = next((c for c in result if c.fact_key == "stress_level" and c.fact_value == "high"), None)
    assert stress is not None
    assert stress.confidence >= 0.80


def test_stress_low():
    """استرس ندارم => stress_level low"""
    result = extract_candidates("استرس ندارم", "fa")
    assert len(result) >= 1
    stress = next((c for c in result if c.fact_key == "stress_level" and c.fact_value == "low"), None)
    assert stress is not None


def test_daily_walk_minutes_regex():
    """۴۵ دقیقه پیاده => daily_walk_minutes=45"""
    result = extract_candidates("هر روز ۴۵ دقیقه پیاده میرم", "fa")
    assert len(result) >= 1
    walk = next((c for c in result if c.fact_key == "daily_walk_minutes"), None)
    assert walk is not None
    assert walk.fact_value == 45


def test_empty_text_returns_empty():
    result = extract_candidates("", "fa")
    assert result == []


def test_stopword_هم_does_not_create_medication_candidate():
    """Message containing only stopword 'هم' as medication token must not create a candidate."""
    result = extract_candidates("دارم هم می‌خورم", "fa")
    meds = [c for c in result if c.fact_key == "medications"]
    assert len(meds) == 0, "stopword 'هم' must not become a medications candidate"


def test_message_only_stopwords_creates_no_candidates():
    """Message that is only stopwords (e.g. 'هم') creates no candidates."""
    result = extract_candidates("هم", "fa")
    assert result == []


def test_medications_persian_past_خوردم():
    """امروز متفورمین خوردم => medications with متفورمین, conf>=0.70"""
    result = extract_candidates("امروز متفورمین خوردم", "fa")
    meds = [c for c in result if c.fact_key == "medications"]
    assert len(meds) >= 1
    med = next((c for c in meds if "متفورمین" in str(c.fact_value)), None)
    assert med is not None
    assert med.confidence >= 0.70


def test_medications_persian_past_مصرف_کردم():
    """متفورمین مصرف کردم => medications with متفورمین, conf>=0.70"""
    result = extract_candidates("متفورمین مصرف کردم", "fa")
    meds = [c for c in result if c.fact_key == "medications"]
    assert len(meds) >= 1
    med = next((c for c in meds if "متفورمین" in str(c.fact_value)), None)
    assert med is not None
    assert med.confidence >= 0.70


def test_medications_arabic_اتناول():
    """أنا أتناول metformin => medications containing metformin, conf>=0.70"""
    result = extract_candidates("أنا أتناول metformin", "ar")
    meds = [c for c in result if c.fact_key == "medications"]
    assert len(meds) >= 1
    med = next((c for c in meds if "metformin" in str(c.fact_value).lower()), None)
    assert med is not None
    assert med.confidence >= 0.70


def test_medications_arabic_أخذت():
    """أخذت فيتامين D => medications includes فيتامين (or related token), conf>=0.70"""
    result = extract_candidates("أخذت فيتامين D", "ar")
    meds = [c for c in result if c.fact_key == "medications"]
    assert len(meds) >= 1
    med = meds[0]
    assert "فيتامين" in str(med.fact_value)
    assert med.confidence >= 0.70


# --- Unicode normalization (Arabic yeh/kaf, diacritics, tatweel) ---


def test_unicode_normalize_arabic_yeh_to_persian():
    """Arabic yeh ي (U+064A) normalizes to Persian ی (U+06CC)."""
    assert _unicode_normalize_pass("\u064A") == "\u06CC"
    assert _unicode_normalize_pass("في") == "فی"


def test_unicode_normalize_arabic_kaf_to_persian():
    """Arabic kaf ك (U+0643) normalizes to Persian ک (U+06A9)."""
    assert _unicode_normalize_pass("\u0643") == "\u06A9"


def test_unicode_normalize_diacritics_removed():
    """Arabic diacritics (harakat U+064B--U+0652) and dagger alif U+0670 are removed."""
    # أَتناول = ALEF+HAMZA + FATHA + TAA etc.
    assert _unicode_normalize_pass("\u0623\u064e\u062a\u0646\u0627\u0648\u0644") == "\u0623\u062a\u0646\u0627\u0648\u0644"
    assert "\u064e" not in _unicode_normalize_pass("أَتناول")


def test_unicode_normalize_tatweel_removed():
    """Tatweel/kashida ـ (U+0640) is removed."""
    assert _unicode_normalize_pass("دواء\u0640\u0640") == "دواء"


def test_normalize_token_uses_unicode_pass():
    """_normalize_token applies yeh/kaf and diacritics so stopwords match across variants."""
    assert _normalize_token("في") == "فی"
    assert _normalize_token("كلمة") == "کلمة"


def test_medications_arabic_with_diacritics_still_matches():
    """Trigger with diacritics (أَتناول) still matches and extracts medication."""
    result = extract_candidates("\u0623\u064e\u062a\u0646\u0627\u0648\u0644 metformin", "ar")
    meds = [c for c in result if c.fact_key == "medications"]
    assert len(meds) >= 1
    med = next((c for c in meds if "metformin" in str(c.fact_value).lower()), None)
    assert med is not None
    assert med.confidence >= 0.70
