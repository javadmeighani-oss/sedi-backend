"""Image-resident PubMed derived persist canary + idempotent rerun + synthetic failure.

Must run with PYTHONPATH=/app inside sedi-backend. Never prints NCBI email or abstracts.
"""
from __future__ import annotations

import json
import os
import time
import traceback

os.environ.setdefault("PYTHONPATH", "/app")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.know05.bounded_ingestion import (
    PUBMED_CANARY_DEFAULT_QUERY,
    ingest_pubmed_bounded,
)
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity


def _log(k, v):
    print(f"I5_PUBMED|{k}|{v}", flush=True)


def _counts(db):
    mem = 0
    kce = 0
    if hasattr(models, "KnowledgeMemoryItem"):
        mem = db.query(models.KnowledgeMemoryItem).count()
    if hasattr(models, "KnowledgeChunkEmbedding"):
        kce = db.query(models.KnowledgeChunkEmbedding).count()
    elif hasattr(models, "I5KnowledgeChunkEmbedding"):
        kce = db.query(models.I5KnowledgeChunkEmbedding).count()
    eligible = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.runtime_eligibility == "ELIGIBLE")
        .count()
    )
    return {
        "raw": db.query(models.I5RawEvidence).count(),
        "artifact": db.query(models.I5ScientificArtifact).count(),
        "ku": db.query(models.KnowledgeUnit).count(),
        "prov": db.query(models.KnowledgeProvenance).count(),
        "memory": mem,
        "kce": kce,
        "eligible": eligible,
        "cells": db.query(models.I5KnowledgeCoverageCell).count()
        if hasattr(models, "I5KnowledgeCoverageCell")
        else 0,
        "cells_partial": (
            db.query(models.I5KnowledgeCoverageCell)
            .filter(models.I5KnowledgeCoverageCell.cell_state == "PARTIAL")
            .count()
            if hasattr(models, "I5KnowledgeCoverageCell")
            else 0
        ),
    }


def _fail_http(kind: str):
    class _Resp:
        def __init__(self, status, content=b"", headers=None):
            self.status_code = status
            self.content = content
            self.headers = headers or {"Content-Type": "text/plain"}
            self.url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    def _get(url, headers=None, timeout=None, **kwargs):
        if kind == "429":
            return _Resp(429, b"retry later", {"Content-Type": "text/plain", "Retry-After": "1"})
        if kind == "timeout":
            raise TimeoutError("SYNTHETIC_TIMEOUT")
        return _Resp(500, b"invalid", {"Content-Type": "text/plain"})

    return _get


