"""Gate 2 — PATCH /auth/me request schema (no DB)."""

from datetime import date

import pytest
from pydantic import ValidationError

from backend.app.schemas.auth_otp import MeUpdateIn


def test_gate2_jalali_registration_payload_accepts_persian_name():
    payload = MeUpdateIn(
        name="جواد",
        sex="male",
        preferred_language="fa",
        calendar_type="jalali",
        birth_day=1,
        birth_month=1,
        birth_year=1370,
        date_of_birth=date(1991, 3, 21),
    )
    assert payload.name == "جواد"
    assert payload.calendar_type == "jalali"


def test_gate2_patch_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        MeUpdateIn()
