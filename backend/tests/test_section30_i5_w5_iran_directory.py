"""Section 30 / W5-P01 — Iran directory layer (P10).

Frozen node contract: 24 exact nodes (T1–T24).
No live IR fetch/network. Migration AUTHOR only (not run).
IR directory → KnowledgeUnit forbidden. local_rag untouched.
"""
from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5 import iran_directory_service as ids
from backend.app.services.i5.iran_directory_service import (
    MANAGEMENT_ALIAS,
    MIGRATION_RUN_EXECUTED,
    NO_CLINICAL_AUTHORITY,
    NO_IR_TO_KU,
    NO_LIVE_IR_SOURCE_FETCH,
    PACKAGE_ID,
    SERVICE_NAME,
    ForbiddenClinicalWriteError,
    refuse_ir_directory_to_knowledge_unit,
    search_doctors,
    search_hospitals,
    search_laboratories,
)


def _load_models():
    return importlib.import_module("backend.app.models")


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


def _seed_doctor(db, **overrides):
    models = _load_models()
    base = dict(
        canonical_directory_key="doc-" + overrides.pop("key_suffix", "a1"),
        full_name="Dr Example Tehrani",
        specialty="Neurology",
        city="Tehran",
        province="Tehran",
        phone="+982100000000",
        address="Example St",
        record_state="ACTIVE",
        source_system_label=None,
    )
    base.update(overrides)
    row = models.IranDoctor(**base)
    db.add(row)
    db.flush()
    return row


def _seed_lab(db, **overrides):
    models = _load_models()
    base = dict(
        canonical_directory_key="lab-" + overrides.pop("key_suffix", "a1"),
        name="Example Lab",
        city="Isfahan",
        province="Isfahan",
        services_text="CBC",
        record_state="ACTIVE",
    )
    base.update(overrides)
    row = models.IranLaboratory(**base)
    db.add(row)
    db.flush()
    return row


def _seed_hospital(db, **overrides):
    models = _load_models()
    base = dict(
        canonical_directory_key="hosp-" + overrides.pop("key_suffix", "a1"),
        name="Example Hospital",
        facility_type="HOSPITAL",
        city="Shiraz",
        province="Fars",
        record_state="ACTIVE",
    )
    base.update(overrides)
    row = models.IranHospital(**base)
    db.add(row)
    db.flush()
    return row


def test_W5P01_T1_package_identity():
    assert PACKAGE_ID == "I5-IMPL-W5-P01"
    assert MANAGEMENT_ALIAS == "P10"
    assert SERVICE_NAME == "directory_search"
    assert NO_IR_TO_KU is True
    assert NO_CLINICAL_AUTHORITY is True
    assert NO_LIVE_IR_SOURCE_FETCH is True
    assert MIGRATION_RUN_EXECUTED is False


def test_W5P01_T2_iran_doctor_orm_persist(db):
    _require_postgres(db)
    configure_mappers()
    row = _seed_doctor(db, key_suffix="t2")
    assert row.id > 0
    assert row.full_name == "Dr Example Tehrani"


def test_W5P01_T3_iran_laboratory_orm_persist(db):
    _require_postgres(db)
    configure_mappers()
    row = _seed_lab(db, key_suffix="t3")
    assert row.id > 0
    assert row.name == "Example Lab"


def test_W5P01_T4_iran_hospital_orm_persist(db):
    _require_postgres(db)
    configure_mappers()
    row = _seed_hospital(db, key_suffix="t4")
    assert row.id > 0
    assert row.facility_type == "HOSPITAL"


def test_W5P01_T5_unique_canonical_directory_key(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="uniq")
    with pytest.raises(IntegrityError):
        _seed_doctor(db, key_suffix="uniq", full_name="Other")
        db.flush()


def test_W5P01_T6_search_doctor(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="s6", full_name="Dr Searchable")
    items = search_doctors(db, name="Searchable")
    assert len(items) == 1
    assert items[0]["entity_type"] == "DOCTOR"
    assert items[0]["is_knowledge_unit"] is False


def test_W5P01_T7_search_laboratory(db):
    _require_postgres(db)
    configure_mappers()
    _seed_lab(db, key_suffix="s7", name="Searchable Lab")
    items = search_laboratories(db, name="Searchable")
    assert len(items) == 1
    assert items[0]["entity_type"] == "LABORATORY"


