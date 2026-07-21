"""I5-B2-P1 — governed_source_profiles + immutable versions

Revision ID: 051_i5b2_governed_source_profile
Revises: 050_gate4_event_idem

Additive compatibility-first schema for Section 15 I5-B2-P1.
Creates only the two P1 tables and integrity constraints.
No seed, backfill, network, fetch, publication, or scheduler activation.
Does not modify legacy knowledge_sources rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "051_i5b2_governed_source_profile"
down_revision: Union[str, None] = "050_gate4_event_idem"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "governed_source_profiles",
        sa.Column(
            "id",
            sa.Integer(),
            sa.Identity(start=1),
            nullable=False,
        ),
        sa.Column("canonical_key", sa.String(length=256), nullable=False),
        sa.Column("locator_kind", sa.String(length=64), nullable=True),
        sa.Column("normalized_locator", sa.String(length=1024), nullable=True),
        sa.Column("legacy_knowledge_source_id", sa.Integer(), nullable=True),
        sa.Column("current_profile_version_id", sa.Integer(), nullable=True),
        sa.Column(
            "operational_status",
            sa.String(length=32),
            nullable=False,
            server_default="disabled",
        ),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["legacy_knowledge_source_id"],
            ["knowledge_sources.id"],
            name="fk_gsp_legacy_knowledge_source_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_key", name="uq_governed_source_profiles_canonical_key"
        ),
        sa.UniqueConstraint(
            "legacy_knowledge_source_id",
            name="uq_governed_source_profiles_legacy_knowledge_source_id",
        ),
        sa.UniqueConstraint(
            "locator_kind",
            "normalized_locator",
            name="uq_governed_source_profiles_locator",
        ),
        sa.CheckConstraint(
            "(locator_kind IS NULL AND normalized_locator IS NULL) OR "
            "(locator_kind IS NOT NULL AND normalized_locator IS NOT NULL)",
            name="ck_governed_source_profiles_locator_pair",
        ),
    )
    op.create_index(
        "ix_governed_source_profiles_id",
        "governed_source_profiles",
        ["id"],
    )
    op.create_index(
        "ix_governed_source_profiles_operational_status",
        "governed_source_profiles",
        ["operational_status"],
    )

    op.create_table(
        "governed_source_profile_versions",
        sa.Column(
            "id",
            sa.Integer(),
            sa.Identity(start=1),
            nullable=False,
        ),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("version_seq", sa.Integer(), nullable=False),
        sa.Column("supersedes_version_id", sa.Integer(), nullable=True),
        sa.Column("snapshot_schema_version", sa.String(length=64), nullable=False),
        sa.Column("snapshot_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("publisher_authority_identity", sa.String(length=512), nullable=False),
        sa.Column("source_class", sa.String(length=64), nullable=False),
        sa.Column("authority_evidence_tier", sa.String(length=64), nullable=False),
        sa.Column("jurisdiction_scope", sa.String(length=32), nullable=False),
        sa.Column("jurisdiction_country_code", sa.String(length=16), nullable=True),
        sa.Column("jurisdiction_subdivision_code", sa.String(length=64), nullable=True),
        sa.Column("jurisdiction_organization_id", sa.String(length=128), nullable=True),
        sa.Column("primary_language", sa.String(length=16), nullable=False),
        sa.Column("specialty_domain", sa.String(length=128), nullable=False),
        sa.Column("license_status", sa.String(length=32), nullable=False),
        sa.Column("permitted_use_restriction", sa.String(length=512), nullable=False),
        sa.Column("storage_permission", sa.String(length=32), nullable=False),
        sa.Column("transformation_permission", sa.String(length=32), nullable=False),
        sa.Column(
            "display_redistribution_permission", sa.String(length=32), nullable=False
        ),
        sa.Column("automation_status", sa.String(length=32), nullable=False),
        sa.Column("verification_method", sa.String(length=64), nullable=False),
        sa.Column("freshness_policy_days", sa.Integer(), nullable=False),
        sa.Column("freshness_status", sa.String(length=32), nullable=False),
        sa.Column("fetch_policy", sa.String(length=128), nullable=False),
        sa.Column(
            "iran_first_applicable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("policy_version_reference", sa.String(length=128), nullable=False),
        sa.Column(
            "configuration_version_reference", sa.String(length=128), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["governed_source_profiles.id"],
            name="fk_gspv_profile_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "version_seq", name="uq_gspv_profile_version_seq"
        ),
        sa.UniqueConstraint(
            "profile_id",
            "snapshot_fingerprint",
            name="uq_gspv_profile_snapshot_fingerprint",
        ),
        sa.UniqueConstraint("profile_id", "id", name="uq_gspv_profile_id_id"),
        sa.CheckConstraint(
            "supersedes_version_id IS NULL OR supersedes_version_id <> id",
            name="ck_gspv_supersedes_not_self",
        ),
    )
    op.create_index(
        "ix_governed_source_profile_versions_id",
        "governed_source_profile_versions",
        ["id"],
    )
    op.create_index(
        "ix_governed_source_profile_versions_profile_id",
        "governed_source_profile_versions",
        ["profile_id"],
    )

    # Same-profile current pointer.
    op.create_foreign_key(
        "fk_gsp_current_version_same_profile",
        "governed_source_profiles",
        "governed_source_profile_versions",
        ["id", "current_profile_version_id"],
        ["profile_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )
    # Same-profile supersedes composite FK (replaces simple id-only FK).
    op.create_foreign_key(
        "fk_gspv_supersedes_same_profile",
        "governed_source_profile_versions",
        "governed_source_profile_versions",
        ["profile_id", "supersedes_version_id"],
        ["profile_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_gspv_supersedes_same_profile",
        "governed_source_profile_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_gsp_current_version_same_profile",
        "governed_source_profiles",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_governed_source_profile_versions_profile_id",
        table_name="governed_source_profile_versions",
    )
    op.drop_index(
        "ix_governed_source_profile_versions_id",
        table_name="governed_source_profile_versions",
    )
    op.drop_table("governed_source_profile_versions")
    op.drop_index(
        "ix_governed_source_profiles_operational_status",
        table_name="governed_source_profiles",
    )
    op.drop_index("ix_governed_source_profiles_id", table_name="governed_source_profiles")
    op.drop_table("governed_source_profiles")
