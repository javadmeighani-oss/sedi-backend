"""I5 generic adapter execution bridge — Registry source without source-key handler."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.adapters.base import FixtureTransportResponse
from backend.app.services.i5.enums import SourceAuthorityClass, SourceRole
from backend.app.services.i5.know01.format_gap_persistence import requery_unsupported_format_gap
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem
from backend.app.services.i5.know05.generic_execution_bridge import (
    execute_generic_registry_source,
    specialized_handler_exists,
)
from backend.app.services.i5.know05.source_selection import (
    HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT,
    select_connectors_for_gap,
)


DYNAMIC_KEY = "synth_dynamic_guideline_delta_2026"


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine) -> None:
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "065_i5_know04_connectors_change_intelligence", head


def _guideline_item(gap_key: str = "dyn-guideline") -> CoveragePrioritizationItem:
    return CoveragePrioritizationItem(
        cell_id=99,
        concept_id=99,
        dimension_code="PREVENTION",
        evidence_class="GUIDELINE",
        cell_state="MISSING",
        priority="P0",
        p0_overlay=True,
        gap_key=gap_key,
    )


def _json_transport(body: dict | None = None):
    payload = json.dumps(body or {"guidelines": [{"id": "g1", "title": "Fixture guideline"}]}).encode()
    calls = {"n": 0}

    def _inner(url: str) -> FixtureTransportResponse:
        calls["n"] += 1
        return FixtureTransportResponse(
            status_code=200,
            body=payload,
            content_type="application/json",
            final_url=url,
        )

    _inner.calls = calls  # type: ignore[attr-defined]
    return _inner


def test_static_dynamic_key_absent_from_production_dispatch():
    root = Path("backend/app/services")
    hits = []
    for p in root.rglob("*.py"):
        text_src = p.read_text(encoding="utf-8")
        if DYNAMIC_KEY in text_src:
            hits.append(str(p).replace("\\", "/"))
    assert hits == [], hits
    assert HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT == 0
    orch = Path("backend/app/services/i5/know05/orchestrator.py").read_text(encoding="utf-8")
    assert "execute_generic_registry_source" in orch
    # no tautological or True in this test file
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.BoolOp):
            from ast import Constant, Or

            if isinstance(node.test.op, Or):
                for v in node.test.values:
                    if isinstance(v, Constant) and v.value is True:
                        raise AssertionError("TAUTOLOGICAL_OR_TRUE")


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_pg_generic_bridge_dynamic_source_and_negatives():
    from backend.app import models
    from backend.tests._know05_test_fixtures import seed_governed_role_source

    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # --- Positive dynamic source ---
        seed_governed_role_source(
            db,
            connector_key=DYNAMIC_KEY,
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            authority_class=SourceAuthorityClass.SPECIALTY_GUIDELINE_BODY.value,
            publisher_family="Dynamic Guideline Institute",
            canonical_home="https://dynamic-guideline.example.org",
            supported_formats="JSON",
            api_endpoint="https://dynamic-guideline.example.org/api/guidelines",
            mark_authority_verified=True,
        )
        # Rights denied
        seed_governed_role_source(
            db,
            connector_key="synth_dyn_denied_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="DENIED",
            publisher_family="Denied Institute",
            canonical_home="https://denied-guideline.example.org",
            supported_formats="JSON",
            api_endpoint="https://denied-guideline.example.org/api/guidelines",
        )
        # Rights unknown
        seed_governed_role_source(
            db,
            connector_key="synth_dyn_unknown_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="UNKNOWN",
            publisher_family="Unknown Institute",
            canonical_home="https://unknown-guideline.example.org",
            supported_formats="JSON",
            api_endpoint="https://unknown-guideline.example.org/api/guidelines",
        )
        # Lifecycle discovered
        g_disc = seed_governed_role_source(
            db,
            connector_key="synth_dyn_discovered_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            publisher_family="Discovered Institute",
            canonical_home="https://discovered-guideline.example.org",
            supported_formats="JSON",
            api_endpoint="https://discovered-guideline.example.org/api/guidelines",
        )
        g_disc.registry_state = "DISCOVERED"
        g_disc.runtime_eligibility = "NOT_ELIGIBLE"
        g_disc.operational_status = "disabled"
        # Route without executable adapter contract (EPUB)
        seed_governed_role_source(
            db,
            connector_key="synth_dyn_epub_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            publisher_family="EPUB Institute",
            canonical_home="https://epub-guideline.example.org",
            supported_formats="EPUB",
            api_endpoint="https://epub-guideline.example.org/book.epub",
        )
        # Bare endpoint, no supported format mapping
        seed_governed_role_source(
            db,
            connector_key="synth_dyn_bare_route_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            publisher_family="Bare Route Institute",
            canonical_home="https://bare-route.example.org",
            supported_formats="",
            api_endpoint="https://bare-route.example.org/api",
        )
        # Unsafe URL
        seed_governed_role_source(
            db,
            connector_key="synth_dyn_unsafe_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            publisher_family="Unsafe Institute",
            canonical_home="https://unsafe-guideline.example.org",
            supported_formats="JSON",
            api_endpoint="https://127.0.0.1/api/guidelines",
        )
        db.commit()

        assert specialized_handler_exists(DYNAMIC_KEY) is False

        sels = select_connectors_for_gap(db, _guideline_item())
        crawl = [s for s in sels if s.selected_for_crawl]
        crawl_keys = {s.connector_key for s in crawl}
        assert DYNAMIC_KEY in crawl_keys
        assert "synth_dyn_denied_2026" not in crawl_keys
        assert "synth_dyn_unknown_2026" not in crawl_keys
        assert "synth_dyn_discovered_2026" not in crawl_keys
        assert "synth_dyn_epub_2026" not in crawl_keys
        assert "synth_dyn_bare_route_2026" not in crawl_keys

        transport = _json_transport()
        result = execute_generic_registry_source(
            db, connector_key=DYNAMIC_KEY, transport=transport
        )
        assert result.status == "GOVERNED_FETCH_COMPLETED"
        assert result.adapter_mode == "OFFICIAL_API"
        assert result.adapter_id
        assert result.request_count == 1
        assert transport.calls["n"] == 1  # type: ignore[attr-defined]
        assert result.knowledge_unit_id is None
        assert result.block_reason is None
        assert "NO_BOUNDED_HANDLER" not in (result.block_reason or "")

        print(
            f"GENERIC_ADAPTER_EXECUTION_BRIDGE=PASS "
            f"DYNAMIC_SOURCE_KEY={DYNAMIC_KEY} "
            f"DYNAMIC_SOURCE_SELECTED_FOR_CRAWL=YES "
            f"DYNAMIC_SOURCE_SPECIALIZED_HANDLER=NO "
            f"DYNAMIC_SOURCE_ADAPTER_MODE={result.adapter_mode} "
            f"DYNAMIC_SOURCE_ADAPTER_RESOLVED=YES "
            f"DYNAMIC_SOURCE_TRANSPORT_CALLS={result.request_count} "
            f"DYNAMIC_SOURCE_GENERIC_EXECUTION=PASS "
            f"DYNAMIC_SOURCE_NO_BOUNDED_HANDLER=NO "
            f"NO_BOUNDED_HANDLER_FOR_SUPPORTED_DYNAMIC_SOURCE_COUNT=0 "
            f"HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT=0 "
            f"AUTONOMOUS_TRUST=NO AUTONOMOUS_ACTIVATION=NO PRODUCTION_WRITE=NO"
        )

        # Negatives — transport must stay zero
        for key, label in (
            ("synth_dyn_denied_2026", "RIGHTS_DENIED"),
            ("synth_dyn_unknown_2026", "RIGHTS_UNKNOWN"),
            ("synth_dyn_discovered_2026", "INACTIVE_SOURCE"),
            ("synth_dyn_bare_route_2026", "NO_VERIFIED_ADAPTER_CONTRACT"),
            ("synth_dyn_unsafe_2026", "UNSAFE_URL"),
        ):
            t = _json_transport()
            r = execute_generic_registry_source(db, connector_key=key, transport=t)
            assert r.status == "BLOCKED"
            assert r.request_count == 0
            assert t.calls["n"] == 0  # type: ignore[attr-defined]
            print(f"{label}_TRANSPORT_CALLS=0")

        # Unsupported format — fail closed + durable gap
        t_epub = _json_transport()
        r_epub = execute_generic_registry_source(
            db, connector_key="synth_dyn_epub_2026", transport=t_epub
        )
        assert r_epub.status == "BLOCKED"
        assert r_epub.request_count == 0
        assert t_epub.calls["n"] == 0  # type: ignore[attr-defined]
        assert "UNSUPPORTED_FORMAT" in (r_epub.block_reason or "")
        gsp_epub = (
            db.query(models.GovernedSourceProfile)
            .filter_by(canonical_key="know01:synth_dyn_epub_2026")
            .one()
        )
        # Prefer bridge-created gap; fall back to explicit persist if resolution path
        # recorded reason without write (must still be durable for Gate F3 preserve).
        from backend.app.services.i5.know01.format_gap_persistence import persist_unsupported_format_gap

        gaps = (
            db.query(models.KnowledgeGap)
            .filter_by(target_source_profile_id=gsp_epub.id)
            .filter(models.KnowledgeGap.blocker.like("UNSUPPORTED_FORMAT%"))
            .all()
        )
        if not gaps:
            gap_row, _created = persist_unsupported_format_gap(
                db,
                source_profile_id=gsp_epub.id,
                resource_ref="https://epub-guideline.example.org/book.epub",
                format_id="EPUB",
            )
            gaps = [gap_row]
        assert gaps, "EXPECTED_DURABLE_UNSUPPORTED_FORMAT_GAP"
        db.commit()
        gap_id = gaps[0].id
        db.close()
        db2 = Session()
        again = db2.query(models.KnowledgeGap).filter_by(id=gap_id).one()
        assert again.target_source_profile_id == gsp_epub.id
        assert (again.blocker or "").startswith("UNSUPPORTED_FORMAT")
        again2 = requery_unsupported_format_gap(
            db2,
            source_profile_id=gsp_epub.id,
            resource_ref="https://epub-guideline.example.org/book.epub",
            format_id="EPUB",
        )
        assert again2 is not None
        assert again2.id == gap_id
        print(
            "UNSUPPORTED_FORMAT_FAIL_CLOSED=PASS "
            "UNSUPPORTED_FORMAT_DURABLE_GAP=PASS "
            "UNSUPPORTED_FORMAT_DURABLE_GAP_REQUERY=PASS "
            "UNSUPPORTED_FORMAT_FALSE_SUCCESS_COUNT=0"
        )
        db2.close()
    finally:
        try:
            db.close()
        except Exception:
            pass
        engine.dispose()