def test_W5P01_T8_search_hospital(db):
    _require_postgres(db)
    configure_mappers()
    _seed_hospital(db, key_suffix="s8", name="Searchable Hospital")
    items = search_hospitals(db, name="Searchable")
    assert len(items) == 1
    assert items[0]["entity_type"] == "HOSPITAL"


def test_W5P01_T9_search_filter_city_specialty(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="f9a", city="Tehran", specialty="Cardiology", full_name="Dr A")
    _seed_doctor(db, key_suffix="f9b", city="Mashhad", specialty="Cardiology", full_name="Dr B")
    items = search_doctors(db, city="Tehran", specialty="Cardio")
    assert len(items) == 1
    assert items[0]["city"] == "Tehran"


def test_W5P01_T10_empty_result(db):
    _require_postgres(db)
    configure_mappers()
    assert search_doctors(db, name="ZZZ-NO-MATCH") == []


def test_W5P01_T11_schema_serialization():
    from backend.app.schemas.i5_iran_directory import IranDoctorView

    view = IranDoctorView(
        entity_type="DOCTOR",
        id=1,
        canonical_directory_key="k",
        full_name="Dr X",
        record_state="ACTIVE",
        endorsement_disclaimer=ids.ENDORSEMENT_DISCLAIMER,
        is_clinical_authority=False,
        is_knowledge_unit=False,
    )
    dumped = view.model_dump()
    assert "knowledge_unit_id" not in dumped
    assert dumped["is_clinical_authority"] is False


