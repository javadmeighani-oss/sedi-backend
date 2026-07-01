"""Post-generation safety validator for Gate 3."""

import re
from typing import Optional, Tuple

UNSAFE_PATTERNS = [
    (re.compile(r"\byou have\b.{0,40}\b(diabetes|cancer|stroke|heart attack)\b", re.I), "definitive_diagnosis"),
    (re.compile(r"شما\s+.+\s+دارید", re.I), "definitive_diagnosis"),
    (re.compile(r"\b(increase|decrease|reduce|raise)\b.{0,30}\b(dose|dosage|mg)\b", re.I), "medication_dose_change"),
    (re.compile(r"(دوز|میلی\s*گرم).{0,20}(زیاد|کم|افزایش|کاهش)", re.I), "medication_dose_change"),
    (re.compile(r"\bstop taking\b.{0,30}\b(medication|medicine|med)\b", re.I), "stop_medication"),
    (re.compile(r"\bstart taking\b.{0,30}\b(medication|medicine|med)\b", re.I), "start_medication"),
    (re.compile(r"دارو.{0,15}(قطع|حذف|شروع)\s*کن", re.I), "stop_start_medication"),
    (re.compile(r"\bbest doctor\b|\bبهترین دکتر\b", re.I), "unsupported_provider_ranking"),
    (re.compile(r"\btake\b.{0,20}\b(aspirin|nitroglycerin|epinephrine)\b", re.I), "emergency_treatment_instruction"),
    (re.compile(r"\byou have\b.{0,40}\b(depression|adhd|bipolar|anxiety disorder|personality disorder)\b", re.I), "psychiatric_disorder_diagnosis"),
    (re.compile(r"شما\s+.+\s+(افسردگی|اضطراب|دو قطبی|اختلال شخصیت)\s+دارید", re.I), "psychiatric_disorder_diagnosis"),
    (re.compile(r"\b(i am your therapist|replace your psychiatrist|stop therapy)\b", re.I), "replace_therapist_or_psychiatrist"),
]


def validate_response_text(text: str) -> Tuple[bool, Optional[str]]:
    """Return (is_safe, violation_code)."""
    if not text or not str(text).strip():
        return True, None
    for pat, code in UNSAFE_PATTERNS:
        if pat.search(text):
            return False, code
    return True, None
