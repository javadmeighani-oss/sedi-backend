"""Terminology expansion foundation — contracts only; no bulk proprietary ingest."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import TerminologyImportScope, TerminologySystem


def upsert_import_contract(
    db: Session,
    *,
    terminology_system: str,
    contract_key: str,
    official_source_note: str,
    rights_status: str,
    import_scope: str,
    api_or_mechanism: Optional[str] = None,
    notes: Optional[str] = None,
) -> models.I5TerminologyImportContract:
    TerminologySystem(terminology_system)
    TerminologyImportScope(import_scope)
    row = (
        db.query(models.I5TerminologyImportContract)
        .filter_by(terminology_system=terminology_system, contract_key=contract_key)
        .first()
    )
    if row is None:
        row = models.I5TerminologyImportContract(
            terminology_system=terminology_system,
            contract_key=contract_key,
            official_source_note=official_source_note,
            rights_status=rights_status,
            import_scope=import_scope,
        )
        db.add(row)
    row.official_source_note = official_source_note
    row.rights_status = rights_status
    row.import_scope = import_scope
    row.api_or_mechanism = api_or_mechanism
    row.notes = notes
    db.flush()
    return row


def seed_terminology_contracts(db: Session) -> int:
    specs = [
        (
            TerminologySystem.ICD11.value,
            "who_icd11_api",
            "WHO ICD-11 API / MMS import contract",
            "OFFICIAL_API_REVIEWED",
            TerminologyImportScope.FULL_IMPORT_DEFERRED.value,
            "ICD11_FULL_IMPORT=NEXT_TERMINOLOGY_WAVE",
        ),
        (
            TerminologySystem.MESH.value,
            "nlm_mesh_mapping",
            "NLM MeSH mapping foundation",
            "RIGHTS_BOUNDED",
            TerminologyImportScope.API_CONTRACT.value,
            None,
        ),
        (
            TerminologySystem.RXNORM.value,
            "nlm_rxnorm_mapping",
            "NLM RxNorm drug normalization foundation",
            "RIGHTS_BOUNDED",
            TerminologyImportScope.BOUNDED_FIXTURE.value,
            None,
        ),
        (
            TerminologySystem.LOINC.value,
            "regenstrief_loinc_mapping",
            "LOINC lab/observation mapping foundation",
            "RIGHTS_BOUNDED",
            TerminologyImportScope.BOUNDED_FIXTURE.value,
            None,
        ),
        (
            TerminologySystem.ICF.value,
            "who_icf_functioning",
            "ICF functioning/disability mapping foundation",
            "RIGHTS_BOUNDED",
            TerminologyImportScope.METADATA_ONLY.value,
            None,
        ),
        (
            TerminologySystem.ICHI.value,
            "who_ichi_interventions",
            "ICHI intervention classification foundation",
            "RIGHTS_BOUNDED",
            TerminologyImportScope.METADATA_ONLY.value,
            None,
        ),
    ]
    n = 0
    for system, key, note, rights, scope, extra in specs:
        upsert_import_contract(
            db,
            terminology_system=system,
            contract_key=key,
            official_source_note=note,
            rights_status=rights,
            import_scope=scope,
            notes=extra,
        )
        n += 1
    return n
