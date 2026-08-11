"""Terminology importers/contracts — no proprietary content hard-coded.

Live imports requiring credentials/licenses are honestly classified NOT_EXECUTED_*.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app import models


TERMINOLOGY_STATES = (
    "CONNECTOR_READY",
    "AUTH_REQUIRED",
    "LICENSE_ACCEPTANCE_REQUIRED",
    "LIVE_VERIFIED",
    "BOUNDED_IMPORT_VERIFIED",
    "FULL_IMPORT_READY",
    "FULL_IMPORT_DEFERRED",
    "BLOCKED_BY_RIGHTS",
)


@dataclass(frozen=True)
class TerminologyConnectorStatus:
    system: str
    connector_state: str
    live_status: str
    rights_status: str
    notes: str


def icd11_status() -> TerminologyConnectorStatus:
    client_id = os.environ.get("SEDI_ICD11_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SEDI_ICD11_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return TerminologyConnectorStatus(
            system="ICD11",
            connector_state="AUTH_REQUIRED",
            live_status="NOT_EXECUTED_MISSING_CREDENTIALS",
            rights_status="API_CONTRACT_READY",
            notes="WHO ICD-11 API credentials required via SEDI_ICD11_CLIENT_ID/SECRET",
        )
    return TerminologyConnectorStatus(
        system="ICD11",
        connector_state="CONNECTOR_READY",
        live_status="NOT_EXECUTED",  # live canary may upgrade
        rights_status="CREDENTIALED",
        notes="Credentials present; bounded live verification separate",
    )


def mesh_status() -> TerminologyConnectorStatus:
    return TerminologyConnectorStatus(
        system="MESH",
        connector_state="CONNECTOR_READY",
        live_status="NOT_EXECUTED",
        rights_status="NLM_MeSH_RDF_OR_XML_RELEASE",
        notes="Official MeSH release formats; versioned; no discontinued legacy-only path",
    )


def rxnorm_status() -> TerminologyConnectorStatus:
    return TerminologyConnectorStatus(
        system="RXNORM",
        connector_state="LICENSE_ACCEPTANCE_REQUIRED",
        live_status="NOT_EXECUTED_RIGHTS_BLOCK",
        rights_status="UMLS_OR_RXNAV_PATHS_REQUIRE_EXPLICIT_ACCEPTABLE_LICENSE",
        notes="Only content paths with explicit acceptable licensing; do not assume embedded vocab reuse",
    )


def loinc_status() -> TerminologyConnectorStatus:
    return TerminologyConnectorStatus(
        system="LOINC",
        connector_state="LICENSE_ACCEPTANCE_REQUIRED",
        live_status="NOT_EXECUTED_RIGHTS_BLOCK",
        rights_status="LOINC_LICENSE_ACCEPTANCE_REQUIRED",
        notes="Honor attribution and third-party restrictions; never copy restricted adjacent material",
    )


def icf_status() -> TerminologyConnectorStatus:
    return TerminologyConnectorStatus(
        system="ICF",
        connector_state="AUTH_REQUIRED",
        live_status="NOT_EXECUTED_MISSING_CREDENTIALS",
        rights_status="WHO_API_OR_DOWNLOAD_REVIEW",
        notes="WHO ICF access/credentials required",
    )


def ichi_status() -> TerminologyConnectorStatus:
    return TerminologyConnectorStatus(
        system="ICHI",
        connector_state="AUTH_REQUIRED",
        live_status="NOT_EXECUTED_MISSING_CREDENTIALS",
        rights_status="WHO_API_OR_DOWNLOAD_REVIEW",
        notes="WHO ICHI access/credentials required",
    )


def all_terminology_statuses() -> list[TerminologyConnectorStatus]:
    return [icd11_status(), mesh_status(), rxnorm_status(), loinc_status(), icf_status(), ichi_status()]


def parse_mesh_descriptor_xml_fixture(content: bytes) -> list[dict[str, Any]]:
    """Bounded synthetic/official-shaped MeSH descriptor parser (deterministic tests)."""
    from backend.app.services.i5.know04.xml_safety import safe_parse_xml

    root = safe_parse_xml(content)
    out = []
    for desc in root.findall(".//DescriptorRecord"):
        ui = desc.findtext("DescriptorUI") or ""
        name = desc.findtext(".//DescriptorName/String") or ""
        treenums = [t.text or "" for t in desc.findall(".//TreeNumberList/TreeNumber")]
        out.append({"descriptor_ui": ui, "name": name, "tree_numbers": treenums})
    return out


def record_terminology_import_run(
    db: Session,
    *,
    terminology_system: str,
    release_version: str,
    source_note: str,
    import_status: str,
    content_hash: Optional[str] = None,
    release_date: Optional[date] = None,
    previous_release_version: Optional[str] = None,
    change_count: int = 0,
    new_codes: int = 0,
    changed_codes: int = 0,
    deprecated_codes: int = 0,
    replaced_codes: int = 0,
    mapping_conflicts: int = 0,
    notes: Optional[str] = None,
) -> models.I5TerminologyImportRun:
    """Never silently overwrite an old release — UNIQUE(system, release_version)."""
    existing = (
        db.query(models.I5TerminologyImportRun)
        .filter_by(terminology_system=terminology_system, release_version=release_version)
        .first()
    )
    if existing:
        if content_hash and existing.content_hash and content_hash != existing.content_hash:
            raise ValueError("SILENT_TERMINOLOGY_CONTENT_OVERWRITE_BLOCKED")
        # idempotent same release
        existing.import_status = "IDEMPOTENT_NOOP"
        db.flush()
        return existing
    row = models.I5TerminologyImportRun(
        terminology_system=terminology_system,
        release_version=release_version,
        release_date=release_date,
        source_note=source_note,
        content_hash=content_hash,
        previous_release_version=previous_release_version,
        import_status=import_status,
        change_count=change_count,
        new_codes=new_codes,
        changed_codes=changed_codes,
        deprecated_codes=deprecated_codes,
        replaced_codes=replaced_codes,
        mapping_conflicts=mapping_conflicts,
        notes=notes,
        retrieved_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def hash_release_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class Icd11ApiContract:
    """Official WHO ICD-11 API contract — no credentials in repository."""

    TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
    API_BASE = "https://id.who.int/icd"

    def auth_headers_from_env(self) -> Mapping[str, str]:
        status = icd11_status()
        if status.live_status == "NOT_EXECUTED_MISSING_CREDENTIALS":
            raise EnvironmentError(status.live_status)
        # Token exchange is live-only; deterministic tests never call this without injection.
        raise RuntimeError("LIVE_TOKEN_EXCHANGE_REQUIRES_INJECTED_TRANSPORT")
