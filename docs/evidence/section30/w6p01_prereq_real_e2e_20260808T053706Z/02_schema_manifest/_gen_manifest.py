"""One-shot generator: ORM↔Alembic gap manifest. Not imported by app."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models import Base

EV = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "orm_alembic_gap_manifest.json"

I5_TABLES = {
    "governed_source_profiles": ("GovernedSourceProfile", "I5-B2-P1+W1-P01"),
    "governed_source_profile_versions": ("GovernedSourceProfileVersion", "I5-B2-P1"),
    "weekly_knowledge_runs": ("WeeklyKnowledgeRun", "I5-IMPL-W1-P01"),
    "weekly_knowledge_run_attempts": ("WeeklyKnowledgeRunAttempt", "I5-IMPL-W1-P01"),
    "knowledge_gaps": ("KnowledgeGap", "I5-IMPL-W1-P01"),
    "weekly_run_source_results": ("WeeklyRunSourceResult", "I5-IMPL-W1-P01"),
    "weekly_run_gap_results": ("WeeklyRunGapResult", "I5-IMPL-W1-P01"),
    "i5_governance_decisions": ("I5GovernanceDecision", "I5-IMPL-W1-P01"),
    "i5_raw_evidence": ("I5RawEvidence", "I5-IMPL-W1-P02"),
    "knowledge_units": ("KnowledgeUnit", "I5-IMPL-W1-P02"),
    "knowledge_provenance": ("KnowledgeProvenance", "I5-IMPL-W1-P02"),
    "knowledge_memory_items": ("KnowledgeMemoryItem", "I5-IMPL-W2-P01"),
    "knowledge_memory_transitions": ("KnowledgeMemoryTransition", "I5-IMPL-W2-P01"),
    "knowledge_conflicts": ("KnowledgeConflict", "I5-IMPL-W2-P02"),
    "knowledge_safety_reviews": ("SafetyReviewQueueItem", "I5-IMPL-W2-P02"),
    "iran_doctors": ("IranDoctor", "I5-IMPL-W5-P01"),
    "iran_laboratories": ("IranLaboratory", "I5-IMPL-W5-P01"),
    "iran_hospitals": ("IranHospital", "I5-IMPL-W5-P01"),
}

ALEMBIC_COVERED = {
    "governed_source_profiles": "051_i5b2_governed_source_profile",
    "governed_source_profile_versions": "051_i5b2_governed_source_profile",
    "iran_doctors": "052_i5_w5_iran_directory",
    "iran_laboratories": "052_i5_w5_iran_directory",
    "iran_hospitals": "052_i5_w5_iran_directory",
}

GSP_051_COLS = {
    "id",
    "canonical_key",
    "locator_kind",
    "normalized_locator",
    "legacy_knowledge_source_id",
    "current_profile_version_id",
    "operational_status",
    "row_version",
    "created_at",
    "updated_at",
}


def main() -> None:
    total_cols = total_cks = total_fks = total_uqs = total_ix = 0
    missing_tables: list[str] = []
    gsp_missing_cols: list[str] = []
    tables_out: list[dict] = []

    for tname, (cls_name, owner) in I5_TABLES.items():
        table = Base.metadata.tables[tname]
        cols = []
        for c in table.columns:
            sd = None
            if c.server_default is not None:
                arg = getattr(c.server_default, "arg", c.server_default)
                sd = str(arg)
            cols.append(
                {
                    "name": c.name,
                    "type": str(c.type),
                    "nullable": c.nullable,
                    "primary_key": c.primary_key,
                    "server_default": sd,
                }
            )
            total_cols += 1
        checks = [
            {"name": ck.name, "sql": str(ck.sqltext)}
            for ck in table.constraints
            if ck.__class__.__name__ == "CheckConstraint"
        ]
        fks = []
        for fk in table.foreign_key_constraints:
            referred = None
            if fk.elements:
                referred = fk.elements[0].column.table.name
            fks.append(
                {
                    "name": fk.name,
                    "columns": list(fk.column_keys),
                    "referred_table": referred,
                    "ondelete": fk.ondelete,
                    "use_alter": bool(getattr(fk, "use_alter", False)),
                    "deferrable": fk.deferrable,
                }
            )
        uqs = [
            {"name": uq.name, "columns": list(uq.columns.keys())}
            for uq in table.constraints
            if uq.__class__.__name__ == "UniqueConstraint"
        ]
        ixs = []
        for ix in table.indexes:
            pg = ix.dialect_options.get("postgresql", {}) if ix.dialect_options else {}
            ixs.append(
                {
                    "name": ix.name,
                    "columns": [c.name for c in ix.columns],
                    "unique": ix.unique,
                    "postgresql_where": str(pg.get("where")) if pg.get("where") is not None else None,
                }
            )
        total_cks += len(checks)
        total_fks += len(fks)
        total_uqs += len(uqs)
        total_ix += len(ixs)

        in_alembic = tname in ALEMBIC_COVERED
        missing_table = not in_alembic
        if missing_table:
            missing_tables.append(tname)

        gsp_drift = None
        if tname == "governed_source_profiles":
            orm_cols = {c.name for c in table.columns}
            gsp_missing_cols = sorted(orm_cols - GSP_051_COLS)
            gsp_drift = {
                "051_columns": sorted(GSP_051_COLS),
                "orm_extra_columns": gsp_missing_cols,
                "051_missing_checks": [
                    c["name"]
                    for c in checks
                    if c["name"]
                    and c["name"].startswith("ck_gsp_")
                    and c["name"] != "ck_governed_source_profiles_locator_pair"
                ],
                "051_missing_indexes": [
                    i["name"] for i in ixs if i["name"] and i["name"].startswith("ix_gsp_")
                ],
            }

        tables_out.append(
            {
                "table": tname,
                "orm_class": cls_name,
                "owner_package": owner,
                "existing_in_alembic": (
                    "PARTIAL"
                    if tname == "governed_source_profiles"
                    else ("YES" if in_alembic else "NO")
                ),
                "created_by_revision": ALEMBIC_COVERED.get(tname),
                "missing_table": missing_table,
                "column_count": len(cols),
                "columns": cols,
                "checks": checks,
                "foreign_keys": fks,
                "unique_constraints": uqs,
                "indexes": ixs,
                "gsp_drift": gsp_drift,
            }
        )

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authority": "backend/app/models.py current ORM bytes",
        "alembic_start_head": "052_i5_w5_iran_directory",
        "tables": tables_out,
        "summary": {
            "ORM_I5_TABLE_COUNT": len(I5_TABLES),
            "ORM_I5_RELEVANT_COLUMN_COUNT": total_cols,
            "ORM_NAMED_CHECK_COUNT": total_cks,
            "ORM_FK_COUNT": total_fks,
            "ORM_UQ_COUNT": total_uqs,
            "ORM_INDEX_COUNT": total_ix,
            "MISSING_TABLES": missing_tables,
            "MISSING_TABLE_COUNT": len(missing_tables),
            "GSP_DRIFT_COLUMNS": gsp_missing_cols,
            "W6P01-MIGRATION-INVENTORY-COMPLETENESS-01": "CLOSED_BY_MANIFEST",
        },
    }
    OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("WROTE", OUT)
    print("tables", len(tables_out), "missing", len(missing_tables), "cols", total_cols, "cks", total_cks)


if __name__ == "__main__":
    main()
