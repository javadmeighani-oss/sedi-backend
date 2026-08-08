"""Generate W1/W2 Alembic migrations from current ORM metadata (W6-P01).

Produces:
  053_i5_w1_p01_weekly_governance.py  (GSP alter + W1-P01 tables)
  054_i5_w1_p02_ku_provenance.py
  055_i5_w2_p01_knowledge_memory.py
  056_i5_w2_p02_conflict_safety.py

KnowledgeGap.target_knowledge_unit_id FK is deferred to 054 (FK DAG).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy import MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable, ForeignKeyConstraint

from backend.app.models import Base

VERSIONS = Path(__file__).resolve().parents[4] / "backend" / "alembic" / "versions"
# When run from evidence dir: workspace/docs/evidence/.../02_schema_manifest
# parents: 0=02_schema_manifest, 1=w6p01..., 2=section30, 3=evidence, 4=docs, 5=workspace
VERSIONS = Path(__file__).resolve().parents[5] / "backend" / "alembic" / "versions"

DIALECT = postgresql.dialect()

# FK that must wait until knowledge_units exists
DEFER_FK_TO_054 = {"fk_knowledge_gaps_target_knowledge_unit_id"}

W1_P01_TABLES = [
    "weekly_knowledge_runs",
    "weekly_knowledge_run_attempts",
    "knowledge_gaps",
    "weekly_run_source_results",
    "weekly_run_gap_results",
    "i5_governance_decisions",
]
W1_P02_TABLES = [
    "knowledge_units",
    "i5_raw_evidence",
    "knowledge_provenance",
]
W2_P01_TABLES = [
    "knowledge_memory_items",
    "knowledge_memory_transitions",
]
W2_P02_TABLES = [
    "knowledge_conflicts",
    "knowledge_safety_reviews",
]


def _compile(elem) -> str:
    return str(elem.compile(dialect=DIALECT)).rstrip() + ";"


def _table_without_deferred_fks(table: Table, defer_names: set[str]) -> Table:
    """Clone table metadata excluding named FKs (for cross-revision DAG)."""
    if not defer_names:
        return table
    md = MetaData()
    keep_fks = [fk for fk in table.constraints if not (isinstance(fk, ForeignKeyConstraint) and fk.name in defer_names)]
    # Also drop column-level ForeignKey objects that belong to deferred named FKs
    defer_cols = set()
    for fk in table.foreign_key_constraints:
        if fk.name in defer_names:
            defer_cols.update(fk.column_keys)

    cols = []
    for c in table.columns:
        if c.name in defer_cols:
            # recreate column without FK
            cols.append(c._copy())  # type: ignore[attr-defined]
            # strip FK from copy
            cols[-1].foreign_keys.clear()
        else:
            cols.append(c._copy())  # type: ignore[attr-defined]

    # Simpler approach: use include_foreign_key_constraints on CreateTable
    return table


def render_create_table_only(table: Table, exclude_fk_names: set[str] | None = None) -> list[str]:
    """CREATE TABLE without use_alter FKs and without excluded cross-revision FKs."""
    exclude_fk_names = exclude_fk_names or set()
    include_fks = [
        fk
        for fk in table.foreign_key_constraints
        if fk.name not in exclude_fk_names and not getattr(fk, "use_alter", False)
    ]
    stmt = CreateTable(table, include_foreign_key_constraints=include_fks)
    sql = _compile(stmt)
    return [f"    # --- {table.name} ---", '    op.execute("""', sql, '""")']


def render_table_indexes(table: Table) -> list[str]:
    lines = []
    for ix in sorted(table.indexes, key=lambda i: i.name or ""):
        lines.append(f'    op.execute("""{_compile(CreateIndex(ix))}""")')
    return lines


def collect_use_alter_fks(tables: list[Table], exclude_fk_names: set[str] | None = None) -> list[str]:
    exclude_fk_names = exclude_fk_names or set()
    lines: list[str] = []
    for table in tables:
        for fk in table.foreign_key_constraints:
            if fk.name in exclude_fk_names:
                continue
            if not getattr(fk, "use_alter", False):
                continue
            lines.extend(_render_fk_op(table, fk))
    return lines


def _render_fk_op(table: Table, fk: ForeignKeyConstraint) -> list[str]:
    cols = ", ".join(f"'{c}'" for c in fk.column_keys)
    ref_table = fk.elements[0].column.table.name
    ref_cols = ", ".join(f"'{e.column.name}'" for e in fk.elements)
    ondelete = f", ondelete='{fk.ondelete}'" if fk.ondelete else ""
    defer = ""
    if fk.deferrable:
        initially = getattr(fk, "initially", None) or "DEFERRED"
        defer = f", deferrable=True, initially='{initially}'"
    return [
        f"    op.create_foreign_key(",
        f"        '{fk.name}',",
        f"        '{table.name}',",
        f"        '{ref_table}',",
        f"        [{cols}],",
        f"        [{ref_cols}]{ondelete}{defer},",
        f"    )",
    ]


def render_drop_table(table: Table) -> list[str]:
    lines = []
    # Drop use_alter FKs first
    for fk in table.foreign_key_constraints:
        if getattr(fk, "use_alter", False):
            lines.append(f"    op.drop_constraint('{fk.name}', '{table.name}', type_='foreignkey')")
    for ix in sorted(table.indexes, key=lambda i: i.name or "", reverse=True):
        lines.append(f"    op.drop_index('{ix.name}', table_name='{table.name}')")
    lines.append(f"    op.drop_table('{table.name}')")
    return lines


def render_gsp_alter() -> tuple[list[str], list[str]]:
    """Additive W1-P01 GSP columns/checks/indexes missing from 051."""
    up = [
        "    # --- GSP W1-P01 additive contract (alter 051) ---",
        "    op.add_column('governed_source_profiles', sa.Column('registry_state', sa.String(length=32), nullable=False, server_default='DISCOVERED'))",
        "    op.add_column('governed_source_profiles', sa.Column('runtime_eligibility', sa.String(length=32), nullable=False, server_default='NOT_ELIGIBLE'))",
        "    op.add_column('governed_source_profiles', sa.Column('block_reason', sa.Text(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('owner_reference', sa.String(length=512), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('reviewer_reference', sa.String(length=512), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('approver_reference', sa.String(length=512), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('topic_coverage', sa.Text(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('effective_from', sa.DateTime(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('effective_to', sa.DateTime(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('last_discovered_at', sa.DateTime(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('last_checked_at', sa.DateTime(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('last_reviewed_at', sa.DateTime(), nullable=True))",
        "    op.add_column('governed_source_profiles', sa.Column('canonicalization_version', sa.String(length=32), nullable=False, server_default='v1'))",
    ]
    # Pull check SQL from ORM
    gsp = Base.metadata.tables["governed_source_profiles"]
    for ck in gsp.constraints:
        if ck.__class__.__name__ != "CheckConstraint":
            continue
        if not ck.name or not ck.name.startswith("ck_gsp_"):
            continue
        if ck.name == "ck_governed_source_profiles_locator_pair":
            continue
        sql = str(ck.sqltext)
        up.append(
            f"    op.create_check_constraint('{ck.name}', 'governed_source_profiles', \"\"\"{sql}\"\"\")"
        )
    for ix_name, cols in [
        ("ix_gsp_registry_state", ["registry_state"]),
        ("ix_gsp_runtime_eligibility", ["runtime_eligibility"]),
        ("ix_gsp_last_checked_at", ["last_checked_at"]),
        ("ix_gsp_last_reviewed_at", ["last_reviewed_at"]),
        ("ix_gsp_registry_runtime", ["registry_state", "runtime_eligibility"]),
    ]:
        col_list = ", ".join(f"'{c}'" for c in cols)
        up.append(f"    op.create_index('{ix_name}', 'governed_source_profiles', [{col_list}])")

    down = [
        "    op.drop_index('ix_gsp_registry_runtime', table_name='governed_source_profiles')",
        "    op.drop_index('ix_gsp_last_reviewed_at', table_name='governed_source_profiles')",
        "    op.drop_index('ix_gsp_last_checked_at', table_name='governed_source_profiles')",
        "    op.drop_index('ix_gsp_runtime_eligibility', table_name='governed_source_profiles')",
        "    op.drop_index('ix_gsp_registry_state', table_name='governed_source_profiles')",
        "    op.drop_constraint('ck_gsp_effective_window_order', 'governed_source_profiles', type_='check')",
        "    op.drop_constraint('ck_gsp_block_reason_length', 'governed_source_profiles', type_='check')",
        "    op.drop_constraint('ck_gsp_runtime_eligibility_vocab', 'governed_source_profiles', type_='check')",
        "    op.drop_constraint('ck_gsp_registry_state_vocab', 'governed_source_profiles', type_='check')",
        "    op.drop_column('governed_source_profiles', 'canonicalization_version')",
        "    op.drop_column('governed_source_profiles', 'last_reviewed_at')",
        "    op.drop_column('governed_source_profiles', 'last_checked_at')",
        "    op.drop_column('governed_source_profiles', 'last_discovered_at')",
        "    op.drop_column('governed_source_profiles', 'effective_to')",
        "    op.drop_column('governed_source_profiles', 'effective_from')",
        "    op.drop_column('governed_source_profiles', 'topic_coverage')",
        "    op.drop_column('governed_source_profiles', 'approver_reference')",
        "    op.drop_column('governed_source_profiles', 'reviewer_reference')",
        "    op.drop_column('governed_source_profiles', 'owner_reference')",
        "    op.drop_column('governed_source_profiles', 'block_reason')",
        "    op.drop_column('governed_source_profiles', 'runtime_eligibility')",
        "    op.drop_column('governed_source_profiles', 'registry_state')",
    ]
    return up, down


def write_migration(
    filename: str,
    revision: str,
    down_revision: str,
    title: str,
    package: str,
    upgrade_body: list[str],
    downgrade_body: list[str],
) -> Path:
    path = VERSIONS / filename
    content = f'''"""{title}

