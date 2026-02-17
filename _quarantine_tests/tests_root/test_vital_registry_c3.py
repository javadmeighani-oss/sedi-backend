# tests/test_vital_registry_c3.py
import pytest
from datetime import datetime

from app.services.vitals.vital_registry import validate_event, map_to_memory_facts, VitalValidationError


def test_validate_heart_rate():
    norm = validate_event("heart_rate", {"bpm": 80, "quality": "good"})
    assert norm["bpm"] == 80
    assert norm["quality"] == "good"


def test_validate_blood_pressure():
    norm = validate_event("blood_pressure", {"sys": 120, "dia": 80, "pulse": 72})
    assert norm == {"sys": 120, "dia": 80, "pulse": 72}


def test_validate_glucose_normalizes_mmol_to_mgdl():
    norm = validate_event("glucose", {"mmol_l": 5.0})
    assert abs(norm["glucose_mg_dl"] - 90.0) < 0.001


def test_validate_temperature_normalizes_f_to_c():
    norm = validate_event("temperature", {"f": 98.6})
    assert abs(norm["temperature_c"] - 37.0) < 0.2


def test_validate_rejects_unknown_type():
    with pytest.raises(VitalValidationError):
        validate_event("ecg", {"x": 1})


def test_map_to_memory_facts_bp_creates_two_keys_and_optional_pulse_hr():
    recorded_at = datetime(2026, 2, 3, 6, 40, 0)
    norm = {"sys": 130, "dia": 85, "pulse": 70}
    updates = map_to_memory_facts(
        user_id=1,
        event_type="blood_pressure",
        normalized_payload=norm,
        device_id="Sedi001",
        recorded_at=recorded_at,
    )
    keys = {u.key for u in updates}
    assert "blood_pressure_sys" in keys
    assert "blood_pressure_dia" in keys
    assert "heart_rate_bpm" in keys