def test_W5P01_T12_api_contract(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="api12", full_name="Dr API")
    from backend.app.routers import i5_iran_directory as router_mod
    from backend.app.database import get_db

    app = FastAPI()
    app.include_router(router_mod.router)

    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    os.environ["ADMIN_TOKEN"] = "w5p01-test-admin-token"
    client = TestClient(app)
    resp = client.get(
        "/i5/directory/doctors",
        headers={"X-Admin-Token": "w5p01-test-admin-token"},
        params={"name": "API"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_id"] == PACKAGE_ID
    assert body["is_clinical_knowledge"] is False
    assert body["no_ir_to_ku"] is True
    assert body["count"] >= 1


def test_W5P01_T13_entity_type_separation(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="e13")
    _seed_lab(db, key_suffix="e13")
    _seed_hospital(db, key_suffix="e13")
    docs = search_doctors(db)
    labs = search_laboratories(db)
    hosps = search_hospitals(db)
    assert all(i["entity_type"] == "DOCTOR" for i in docs)
    assert all(i["entity_type"] == "LABORATORY" for i in labs)
    assert all(i["entity_type"] in {"HOSPITAL", "MEDICAL_CENTER"} for i in hosps)


def test_W5P01_T14_userdoctor_vs_irandoctor_separation():
    models = _load_models()
    assert models.UserDoctor.__tablename__ == "user_doctors"
    assert models.IranDoctor.__tablename__ == "iran_doctors"
    assert models.UserDoctor.__tablename__ != models.IranDoctor.__tablename__
    user_cols = {c.name for c in models.UserDoctor.__table__.columns}
    iran_cols = {c.name for c in models.IranDoctor.__table__.columns}
    assert "user_id" in user_cols
    assert "user_id" not in iran_cols
    assert "canonical_directory_key" in iran_cols
    assert "canonical_directory_key" not in user_cols


def test_W5P01_T15_no_ir_to_ku_structural_fk():
    models = _load_models()
    for cls in (models.IranDoctor, models.IranLaboratory, models.IranHospital):
        fks = list(cls.__table__.foreign_keys)
        targets = {fk.column.table.name for fk in fks}
        assert "knowledge_units" not in targets
        assert "knowledge_memory_items" not in targets
        assert "knowledge_provenance" not in targets


def test_W5P01_T16_no_ku_creation_via_directory_service():
    with pytest.raises(ForbiddenClinicalWriteError):
        refuse_ir_directory_to_knowledge_unit(directory_id=1, statement="fake clinical")
    src = Path("backend/app/services/i5/iran_directory_service.py").read_text(encoding="utf-8")
    assert "knowledge_unit_service" not in src
    tree = ast.parse(src)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
    assert not any("knowledge_unit_service" in m for m in imported)


def test_W5P01_T17_no_clinical_evidence_output(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="c17")
    item = search_doctors(db)[0]
    for banned in (
        "knowledge_unit_id",
        "normalized_statement",
        "evidence_strength",
        "medical_safety_state",
        "runtime_eligibility",
        "provenance_id",
    ):
        assert banned not in item
    assert item["is_clinical_authority"] is False


def test_W5P01_T18_no_network_markers():
    src = Path("backend/app/services/i5/iran_directory_service.py").read_text(encoding="utf-8")
    for token in ("requests.", "httpx", "urllib.request", "openai", "aiohttp"):
        assert token not in src


def test_W5P01_T19_migration_authored_not_run():
    mig = Path("backend/alembic/versions/052_i5_w5_iran_directory.py")
    assert mig.is_file()
    text = mig.read_text(encoding="utf-8")
    assert 'revision: str = "052_i5_w5_iran_directory"' in text
    assert 'down_revision: Union[str, None] = "051_i5b2_governed_source_profile"' in text
    assert "iran_doctors" in text
    assert "iran_laboratories" in text
    assert "iran_hospitals" in text
    assert MIGRATION_RUN_EXECUTED is False
    # Prove this Gate did not invoke alembic upgrade (constant + no env flag).
    assert os.environ.get("SEDI_I5_W5P01_ALEMBIC_UPGRADE") in (None, "", "0", "false", "False")


def test_W5P01_T20_source_legal_boundary_no_live_source():
    assert NO_LIVE_IR_SOURCE_FETCH is True
    meta = ids.directory_package_metadata()
    assert meta["no_live_ir_source_fetch"] is True
    src = Path("backend/app/services/i5/iran_directory_service.py").read_text(encoding="utf-8")
    # Forbid live fetch/API client imports; docstring mentions of prohibited behaviors are allowed.
    for token in ("import requests", "import httpx", "urllib.request", "aiohttp", "openai"):
        assert token not in src
    assert "def scrape" not in src
    assert "def crawl" not in src


def test_W5P01_T21_endorsement_disclaimer(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="d21")
    item = search_doctors(db)[0]
    assert "informational" in item["endorsement_disclaimer"].lower()
    assert "recommend" in item["endorsement_disclaimer"].lower()


def test_W5P01_T22_git_history_evidence_invariant():
    """W4P02-EVIDENCE-GIT-HISTORY-01: evidence must use explicit SHAs + fetch-depth 0."""
    wf = Path(".github/workflows/w5p01-postgresql-iran-directory-runtime.yml")
    assert wf.is_file()
    text = wf.read_text(encoding="utf-8")
    assert "fetch-depth: 0" in text
    assert "HEAD~1" not in text
    builder = Path("backend/tests/helpers/w5p01_build_evidence_assurance_pack.py")
    assert builder.is_file()
    btxt = builder.read_text(encoding="utf-8")
    assert "GATE_START_SHA" in btxt
    assert "GREEN_TECHNICAL_SHA" in btxt or "GITHUB_SHA" in btxt
    assert "HEAD~1" not in btxt


def test_W5P01_T23_medical_center_facility_type(db):
    _require_postgres(db)
    configure_mappers()
    _seed_hospital(
        db,
        key_suffix="mc23",
        name="Example Medical Center",
        facility_type="MEDICAL_CENTER",
    )
    items = search_hospitals(db, facility_type="MEDICAL_CENTER")
    assert len(items) == 1
    assert items[0]["entity_type"] == "MEDICAL_CENTER"


def test_W5P01_T24_inactive_excluded_by_default(db):
    _require_postgres(db)
    configure_mappers()
    _seed_doctor(db, key_suffix="act24", full_name="Active Doc", record_state="ACTIVE")
    _seed_doctor(db, key_suffix="inact24", full_name="Inactive Doc", record_state="INACTIVE")
    items = search_doctors(db, name="Doc")
    names = {i["full_name"] for i in items}
    assert "Active Doc" in names
    assert "Inactive Doc" not in names