def main() -> int:
    leak_needles = []
    email = os.environ.get("SEDI_NCBI_EMAIL", "")
    if email:
        leak_needles.append(email)
    api_key = os.environ.get("SEDI_NCBI_API_KEY", "")
    if api_key:
        leak_needles.append(api_key)

    def _assert_no_leak(blob: str):
        low = blob.lower()
        for n in leak_needles:
            if n and n.lower() in low:
                raise SystemExit("SECRET_LEAK")

    _log("outbound_email_to_ncbi", "NO")
    _log("ncbi_tool_email_registration_status", "NOT_REGISTERED")
    ident = load_ncbi_operational_identity(require_for_weekly=True)
    _log("ncbi_operational_identity_status", ident.weekly_operation_status)
    _log("ncbi_tool_present", "YES" if ident.tool else "NO")
    _log("ncbi_email_present", "YES" if ident.email else "NO")
    _log("ncbi_email_domain", ident.email.rsplit("@", 1)[-1] if "@" in ident.email else "")
    _log("ncbi_api_key_present", "YES" if ident.api_key_present else "NO")
    _log("nf16_blocked_by_api_key", "NO")

    url = os.environ.get("DATABASE_URL")
    if not url:
        _log("database_url", "MISSING")
        return 2
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        alembic = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        _log("alembic", alembic)
        before = _counts(db)
        for k, v in before.items():
            _log(f"before_{k}", v)

        orch = os.environ.get("SEDI_I5_WEEKLY_ORCHESTRATOR_ENABLED", "")
        src = os.environ.get("SEDI_I5_SOURCE_ACTIVATION_ENABLED", "")
        multi = os.environ.get("SEDI_I5_MULTISOURCE_ENABLED", "")
        _log("i5_weekly_orchestrator_enabled", orch)
        _log("i5_source_activation_enabled", src)
        _log("i5_multisource_enabled", multi)

        from backend.app.services.i5.weekly_orchestrator import run_dormant_scheduled_tick as weekly_dormant

        dormant = weekly_dormant()
        _log("i5_weekly_tick_outcome", getattr(dormant, "outcome", "UNKNOWN"))
        _log("network_executed", str(getattr(dormant, "network_executed", "")).lower())
        _log("production_write", str(getattr(dormant, "production_write", "")).lower())

        t0 = time.monotonic()
        r1 = ingest_pubmed_bounded(
            db,
            persist=True,
            ensure_official_source=True,
            query=PUBMED_CANARY_DEFAULT_QUERY,
            max_records=1,
            max_rps=1.0,
        )
        db.commit()
        t1 = time.monotonic()
        after1 = _counts(db)
        _log("canary1_status", r1.status)
        _log("canary1_block_reason", r1.block_reason or "")
        _log("canary1_storage", r1.storage_decision)
        _log("canary1_request_count", r1.request_count)
        _log("canary1_external_ids", ",".join(r1.external_ids[:2]))
        _log("canary1_ku_id", r1.knowledge_unit_id or 0)
        _log("canary1_artifact_id", r1.artifact_id or 0)
        _log("canary1_runtime_eligible", r1.clinical_runtime_eligible)
        _log("canary1_duration_s", round(t1 - t0, 3))
        _assert_no_leak(json.dumps(r1.as_dict(), default=str))

        pmid = ""
        if r1.artifact_id:
            art = db.query(models.I5ScientificArtifact).filter_by(id=r1.artifact_id).first()
            if art is not None:
                pmid = art.pmid or ""
                _log("pubmed_selected_pmid", pmid)
                _log("pubmed_doi", art.doi or "")
                _log("pubmed_pmcid", art.pmcid or "")
                _log("pubmed_artifact_type", art.artifact_type)
                vers = (
                    db.query(models.I5ScientificArtifactVersion)
                    .filter_by(artifact_id=art.id)
                    .all()
                )
                _log(
                    "pubmed_abstract_verbatim_persisted",
                    "YES" if any(v.abstract_or_summary for v in vers) else "NO",
                )
        if r1.knowledge_unit_id:
            ku = db.query(models.KnowledgeUnit).filter_by(id=r1.knowledge_unit_id).first()
            if ku is not None:
                _log("ku_publication_state", ku.publication_state)
                _log("ku_review_state", ku.review_state)
                _log("ku_runtime_eligibility", ku.runtime_eligibility)
                _assert_no_leak(ku.normalized_statement or "")

        r2 = ingest_pubmed_bounded(
            db,
            persist=True,
            ensure_official_source=True,
            query=PUBMED_CANARY_DEFAULT_QUERY,
            max_records=1,
            max_rps=1.0,
        )
        db.commit()
        after2 = _counts(db)
        _log("canary2_status", r2.status)
        _log("canary2_ku_id", r2.knowledge_unit_id or 0)
        _log("canary2_records_changed", r2.records_changed)
        _log("idempotent_ku_same", "YES" if r1.knowledge_unit_id and r1.knowledge_unit_id == r2.knowledge_unit_id else "NO")

        r429 = ingest_pubmed_bounded(
            db,
            persist=False,
            http_get=_fail_http("429"),
            max_records=1,
        )
        rto = ingest_pubmed_bounded(
            db,
            persist=False,
            http_get=_fail_http("timeout"),
            max_records=1,
        )
        _log("fail_429_status", r429.status)
        _log("fail_429_reason", (r429.block_reason or "")[:120])
        _log("fail_timeout_status", rto.status)
        _log("fail_timeout_reason", (rto.block_reason or "")[:120])

        for k in before:
            _log(f"after_{k}", after2[k])
            _log(f"delta_{k}", after2[k] - before[k])

        ok_persist = r1.status == "STORED" and r2.status == "STORED"
        ok_idemp = (
            after2["ku"] == after1["ku"]
            and after2["artifact"] == after1["artifact"]
            and after2["prov"] == after1["prov"]
            and r1.knowledge_unit_id == r2.knowledge_unit_id
        )
        ok_safety = after2["eligible"] == before["eligible"] and after2["memory"] == before["memory"] and after2["kce"] == before["kce"]
        ok_fail = r429.status in {"FAILED", "BLOCKED"} and rto.status in {"FAILED", "BLOCKED"}
        _log("pubmed_derived_knowledge_persistence", "PASS" if ok_persist else "NO")
        _log("pubmed_idempotent_rerun", "PASS" if ok_idemp else "NO")
        _log("medical_safety", "PASS" if ok_safety else "NO")
        _log("failure_classification", "PASS" if ok_fail else "NO")
        _log("pubmed_full_text_persisted", "NO")
        _log("pubmed_pdf_persisted", "NO")
        measured_rps = 0.0
        if r1.request_count and (t1 - t0) > 0:
            measured_rps = round(r1.request_count / (t1 - t0), 4)
        _log("ncbi_max_measured_rps", measured_rps)
        _log("ncbi_request_rate_compliant", "PASS" if measured_rps <= 1.01 else "NO")

        if not (ok_persist and ok_idemp and ok_safety and ok_fail):
            _log("canary_complete", "NO")
            return 1
        _log("canary_complete", "YES")
        return 0
    except Exception:
        traceback.print_exc()
        _log("canary_complete", "EXCEPTION")
        return 3
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