Revision ID: {revision}
Revises: {down_revision}

{package} — schema authoring for current frozen ORM (W6-P01).
Additive PostgreSQL-only. Exact ORM CHECK/FK/UQ/Index parity.
No seed, network, activation, or Base.metadata.create_all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "{revision}"
down_revision: Union[str, None] = "{down_revision}"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
{chr(10).join(upgrade_body)}


def downgrade() -> None:
{chr(10).join(downgrade_body)}
'''
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def render_tables(names: Iterable[str], exclude_fk_names: set[str] | None = None) -> tuple[list[str], list[str]]:
    up: list[str] = []
    down: list[str] = []
    tables = [Base.metadata.tables[n] for n in names]
    # 1) CREATE TABLE (inline FKs only where targets already exist / same revision order)
    for t in tables:
        up.extend(render_create_table_only(t, exclude_fk_names=exclude_fk_names))
        up.append("")
    # 2) indexes
    for t in tables:
        up.extend(render_table_indexes(t))
    up.append("")
    # 3) deferred / use_alter FKs after all tables exist
    alter_fks = collect_use_alter_fks(tables, exclude_fk_names=exclude_fk_names)
    if alter_fks:
        up.append("    # deferred / use_alter foreign keys")
        up.extend(alter_fks)
        up.append("")
    # Downgrade: drop use_alter FKs first, then reverse table drops
    if alter_fks:
        down.append("    # drop deferred / use_alter foreign keys first")
        for table in tables:
            for fk in table.foreign_key_constraints:
                if fk.name in (exclude_fk_names or set()):
                    continue
                if getattr(fk, "use_alter", False):
                    down.append(
                        f"    op.drop_constraint('{fk.name}', '{table.name}', type_='foreignkey')"
                    )
        down.append("")
    for t in reversed(tables):
        # skip use_alter drops inside render_drop_table (already done)
        lines = []
        for ix in sorted(t.indexes, key=lambda i: i.name or "", reverse=True):
            lines.append(f"    op.drop_index('{ix.name}', table_name='{t.name}')")
        lines.append(f"    op.drop_table('{t.name}')")
        down.extend(lines)
    return up, down


def main() -> None:
    assert VERSIONS.is_dir(), VERSIONS

    # --- 053 W1-P01 ---
    gsp_up, gsp_down = render_gsp_alter()
    t_up, t_down = render_tables(W1_P01_TABLES, exclude_fk_names=DEFER_FK_TO_054)
    # After creating weekly runs/attempts, create deferred mutual FKs already handled via use_alter in render
    write_migration(
        "053_i5_w1_p01_weekly_governance.py",
        "053_i5_w1_p01_weekly_governance",
        "052_i5_w5_iran_directory",
        "I5 W1-P01 weekly governance + GSP additive",
        "MIG-I5-W1-P01",
        gsp_up + [""] + t_up,
        t_down + [""] + gsp_down,
    )

    # --- 054 W1-P02 ---
    u2, d2 = render_tables(W1_P02_TABLES)
    # Add deferred KnowledgeGap → KnowledgeUnit FK
    u2.append("    # Deferred from 053: KnowledgeGap.target_knowledge_unit_id")
    u2.append(
        "    op.create_foreign_key("
        "'fk_knowledge_gaps_target_knowledge_unit_id', "
        "'knowledge_gaps', 'knowledge_units', "
        "['target_knowledge_unit_id'], ['id'], ondelete='RESTRICT')"
    )
    d2_pre = [
        "    op.drop_constraint('fk_knowledge_gaps_target_knowledge_unit_id', 'knowledge_gaps', type_='foreignkey')",
    ]
    write_migration(
        "054_i5_w1_p02_ku_provenance.py",
        "054_i5_w1_p02_ku_provenance",
        "053_i5_w1_p01_weekly_governance",
        "I5 W1-P02 KU / raw evidence / provenance",
        "MIG-I5-W1-P02",
        u2,
        d2_pre + d2,
    )

    # --- 055 W2-P01 ---
    u3, d3 = render_tables(W2_P01_TABLES)
    write_migration(
        "055_i5_w2_p01_knowledge_memory.py",
        "055_i5_w2_p01_knowledge_memory",
        "054_i5_w1_p02_ku_provenance",
        "I5 W2-P01 knowledge memory / transitions",
        "MIG-I5-W2-P01",
        u3,
        d3,
    )

    # --- 056 W2-P02 ---
    u4, d4 = render_tables(W2_P02_TABLES)
    write_migration(
        "056_i5_w2_p02_conflict_safety.py",
        "056_i5_w2_p02_conflict_safety",
        "055_i5_w2_p01_knowledge_memory",
        "I5 W2-P02 conflict / medical-safety review",
        "MIG-I5-W2-P02",
        u4,
        d4,
    )
    print("WROTE migrations into", VERSIONS)
    for name in [
        "053_i5_w1_p01_weekly_governance.py",
        "054_i5_w1_p02_ku_provenance.py",
        "055_i5_w2_p01_knowledge_memory.py",
        "056_i5_w2_p02_conflict_safety.py",
    ]:
        p = VERSIONS / name
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
