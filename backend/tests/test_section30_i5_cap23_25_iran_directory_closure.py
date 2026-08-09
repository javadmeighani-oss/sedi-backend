"""CAP23-25 closure tests: acquisition is injectable; imports stay directory-only."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.services.i5.iran_directory_acquisition import (
    IrimcMemberSearchClient,
    TransportResponse,
    bounded_query,
)
from backend.app.services.i5.iran_directory_import import apply_plan, dry_run_plan
from backend.app.services.i5.iran_directory_normalization import normalize_records, parse_irimc_search_html
from backend.app.services.i5.iran_directory_service import (
    ForbiddenClinicalWriteError,
    search_doctors,
)
from backend.app.services.i5.iran_directory_source_manifest import (
    MAX_CONCURRENT_SEARCHES,
    MIN_SEARCH_INTERVAL_SECONDS,
    SOURCE_MANIFEST,
    SourceNotAuthorizedError,
    get_authorized_source,
    robots_path_allowed,
)

SAMPLE_HTML = """
<table><tbody><tr class="rowclass">
<td>آرمان</td><td>آزادی</td><td>1234</td>
<td><p>پزشکی داخلی</p></td><td>تهران-تهران</td><td>پزشکی</td>
<td><a href="/member/profile?id=11111111-2222-3333-4444-555555555555">نمایش پروفایل</a></td>
</tr></tbody></table>
"""


def _doctor(name: str = "دکتر نمونه") -> dict:
    return {
        "entity_family": "DOCTOR",
        "profile_id": "11111111-2222-3333-4444-555555555555",
        "full_name": name,
        "specialty": "داخلی",
        "city": "تهران",
    }


def test_manifest_and_robots_fail_closed():
    assert SOURCE_MANIFEST["irimc_member_search"]["ALLOWED_FOR_V1_POPULATION"] is True
    assert MAX_CONCURRENT_SEARCHES == 1
    assert MIN_SEARCH_INTERVAL_SECONDS >= 60
    assert robots_path_allowed("irimc_member_search", "/searchresult") is True
    assert robots_path_allowed("irimc_member_search", "/admin/") is False
    assert robots_path_allowed("unknown", "/") is False
    with pytest.raises(SourceNotAuthorizedError):
        get_authorized_source("iran_hospital_official_pending")


def test_injected_transport_fetches_token_and_result():
    calls = []

    def get(url, **kwargs):
        calls.append(("get", url, kwargs))
        return TransportResponse(b'<input name="__RequestVerificationToken" value="token-1">', {"sid": "one"})

    def post(url, **kwargs):
        calls.append(("post", url, kwargs))
        return TransportResponse(SAMPLE_HTML.encode())

    result = IrimcMemberSearchClient(get, post).search({"FirstName": "آرمان"})
    assert result == SAMPLE_HTML.encode()
    assert calls[1][2]["data"]["__RequestVerificationToken"] == "token-1"
    assert calls[1][2]["cookies"] == {"sid": "one"}
    with pytest.raises(ValueError, match="QUERY_EMPTY"):
        bounded_query({})


def test_parse_normalize_canonical_key_and_dedupe():
    raw = parse_irimc_search_html(SAMPLE_HTML)
    valid, rejected = normalize_records(raw + raw)
    assert valid[0]["canonical_directory_key"] == "irimc_member_search:11111111-2222-3333-4444-555555555555"
    assert valid[0]["full_name"] == "آرمان آزادی"
    assert valid[0]["city"] == "تهران-تهران"
    assert valid[0]["source_system_label"] == "irimc_member_search"
    assert rejected[0]["reason"] == "DUPLICATE_CANONICAL_KEY"


def test_normalization_clamps_display_fields_and_rejects_malformed_profile():
    invalid = _doctor()
    invalid["profile_id"] = "a" * 129
    clamped = _doctor("x" * 257)
    valid, rejected = normalize_records([clamped, invalid])
    assert valid[0]["full_name"] == "x" * 256
    assert rejected[0]["reason"] == "PROFILE_ID_INVALID"
    parsed = parse_irimc_search_html(SAMPLE_HTML)[0]
    assert "entity_family" not in parsed


def test_facility_normalization_paths_accept_structured_fixtures():
    records = [
        {"entity_family": "LABORATORY", "canonical_directory_key": "fixture:lab-1", "source_system_label": "fixture",
         "name": "آزمایشگاه نمونه", "services_text": "CBC"},
        {"entity_family": "HOSPITAL", "canonical_directory_key": "fixture:hospital-1", "source_system_label": "fixture",
         "name": "بیمارستان نمونه", "facility_type": "HOSPITAL"},
    ]
    valid, rejected = normalize_records(records)
    assert len(valid) == 2
    assert rejected == []
    assert {record["entity_family"] for record in valid} == {"LABORATORY", "HOSPITAL"}


def test_dry_run_and_knowledge_unit_refusal():
    plan = dry_run_plan([_doctor()])
    assert plan["doctor"]["insert"] == 1
    assert plan["doctor"]["update"] == 0
    with pytest.raises(ForbiddenClinicalWriteError):
        dry_run_plan([dict(_doctor(), knowledge_unit_id=9)])


def test_import_has_no_ranking_or_destructive_operations():
    source = Path("backend/app/services/i5/iran_directory_import.py").read_text(encoding="utf-8")
    assert "ranking" not in source
    assert ".delete(" not in source
    assert "auto_deactivate" not in source


def test_postgres_apply_update_idempotency_and_active_search(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for directory ORM persistence")
    first = apply_plan(db, [_doctor()])
    assert first["doctor"]["insert"] == 1
    row = search_doctors(db, name="نمونه")[0]
    observed_at = row["last_observed_at"]
    replay = apply_plan(db, [_doctor()])
    assert replay["doctor"]["unchanged"] == 1
    assert search_doctors(db, name="نمونه")[0]["last_observed_at"] == observed_at
    changed = apply_plan(db, [_doctor("دکتر نمونه تغییر")])
    assert changed["doctor"]["update"] == 1
    assert len(search_doctors(db, name="تغییر")) == 1


def test_router_is_mounted_and_keeps_admin_gate(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "cap23-token")
    from backend.app.main import app

    with TestClient(app) as client:
        assert client.get("/i5/directory/meta").status_code == 401
        response = client.get("/i5/directory/meta", headers={"X-Admin-Token": "cap23-token"})
    assert response.status_code == 200
    assert response.json()["no_ir_to_ku"] is True
