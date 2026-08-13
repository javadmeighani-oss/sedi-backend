"""Section44 storage-model arithmetic. No schema mutation. No infrastructure."""

from __future__ import annotations

from backend.app.services.i7.storage_capacity_model import (
    ASSUMPTIONS,
    HORIZONS_YEARS,
    USER_COUNTS,
    fleet_bytes,
    format_bytes,
    report_status,
    unlimited_chat_bytes,
    user_bytes,
)


def test_assumptions_are_explicit_for_all_scenarios():
    required = {
        "active_facts_steady",
        "new_fact_versions_per_year",
        "umf_row_bytes",
        "raw_chat_retain_days",
        "optional_embedding_bytes_per_fact",
    }
    for name, row in ASSUMPTIONS.items():
        assert required <= set(row), name
        assert row["optional_embedding_bytes_per_fact"] == 0
        assert row["raw_chat_retain_days"] <= 90


def test_base_1y_and_100y_are_finite_and_chat_is_capped():
    y1 = user_bytes("BASE", 1)
    y100 = user_bytes("BASE", 100)
    assert y1["primary_heap"] > 0
    assert y100["primary_heap"] > y1["primary_heap"]
    assert y100["raw_chat_capped"] == y1["raw_chat_capped"]
    unlimited = unlimited_chat_bytes(100)
    assert unlimited > y100["primary_heap"] * 10


def test_fleet_5000_users_10y_base_fits_planning_envelope():
    rec = fleet_bytes("BASE", 5_000, 10)
    assert rec["primary_heap"] < 5_000 * 50 * 1024 * 1024
    assert rec["unlimited_chat_contrast"] > rec["primary_heap"]
    assert rec["backup_footprint"] > rec["live_with_replicas"]


def test_matrix_covers_required_user_and_horizon_grid():
    assert USER_COUNTS == (100, 1_000, 5_000, 100_000, 1_000_000)
    assert HORIZONS_YEARS == (1, 5, 10, 50, 100)
    million_100 = fleet_bytes("BASE", 1_000_000, 100)
    assert 20 * 1024**4 < million_100["primary_heap"] < 40 * 1024**4
    assert million_100["unlimited_chat_contrast"] > 10 * million_100["primary_heap"]
    assert "TB" in format_bytes(million_100["backup_footprint"]) or "PB" in format_bytes(
        million_100["backup_footprint"]
    )


def test_report_status_forbids_unlimited_chat():
    rep = report_status()
    assert rep.status == "PASS"
    assert rep.unlimited_raw_chat == "FORBIDDEN"
